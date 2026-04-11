from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from schemas.inventory_schema import InventoryCreate, InventoryUpdate, InventoryResponse
from services.stock_service import add_stock, get_stock_by_medicine, update_stock

router = APIRouter()


@router.post("/", response_model=InventoryResponse, status_code=201)
def create_stock(data: InventoryCreate, db: Session = Depends(get_db)):
    """Add stock for a store-medicine pair."""
    return add_stock(db, data)


@router.get("/medicine/{medicine_id}", response_model=List[InventoryResponse])
def read_stock_by_medicine(medicine_id: int, db: Session = Depends(get_db)):
    """Get stock entries for a given medicine across all stores."""
    return get_stock_by_medicine(db, medicine_id)


@router.put("/{inventory_id}", response_model=InventoryResponse)
def modify_stock(inventory_id: int, data: InventoryUpdate, db: Session = Depends(get_db)):
    """Update quantity of an existing stock entry."""
    return update_stock(db, inventory_id, data)
