from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# --- Request schemas ---

class CustomerCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None


# --- Response schemas ---

class CustomerResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True


# --- History responses ---

class OrderItemDetail(BaseModel):
    medicine_id: int
    medicine_name: str
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


class OrderHistoryItem(BaseModel):
    order_id: int
    store_id: int
    total_amount: float
    created_at: Optional[datetime] = None
    items: List[OrderItemDetail] = []

    class Config:
        from_attributes = True


class CustomerOrderHistoryResponse(BaseModel):
    customer_id: int
    customer_name: str
    orders: List[OrderHistoryItem] = []


class MedicineHistoryItem(BaseModel):
    medicine_id: int
    medicine_name: str
    total_quantity: int
    total_spent: float


class CustomerMedicineHistoryResponse(BaseModel):
    customer_id: int
    customer_name: str
    medicines: List[MedicineHistoryItem] = []
