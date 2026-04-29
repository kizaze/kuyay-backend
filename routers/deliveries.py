from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from routers.auth import require_owner
import models
import schemas

router = APIRouter()


@router.get("/", response_model=List[schemas.DeliveryResponse])
def list_deliveries(
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    return (
        db.query(models.Delivery)
        .order_by(models.Delivery.delivery_date.desc())
        .all()
    )


@router.post("/", response_model=schemas.DeliveryResponse)
def create_delivery(
    data: schemas.DeliveryCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    delivery = models.Delivery(
        trip_name=data.trip_name,
        delivery_date=data.delivery_date,
        zone=data.zone,
        notes=data.notes,
    )
    db.add(delivery)
    db.flush()

    for order_id in data.order_ids:
        order = db.query(models.Order).filter(models.Order.id == order_id).first()
        if order:
            delivery.orders.append(order)

    db.commit()
    db.refresh(delivery)
    return delivery


@router.put("/{delivery_id}", response_model=schemas.DeliveryResponse)
def update_delivery(
    delivery_id: int,
    data: schemas.DeliveryUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    delivery = db.query(models.Delivery).filter(
        models.Delivery.id == delivery_id
    ).first()
    if not delivery:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    update_data = data.model_dump(exclude_none=True)
    order_ids = update_data.pop("order_ids", None)

    for field, value in update_data.items():
        setattr(delivery, field, value)

    if order_ids is not None:
        delivery.orders = []
        for oid in order_ids:
            order = db.query(models.Order).filter(models.Order.id == oid).first()
            if order:
                delivery.orders.append(order)

    db.commit()
    db.refresh(delivery)
    return delivery
