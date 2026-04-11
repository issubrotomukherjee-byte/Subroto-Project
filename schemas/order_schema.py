from pydantic import BaseModel
from typing import Optional, List


# --- Request schemas ---

class OrderItemCreate(BaseModel):
    medicine_id: int
    quantity: int


class OrderCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    items: List[OrderItemCreate]


class OrderAddItems(BaseModel):
    items: List[OrderItemCreate]


# --- Response schemas ---

class OrderItemResponse(BaseModel):
    id: int
    medicine_id: int
    quantity: int
    unit_price: float
    subtotal: float

    class Config:
        from_attributes = True


class OrderResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int] = None
    total_amount: float
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderTotalResponse(BaseModel):
    order_id: int
    total_amount: float
    item_count: int
