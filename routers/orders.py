from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Optional
from datetime import datetime
from database import get_db
from routers.auth import get_current_user, require_owner
from services.order_service import (
    generate_order_hash, is_duplicate, log_status_change, should_queue,
)
from websocket_manager import ws_manager
import models
import schemas

router = APIRouter()


# ── Create order ─────────────────────────────────────────────────────────────

@router.post("/", response_model=schemas.OrderResponse)
async def create_order(
    data: schemas.OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == models.UserRole.dueno:
        raise HTTPException(403, "Los dueños no pueden crear pedidos")

    # ── Duplicate check ──────────────────────────────────────────────────
    today = datetime.utcnow().date()
    order_hash = generate_order_hash(current_user.id, data.items, today)
    if is_duplicate(db, current_user.id, order_hash):
        raise HTTPException(
            409,
            "Ya tienes un pedido activo con estos productos en las últimas 24 horas. "
            "Si deseas hacer uno nuevo de todas formas, espera 24 horas o usa productos diferentes.",
        )

    # ── Concurrency: en_cola if at capacity ──────────────────────────────
    initial_status = (
        models.OrderStatus.en_cola
        if should_queue(db)
        else models.OrderStatus.pendiente
    )

    order = models.Order(
        user_id=current_user.id,
        payment_method=data.payment_method,
        notes=data.notes,
        status=initial_status,
        order_type=models.OrderType.pedido,
        total_amount=0.0,
        unique_hash=order_hash,
    )
    db.add(order)
    db.flush()

    total = 0.0
    for item_data in data.items:
        product = db.query(models.Product).filter(
            models.Product.id == item_data.product_id,
            models.Product.active == True,
        ).first()
        if not product:
            db.rollback()
            raise HTTPException(404, f"Producto {item_data.product_id} no encontrado")
        if item_data.quantity < product.min_qty:
            db.rollback()
            raise HTTPException(400, f"Mínimo {product.min_qty} unidades para '{product.name}'")
        if item_data.quantity > product.max_qty:
            db.rollback()
            raise HTTPException(400, f"Máximo {product.max_qty} unidades para '{product.name}'")

        subtotal = item_data.quantity * product.price_per_unit
        total   += subtotal
        db.add(models.OrderItem(
            order_id=order.id,
            product_id=product.id,
            quantity=item_data.quantity,
            unit_price=product.price_per_unit,
            subtotal=subtotal,
        ))

    order.total_amount = total
    db.add(models.Payment(
        order_id=order.id,
        method=data.payment_method,
        amount=total,
        status=models.PaymentStatus.pendiente,
    ))

    # Audit log
    log_status_change(db, order.id, current_user.id, None, initial_status.value, "Pedido creado")
    db.commit()
    db.refresh(order)

    # Notify admins via WebSocket
    background_tasks.add_task(
        ws_manager.send_new_order,
        order.id, current_user.name, total, initial_status.value,
    )
    return order


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=schemas.DashboardStats)
def dashboard(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    today = datetime.utcnow().date()

    orders_today = db.query(func.count(models.Order.id)).filter(
        func.date(models.Order.created_at) == today,
        models.Order.archived == False,
    ).scalar() or 0

    revenue_today = db.query(func.sum(models.Order.total_amount)).filter(
        func.date(models.Order.created_at) == today,
        models.Order.status == models.OrderStatus.entregado,
        models.Order.archived == False,
    ).scalar() or 0.0

    pending_orders = db.query(func.count(models.Order.id)).filter(
        models.Order.status.in_([models.OrderStatus.pendiente, models.OrderStatus.en_cola]),
        models.Order.archived == False,
    ).scalar() or 0

    top = (
        db.query(
            models.Product.name,
            func.sum(models.OrderItem.quantity).label("total_sold"),
        )
        .join(models.OrderItem)
        .join(models.Order, models.Order.id == models.OrderItem.order_id)
        .filter(models.Order.archived == False)
        .group_by(models.Product.id, models.Product.name)
        .order_by(desc("total_sold"))
        .limit(5)
        .all()
    )

    return schemas.DashboardStats(
        orders_today=orders_today,
        revenue_today=round(float(revenue_today), 2),
        pending_orders=pending_orders,
        top_products=[{"name": r[0], "total_sold": int(r[1])} for r in top],
    )


# ── List orders ───────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.OrderResponse])
def list_orders(
    status:     Optional[str] = Query(None),
    from_date:  Optional[str] = Query(None),
    to_date:    Optional[str] = Query(None),
    archived:   Optional[bool] = Query(False),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Order)
    if current_user.role == models.UserRole.cliente:
        query = query.filter(models.Order.user_id == current_user.id)
    if not archived:
        query = query.filter(models.Order.archived == False)
    if status:
        query = query.filter(models.Order.status == status)
    if from_date:
        query = query.filter(models.Order.created_at >= from_date)
    if to_date:
        query = query.filter(models.Order.created_at <= to_date)
    return query.order_by(desc(models.Order.created_at)).all()


# ── Get single order ──────────────────────────────────────────────────────────

@router.get("/{order_id}", response_model=schemas.OrderResponse)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    if current_user.role == models.UserRole.cliente and order.user_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")
    return order


# ── Update status ─────────────────────────────────────────────────────────────

@router.put("/{order_id}/status", response_model=schemas.OrderResponse)
async def update_status(
    order_id: int,
    data: schemas.OrderStatusUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(require_owner),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    if order.status == models.OrderStatus.entregado:
        raise HTTPException(400, "No se puede modificar un pedido ya entregado")
    if order.archived:
        raise HTTPException(400, "No se puede modificar un pedido archivado")

    prev_status = order.status.value
    order.status     = data.status
    order.updated_at = datetime.utcnow()

    if data.status == models.OrderStatus.rechazado and data.notes:
        order.rejection_reason = data.notes

    log_status_change(db, order.id, current_user.id, prev_status, data.status.value, data.notes)
    db.commit()
    db.refresh(order)

    background_tasks.add_task(ws_manager.send_status_change, order.id, data.status.value)
    return order


# ── Order audit log ───────────────────────────────────────────────────────────

@router.get("/{order_id}/logs")
def get_order_logs(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    if current_user.role == models.UserRole.cliente and order.user_id != current_user.id:
        raise HTTPException(403, "Acceso denegado")

    logs = (
        db.query(models.OrderLog)
        .filter(models.OrderLog.order_id == order_id)
        .order_by(models.OrderLog.created_at)
        .all()
    )
    return [
        {
            "id":          log.id,
            "from_status": log.from_status,
            "to_status":   log.to_status,
            "notes":       log.notes,
            "user":        log.user.name if log.user else None,
            "created_at":  log.created_at.isoformat(),
        }
        for log in logs
    ]
