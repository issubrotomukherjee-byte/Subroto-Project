"""
Pydantic schemas for the Inventory Adjustment endpoint.

Request schema validates input; response schemas provide full
audit detail and adjustment history views.
"""

from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

from schemas.inventory_intelligence_schema import PaginationMeta


# ── Request ──────────────────────────────────────────────

class InventoryAdjustRequest(BaseModel):
    """POST /api/inventory/adjust body.

    Identifies the batch by ``store_id`` + ``medicine_id`` + ``batch_no``
    (matching the Inventory table's unique constraint).
    """
    store_id: int
    medicine_id: int
    batch_no: str
    adjustment_type: str          # "increase" | "decrease"
    quantity: int                  # must be positive
    reason: str                    # required — why the adjustment is being made

    @field_validator("adjustment_type")
    @classmethod
    def validate_adjustment_type(cls, v):
        v = v.lower().strip()
        if v not in ("increase", "decrease"):
            raise ValueError("adjustment_type must be 'increase' or 'decrease'")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("quantity must be a positive integer")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v):
        if not v or not v.strip():
            raise ValueError("reason is required and cannot be empty")
        return v.strip()


# ── Response ─────────────────────────────────────────────

class InventoryAdjustResponse(BaseModel):
    """Returned after a successful adjustment — full audit snapshot."""
    adjustment_id: int
    inventory_id: int
    store_id: int
    medicine_id: int
    medicine_name: str
    batch_no: str
    adjustment_type: str
    quantity_adjusted: int
    quantity_before: int
    quantity_after: int
    units_per_strip: Optional[int] = None
    strips_after: int              # computed: quantity_after // units_per_strip
    loose_units_after: int         # computed: quantity_after % units_per_strip
    reason: str
    adjusted_by: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Adjustment History ───────────────────────────────────

class AdjustmentLogItem(BaseModel):
    """Single row from the adjustment audit log."""
    id: int
    inventory_id: int
    store_id: int
    medicine_id: int
    batch_no: str
    adjustment_type: str
    quantity: int
    quantity_before: int
    quantity_after: int
    reason: str
    adjusted_by: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdjustmentLogResponse(BaseModel):
    """Paginated adjustment history for a store."""
    store_id: int
    pagination: PaginationMeta
    items: List[AdjustmentLogItem] = []
