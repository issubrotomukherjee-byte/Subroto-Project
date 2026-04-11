from pydantic import BaseModel
from typing import Optional


class MedicineCreate(BaseModel):
    name: str
    salt: Optional[str] = None
    price: float


class MedicineResponse(BaseModel):
    id: int
    name: str
    salt: Optional[str] = None
    price: float

    class Config:
        from_attributes = True
