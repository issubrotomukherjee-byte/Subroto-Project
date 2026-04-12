from pydantic import BaseModel, model_validator
from datetime import date
from typing import Optional


class InventoryCreate(BaseModel):
    """Accept inventory in strips. Backend converts to units internally.

    Frontend sends ``medicine_name`` instead of ``medicine_id``.
    Backend auto-resolves or creates the medicine record.
    Requires ``units_per_strip`` so each batch can have its own strip size.
    """
    medicine_name: str
    store_id: int
    quantity: int                     # strips
    units_per_strip: int = 10         # units per strip for this batch
    batch_no: str
    expiry_date: date
    mrp: float
    purchase_price: float


class InventoryUpdate(BaseModel):
    """Update stock. Accepts either units or strips (not both).

    If ``strips`` is provided, it's converted to units using the batch's
    units_per_strip.  If ``quantity_units`` is provided, it's used directly.
    Legacy ``quantity`` (strips) is also accepted for backward compat.
    """
    quantity: Optional[int] = None          # strips (legacy / backward compat)
    quantity_units: Optional[int] = None    # units (preferred)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.quantity is None and self.quantity_units is None:
            raise ValueError("Provide either 'quantity' (strips) or 'quantity_units' (units)")
        return self


class InventoryResponse(BaseModel):
    """Standard response — visible to all roles (worker + admin).

    Returns both strips and unit breakdowns for UI flexibility.
    """
    id: int
    store_id: int
    medicine_id: int
    quantity: int                 # strips (deprecated but present)
    quantity_units: Optional[int] = None
    units_per_strip: Optional[int] = None
    batch_no: str
    expiry_date: date
    mrp: float
    # Computed display fields
    strips: Optional[int] = None
    loose_units: Optional[int] = None

    class Config:
        from_attributes = True


class InventoryAdminResponse(InventoryResponse):
    """Extended response — only returned to admin users.
    Includes purchase_price which must never be exposed to workers.
    """
    purchase_price: float
