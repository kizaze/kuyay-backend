from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from routers.auth import get_current_user, require_owner
import models
import schemas

router = APIRouter()


@router.post("/", response_model=schemas.ReturnResponse)
def request_return(
    data: schemas.ReturnCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    order = db.query(models.Order).filter(
        models.Order.id == data.original_order_id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    if current_user.role == models.UserRole.cliente and order.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    if order.status not in (models.OrderStatus.entregado, models.OrderStatus.en_camino):
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden devolver pedidos en camino o entregados",
        )
    existing = db.query(models.Return).filter(
        models.Return.original_order_id == data.original_order_id
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una solicitud de devolución para este pedido",
        )

    ret = models.Return(
        original_order_id=data.original_order_id,
        reason=data.reason,
        status=models.ReturnStatus.solicitada,
    )
    db.add(ret)
    db.commit()
    db.refresh(ret)
    return ret


@router.get("/", response_model=List[schemas.ReturnResponse])
def list_returns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if current_user.role == models.UserRole.dueno:
        return db.query(models.Return).order_by(models.Return.created_at.desc()).all()
    return (
        db.query(models.Return)
        .join(models.Order, models.Return.original_order_id == models.Order.id)
        .filter(models.Order.user_id == current_user.id)
        .all()
    )


@router.put("/{return_id}/approve", response_model=schemas.ReturnResponse)
def approve_return(
    return_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    ret = db.query(models.Return).filter(models.Return.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    if ret.status != models.ReturnStatus.solicitada:
        raise HTTPException(status_code=400, detail="La devolución ya fue procesada")

    original = db.query(models.Order).filter(
        models.Order.id == ret.original_order_id
    ).first()

    new_order = models.Order(
        user_id=original.user_id,
        status=models.OrderStatus.pendiente,
        order_type=models.OrderType.devolucion,
        original_order_id=original.id,
        total_amount=original.total_amount,
        payment_method=original.payment_method,
        notes=f"Devolución del pedido #{original.id}: {ret.reason}",
    )
    db.add(new_order)
    db.flush()

    for item in original.items:
        db.add(models.OrderItem(
            order_id=new_order.id,
            product_id=item.product_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item.subtotal,
        ))

    ret.status = models.ReturnStatus.aprobada
    ret.new_order_id = new_order.id
    db.commit()
    db.refresh(ret)
    return ret


@router.put("/{return_id}/reject", response_model=schemas.ReturnResponse)
def reject_return(
    return_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    ret = db.query(models.Return).filter(models.Return.id == return_id).first()
    if not ret:
        raise HTTPException(status_code=404, detail="Devolución no encontrada")
    if ret.status != models.ReturnStatus.solicitada:
        raise HTTPException(status_code=400, detail="La devolución ya fue procesada")
    ret.status = models.ReturnStatus.rechazada
    db.commit()
    db.refresh(ret)
    return ret
