from pydantic import BaseModel
from datetime import date
from typing import Optional


class InventoryCreate(BaseModel):
    store_id: int
    medicine_id: int
    quantity: int
    batch_no: str
    expiry_date: date
    mrp: float
    purchase_price: float


class InventoryUpdate(BaseModel):
    quantity: int


class InventoryResponse(BaseModel):
    """Standard response — visible to all roles (worker + admin)."""
    id: int
    store_id: int
    medicine_id: int
    quantity: int
    batch_no: str
    expiry_date: date
    mrp: float

    class Config:
        from_attributes = True


class InventoryAdminResponse(InventoryResponse):
    """Extended response — only returned to admin users.
    Includes purchase_price which must never be exposed to workers.
    """
    purchase_price: float
