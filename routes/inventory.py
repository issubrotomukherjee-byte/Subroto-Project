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
from services.inventory_service import create_inventory, get_inventory_by_medicine, update_inventory

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def add_inventory(data: InventoryCreate, db: Session = Depends(get_db)):
    """Add stock for a store-medicine-batch combo."""
    return create_inventory(db, data)


@router.get("/medicine/{medicine_id}")
def read_inventory_by_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get stock entries for a given medicine across all stores (sorted by expiry).

    - **Admin**: response includes ``purchase_price``
    - **Worker**: response excludes ``purchase_price``
    """
    records = get_inventory_by_medicine(db, medicine_id)

    if user["role"] == "admin":
        return [InventoryAdminResponse.model_validate(r) for r in records]
    return [InventoryResponse.model_validate(r) for r in records]


@router.put("/{inventory_id}", response_model=InventoryResponse)
def modify_inventory(inventory_id: int, data: InventoryUpdate, db: Session = Depends(get_db)):
    """Update quantity of an existing stock entry."""
    return update_inventory(db, inventory_id, data)
