from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from routers.auth import get_current_user, require_owner
import models
import schemas

router = APIRouter()


@router.get("/{order_id}", response_model=schemas.PaymentResponse)
def get_payment(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    payment = db.query(models.Payment).filter(
        models.Payment.order_id == order_id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    return payment


@router.put("/{order_id}", response_model=schemas.PaymentResponse)
def update_payment(
    order_id: int,
    data: schemas.PaymentUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    payment = db.query(models.Payment).filter(
        models.Payment.order_id == order_id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Pago no encontrado")
    payment.status = data.status
    if data.reference:
        payment.reference = data.reference
    db.commit()
    db.refresh(payment)
    return payment
