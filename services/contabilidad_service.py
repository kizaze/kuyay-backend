"""Accounting / reporting calculations — read-only, never modifies data."""
import csv
import io
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
import models


def get_stats(db: Session, start: datetime, end: datetime) -> dict:
    base_filter = [
        models.Order.created_at >= start,
        models.Order.created_at <= end,
        models.Order.archived == False,
    ]

    total_orders = (
        db.query(func.count(models.Order.id))
        .filter(*base_filter)
        .scalar() or 0
    )

    # Count by status
    by_status = {}
    for s in models.OrderStatus:
        count = (
            db.query(func.count(models.Order.id))
            .filter(*base_filter, models.Order.status == s)
            .scalar() or 0
        )
        by_status[s.value] = count

    non_rejected = [
        *base_filter,
        models.Order.status != models.OrderStatus.rechazado,
    ]

    expected_revenue = (
        db.query(func.sum(models.Order.total_amount))
        .filter(*non_rejected)
        .scalar() or 0.0
    )

    confirmed_revenue = (
        db.query(func.sum(models.Order.total_amount))
        .filter(*base_filter, models.Order.status == models.OrderStatus.entregado)
        .scalar() or 0.0
    )

    pending_collection = (
        db.query(func.sum(models.Order.total_amount))
        .filter(
            *base_filter,
            models.Order.status.in_([
                models.OrderStatus.aceptado,
                models.OrderStatus.en_preparacion,
                models.OrderStatus.en_camino,
            ]),
        )
        .scalar() or 0.0
    )

    # Units by product (exclude rejected)
    units_q = (
        db.query(
            models.Product.name,
            func.sum(models.OrderItem.quantity).label("units"),
        )
        .join(models.OrderItem, models.OrderItem.product_id == models.Product.id)
        .join(models.Order,     models.Order.id == models.OrderItem.order_id)
        .filter(*non_rejected)
        .group_by(models.Product.id, models.Product.name)
        .order_by(func.sum(models.OrderItem.quantity).desc())
        .all()
    )

    total_returns = (
        db.query(func.count(models.Return.id))
        .filter(models.Return.created_at >= start, models.Return.created_at <= end)
        .scalar() or 0
    )

    archived_count = (
        db.query(func.count(models.Order.id))
        .filter(
            models.Order.created_at >= start,
            models.Order.created_at <= end,
            models.Order.archived == True,
        )
        .scalar() or 0
    )

    return {
        "period": {
            "start": start.strftime("%Y-%m-%d"),
            "end":   end.strftime("%Y-%m-%d"),
        },
        "total_orders":        total_orders,
        "by_status":           by_status,
        "expected_revenue":    round(float(expected_revenue), 2),
        "confirmed_revenue":   round(float(confirmed_revenue), 2),
        "pending_collection":  round(float(pending_collection), 2),
        "units_by_product":    [{"name": r[0], "units": int(r[1])} for r in units_q],
        "total_returns":       total_returns,
        "archived_orders":     archived_count,
    }


def export_to_csv(db: Session, start: datetime, end: datetime) -> str:
    orders = (
        db.query(models.Order)
        .filter(models.Order.created_at >= start, models.Order.created_at <= end)
        .order_by(models.Order.created_at)
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Cliente", "Email", "Estado", "Tipo",
        "Total (S/.)", "Pago", "Fecha", "Archivado", "Motivo rechazo",
    ])

    for o in orders:
        writer.writerow([
            o.id,
            o.user.name  if o.user  else f"#{o.user_id}",
            o.user.email if o.user  else "",
            o.status.value,
            o.order_type.value,
            f"{o.total_amount:.2f}",
            o.payment_method.value if o.payment_method else "",
            o.created_at.strftime("%Y-%m-%d %H:%M"),
            "Sí" if o.archived else "No",
            o.rejection_reason or "",
        ])

    return output.getvalue()
