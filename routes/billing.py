from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from schemas.order_schema import (
    OrderCreate,
    OrderAddItems,
    OrderResponse,
    OrderTotalResponse,
)
from services.billing_service import (
    create_order,
    add_items_to_order,
    get_order,
    get_order_total,
    list_orders,
)

router = APIRouter()


@router.get("/", response_model=List[OrderResponse])
def read_orders(db: Session = Depends(get_db)):
    """List all orders."""
    return list_orders(db)


@router.post("/", response_model=OrderResponse, status_code=201)
def place_order(data: OrderCreate, db: Session = Depends(get_db)):
    """Create a new order with items. Inventory is reduced automatically."""
    return create_order(db, data)


@router.get("/{order_id}", response_model=OrderResponse)
def read_order(order_id: int, db: Session = Depends(get_db)):
    """Get a single order with its items."""
    return get_order(db, order_id)


@router.post("/{order_id}/items", response_model=OrderResponse)
def add_items(order_id: int, data: OrderAddItems, db: Session = Depends(get_db)):
    """Add more items to an existing order. Inventory is reduced automatically."""
    return add_items_to_order(db, order_id, data)


@router.get("/{order_id}/total", response_model=OrderTotalResponse)
def read_total(order_id: int, db: Session = Depends(get_db)):
    """Get the calculated total for an order."""
    return get_order_total(db, order_id)
