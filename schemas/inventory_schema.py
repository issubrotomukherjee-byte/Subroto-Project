from pydantic import BaseModel
from datetime import date


class InventoryCreate(BaseModel):
    store_id: int
    medicine_id: int
    quantity: int
    batch_no: str
    expiry_date: date


class InventoryUpdate(BaseModel):
    quantity: int


class InventoryResponse(BaseModel):
    id: int
    store_id: int
    medicine_id: int
    quantity: int
    batch_no: str
    expiry_date: date

    class Config:
        from_attributes = True
