"""Admin-only endpoints: accounting, suspicious orders, archiving."""
import io
from datetime import datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from routers.auth import require_owner
from services.contabilidad_service import get_stats, export_to_csv
import models

router = APIRouter()


def _range(period: str):
    today = datetime.utcnow().date()
    if period == "hoy":
        start = datetime.combine(today, datetime.min.time())
    elif period == "semana":
        start = datetime.combine(today - timedelta(days=7), datetime.min.time())
    else:  # mes
        start = datetime.combine(today.replace(day=1), datetime.min.time())
    end = datetime.combine(today, datetime.max.time())
    return start, end


# ── Accounting endpoints ──────────────────────────────────────────────────────

@router.get("/contabilidad/hoy")
def contabilidad_hoy(db: Session = Depends(get_db), _=Depends(require_owner)):
    start, end = _range("hoy")
    return get_stats(db, start, end)


@router.get("/contabilidad/semana")
def contabilidad_semana(db: Session = Depends(get_db), _=Depends(require_owner)):
    start, end = _range("semana")
    return get_stats(db, start, end)


@router.get("/contabilidad/mes")
def contabilidad_mes(db: Session = Depends(get_db), _=Depends(require_owner)):
    start, end = _range("mes")
    return get_stats(db, start, end)


@router.get("/contabilidad/exportar")
def exportar_csv(
    period: Literal["hoy", "semana", "mes"] = Query("hoy"),
    db: Session = Depends(get_db),
    _=Depends(require_owner),
):
    start, end = _range(period)
    csv_text    = export_to_csv(db, start, end)
    filename    = f"kuyay-{period}-{datetime.utcnow().strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        io.StringIO(csv_text),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ── Suspicious orders ─────────────────────────────────────────────────────────

@router.get("/pedidos/sospechosos")
def pedidos_sospechosos(db: Session = Depends(get_db), _=Depends(require_owner)):
    today = datetime.utcnow().date()
    start = datetime.combine(today, datetime.min.time())
    end   = datetime.combine(today, datetime.max.time())

    # Clients with 2+ orders today
    multi = (
        db.query(models.Order.user_id, func.count(models.Order.id).label("cnt"))
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            models.Order.archived == False,
        )
        .group_by(models.Order.user_id)
        .having(func.count(models.Order.id) > 1)
        .all()
    )

    # Gather user names
    user_map = {}
    for user_id, _ in multi:
        u = db.query(models.User).filter(models.User.id == user_id).first()
        user_map[user_id] = u.name if u else f"#{user_id}"

    # Orders with total units > 200
    over_max = (
        db.query(
            models.Order.id,
            func.sum(models.OrderItem.quantity).label("total_units"),
        )
        .join(models.OrderItem)
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            models.Order.archived == False,
        )
        .group_by(models.Order.id)
        .having(func.sum(models.OrderItem.quantity) > 200)
        .all()
    )

    # Duplicate hashes today
    dup_hashes = (
        db.query(models.Order.unique_hash, func.count(models.Order.id).label("cnt"))
        .filter(
            models.Order.unique_hash != None,
            models.Order.archived == False,
        )
        .group_by(models.Order.unique_hash)
        .having(func.count(models.Order.id) > 1)
        .all()
    )

    return {
        "multiple_orders_today": [
            {"user_id": uid, "name": user_map[uid], "count": cnt}
            for uid, cnt in multi
        ],
        "over_max_quantity": [
            {"order_id": oid, "total_units": int(units)}
            for oid, units in over_max
        ],
        "duplicate_hashes": [
            {"hash_preview": (h[:12] + "...") if h else "?", "count": cnt}
            for h, cnt in dup_hashes
        ],
    }


# ── Archive / restore ─────────────────────────────────────────────────────────

@router.post("/pedidos/{order_id}/archivar")
def archivar(
    order_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_owner),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    order.archived = True
    db.commit()
    return {"message": f"Pedido #{order_id} archivado (no eliminado)"}


@router.post("/pedidos/{order_id}/restaurar")
def restaurar(
    order_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_owner),
):
    order = db.query(models.Order).filter(models.Order.id == order_id).first()
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    order.archived = False
    db.commit()
    return {"message": f"Pedido #{order_id} restaurado"}


# ── Queue management ──────────────────────────────────────────────────────────

@router.post("/cola/procesar")
def procesar_cola(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(require_owner),
):
    """Move the oldest 'en_cola' orders to 'pendiente' (up to limit)."""
    queued = (
        db.query(models.Order)
        .filter(
            models.Order.status == models.OrderStatus.en_cola,
            models.Order.archived == False,
        )
        .order_by(models.Order.created_at)
        .limit(limit)
        .all()
    )
    moved = 0
    for order in queued:
        order.status     = models.OrderStatus.pendiente
        order.updated_at = datetime.utcnow()
        moved           += 1
    db.commit()
    return {"moved": moved, "message": f"{moved} pedido(s) pasaron de en_cola a pendiente"}
