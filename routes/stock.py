from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from dependencies.auth import get_current_user
from schemas.inventory_schema import (
    InventoryCreate,
    InventoryUpdate,
    InventoryResponse,
    InventoryAdminResponse,
)
from services.stock_service import add_stock, get_stock_by_medicine, update_stock

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def create_stock(data: InventoryCreate, db: Session = Depends(get_db)):
    """Add stock for a store-medicine pair."""
    return add_stock(db, data)


@router.get("/medicine/{medicine_id}")
def read_stock_by_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get stock entries for a given medicine across all stores.

    - **Admin**: response includes ``purchase_price``
    - **Worker**: response excludes ``purchase_price``
    """
    records = get_stock_by_medicine(db, medicine_id)

    if user["role"] == "admin":
        return [InventoryAdminResponse.model_validate(r) for r in records]
    return [InventoryResponse.model_validate(r) for r in records]


@router.put("/{inventory_id}", response_model=InventoryResponse)
def modify_stock(inventory_id: int, data: InventoryUpdate, db: Session = Depends(get_db)):
    """Update quantity of an existing stock entry."""
    return update_stock(db, inventory_id, data)
