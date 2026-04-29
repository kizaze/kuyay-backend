"""
Order business logic:
- Unique hash generation and duplicate detection
- Concurrency control (max 50 simultaneous orders)
- Audit log helpers
"""
import hashlib
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import models

# ── Concurrency control ────────────────────────────────────────────────────
MAX_CONCURRENT = 50


def active_order_count(db: Session) -> int:
    """Count orders currently being processed (not final states)."""
    active_statuses = [
        models.OrderStatus.en_cola,
        models.OrderStatus.pendiente,
        models.OrderStatus.aceptado,
        models.OrderStatus.en_preparacion,
        models.OrderStatus.en_camino,
    ]
    return (
        db.query(models.Order)
        .filter(models.Order.status.in_(active_statuses), models.Order.archived == False)
        .count()
    )


def should_queue(db: Session) -> bool:
    """Returns True if the system is at capacity and order must be queued."""
    return active_order_count(db) >= MAX_CONCURRENT


# ── Hash / duplicate detection ─────────────────────────────────────────────

def generate_order_hash(user_id: int, items: list, order_date) -> str:
    """
    SHA-256 of: user_id | sorted(product_id:quantity,...) | YYYY-MM-DD
    Items is a list of OrderItemCreate (has product_id and quantity attrs).
    """
    sorted_items = sorted(items, key=lambda x: x.product_id)
    items_str = ",".join(f"{i.product_id}:{i.quantity}" for i in sorted_items)
    raw = f"{user_id}|{items_str}|{order_date}"
    return hashlib.sha256(raw.encode()).hexdigest()


def is_duplicate(db: Session, user_id: int, unique_hash: str) -> bool:
    """True if the same hash already exists for this user in the last 24 h."""
    since = datetime.utcnow() - timedelta(hours=24)
    return (
        db.query(models.Order)
        .filter(
            models.Order.user_id == user_id,
            models.Order.unique_hash == unique_hash,
            models.Order.created_at >= since,
            models.Order.archived == False,
        )
        .first()
    ) is not None


# ── Audit log ──────────────────────────────────────────────────────────────

def log_status_change(
    db: Session,
    order_id: int,
    user_id: int,
    from_status: str | None,
    to_status: str,
    notes: str | None = None,
) -> None:
    """Insert an audit entry for every status transition."""
    db.add(
        models.OrderLog(
            order_id=order_id,
            user_id=user_id,
            from_status=from_status,
            to_status=to_status,
            notes=notes,
        )
    )
