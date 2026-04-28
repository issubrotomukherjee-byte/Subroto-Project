from pydantic import BaseModel
from typing import Optional, List


class MedicineCreate(BaseModel):
    name: str
    salt: Optional[str] = None
    price: float
    units_per_strip: int = 10
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    hsn_code: Optional[str] = None
    schedule_type: Optional[str] = None
    is_active: bool = True


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
    brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    dosage_form: Optional[str] = None
    strength: Optional[str] = None
    hsn_code: Optional[str] = None
    schedule_type: Optional[str] = None
    is_active: Optional[bool] = True

    class Config:
        from_attributes = True


class MedicineResolveResponse(BaseModel):
    """Response for /resolve — name-to-id conversion for autocomplete."""
    id: int
    name: str
    brand_name: Optional[str] = None
    strength: Optional[str] = None

    class Config:
        from_attributes = True


class MedicineSubstituteResponse(BaseModel):
    """Response for /substitutes — alternate medicines with price comparison."""
    id: int
    name: str
    brand_name: Optional[str] = None
    strength: Optional[str] = None
    price: Optional[float] = None
    price_difference_percent: Optional[int] = None
    price_label: Optional[str] = None

    class Config:
        from_attributes = True


class MedicineDetailsComposition(BaseModel):
    """Composition entry for details response."""
    salt: str
    strength: Optional[str] = None


class MedicineDetailsResponse(BaseModel):
    """Full medicine details — unified response for frontend."""
    id: int
    name: str
    brand_name: Optional[str] = None
    strength: Optional[str] = None
    price: Optional[float] = None
    composition: List[MedicineDetailsComposition] = []
    substitutes: List[MedicineSubstituteResponse] = []

    class Config:
        from_attributes = True
