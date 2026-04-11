from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from schemas.customer_schema import (
    CustomerCreate,
    CustomerResponse,
    CustomerOrderHistoryResponse,
    CustomerMedicineHistoryResponse,
)
from services.customer_service import (
    create_customer,
    list_customers,
    get_customer,
    get_customer_orders,
    get_customer_medicines,
)

router = APIRouter()


@router.get("/", response_model=List[CustomerResponse])
def read_all(db: Session = Depends(get_db)):
    """List all customers."""
    return list_customers(db)


@router.post("/", response_model=CustomerResponse, status_code=201)
def create(data: CustomerCreate, db: Session = Depends(get_db)):
    """Create a new customer."""
    return create_customer(db, data)


@router.get("/{customer_id}", response_model=CustomerResponse)
def read_one(customer_id: int, db: Session = Depends(get_db)):
    """Get a single customer by ID."""
    return get_customer(db, customer_id)


@router.get("/{customer_id}/orders", response_model=CustomerOrderHistoryResponse)
def read_orders(customer_id: int, db: Session = Depends(get_db)):
    """Get all orders for a customer (purchase history)."""
    return get_customer_orders(db, customer_id)


@router.get("/{customer_id}/medicines", response_model=CustomerMedicineHistoryResponse)
def read_medicines(customer_id: int, db: Session = Depends(get_db)):
    """Get all medicines purchased by a customer (medicine history)."""
    return get_customer_medicines(db, customer_id)
