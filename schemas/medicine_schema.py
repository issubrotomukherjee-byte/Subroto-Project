from pydantic import BaseModel
from typing import Optional


class MedicineCreate(BaseModel):
    name: str
    salt: Optional[str] = None
    price: float
    units_per_strip: int = 10


class MedicineSearchResponse(BaseModel):
    """Lightweight response for search/autocomplete — only id + name."""
    id: int
    name: str

    class Config:
        from_attributes = True


class MedicineResponse(BaseModel):
    id: int
    name: str
    salt: Optional[str] = None
    price: float
    units_per_strip: int

    class Config:
        from_attributes = True
