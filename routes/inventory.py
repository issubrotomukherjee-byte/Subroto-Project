from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from schemas.inventory_schema import InventoryCreate, InventoryUpdate, InventoryResponse
from services.inventory_service import create_inventory, get_inventory_by_medicine, update_inventory

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def add_inventory(data: InventoryCreate, db: Session = Depends(get_db)):
    """Add stock for a store-medicine-batch combo."""
    return create_inventory(db, data)


@router.get("/medicine/{medicine_id}", response_model=List[InventoryResponse])
def read_inventory_by_medicine(medicine_id: int, db: Session = Depends(get_db)):
    """Get stock entries for a given medicine across all stores (sorted by expiry)."""
    return get_inventory_by_medicine(db, medicine_id)


@router.put("/{inventory_id}", response_model=InventoryResponse)
def modify_inventory(inventory_id: int, data: InventoryUpdate, db: Session = Depends(get_db)):
    """Update quantity of an existing stock entry."""
    return update_inventory(db, inventory_id, data)
