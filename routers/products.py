from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from routers.auth import get_current_user, require_owner
import models
import schemas

router = APIRouter()


@router.get("/", response_model=List[schemas.ProductResponse])
def list_products(db: Session = Depends(get_db)):
    return db.query(models.Product).filter(models.Product.active == True).all()


@router.get("/{product_id}", response_model=schemas.ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return product


@router.post("/", response_model=schemas.ProductResponse)
def create_product(
    data: schemas.ProductCreate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    product = models.Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=schemas.ProductResponse)
def update_product(
    product_id: int,
    data: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}")
def deactivate_product(
    product_id: int,
    db: Session = Depends(get_db),
    _: models.User = Depends(require_owner),
):
    product = db.query(models.Product).filter(models.Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    product.active = False
    db.commit()
    return {"message": "Producto desactivado"}
