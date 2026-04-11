from pydantic import BaseModel, model_validator
from typing import Optional, List
from datetime import date


# ── Request schemas ──────────────────────────────────────

class OrderItemCreate(BaseModel):
    """Order item input — accepts EITHER units OR strips (not both).

    - ``units``: number of tablets/capsules directly
    - ``strips``: converted to units using medicine's units_per_strip
    - ``quantity``: legacy field, treated as strips for backward compat
    """
    medicine_id: int
    units: Optional[int] = None
    strips: Optional[int] = None
    quantity: Optional[int] = None     # backward compat → treated as units

    @model_validator(mode="after")
    def resolve_quantity(self):
        provided = sum(1 for v in [self.units, self.strips, self.quantity] if v is not None)
        if provided == 0:
            raise ValueError("Provide 'units', 'strips', or 'quantity'")
        if provided > 1:
            raise ValueError("Provide only ONE of 'units', 'strips', or 'quantity'")
        return self

    def get_units(self, units_per_strip: int) -> int:
        """Resolve the final unit count.

        - ``units`` → used directly
        - ``strips`` → strips × units_per_strip
        - ``quantity`` → treated as units (backward compat)
        """
        if self.units is not None:
            return self.units
        if self.strips is not None:
            return self.strips * units_per_strip
        # Legacy: quantity = units
        return self.quantity


class OrderCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    items: List[OrderItemCreate]


class OrderAddItems(BaseModel):
    items: List[OrderItemCreate]


class ProcessOrderRequest(BaseModel):
    """Input for the /orders/process endpoint.

    Accepts either ``units`` or ``strips`` (not both).
    Legacy ``quantity`` is treated as units.
    """
    store_id: int
    medicine_id: int
    units: Optional[int] = None
    strips: Optional[int] = None
    quantity: Optional[int] = None    # backward compat → treated as units

    @model_validator(mode="after")
    def resolve_qty(self):
        provided = sum(1 for v in [self.units, self.strips, self.quantity] if v is not None)
        if provided == 0:
            raise ValueError("Provide 'units', 'strips', or 'quantity'")
        if provided > 1:
            raise ValueError("Provide only ONE of 'units', 'strips', or 'quantity'")
        return self

    def get_units(self, units_per_strip: int) -> int:
        if self.units is not None:
            return self.units
        if self.strips is not None:
            return self.strips * units_per_strip
        return self.quantity


# ── Response schemas ─────────────────────────────────────

class OrderItemResponse(BaseModel):
    """Worker-safe order item response. No purchase_price or profit."""
    id: int
    medicine_id: int
    quantity: int              # units
    unit_price: float
    subtotal: float
    mrp: float
    discount_applied: float
    final_price: float

    class Config:
        from_attributes = True


class OrderItemAdminResponse(OrderItemResponse):
    """Admin-only order item response. Adds purchase_price and profit."""
    purchase_price: float
    profit: float


class OrderResponse(BaseModel):
    id: int
    store_id: int
    customer_id: Optional[int] = None
    total_amount: float
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderAdminResponse(BaseModel):
    """Admin-only order response with full pricing detail."""
    id: int
    store_id: int
    customer_id: Optional[int] = None
    total_amount: float
    items: List[OrderItemAdminResponse] = []

    class Config:
        from_attributes = True


class OrderTotalResponse(BaseModel):
    order_id: int
    total_amount: float
    item_count: int


# ── Process-order response schemas ───────────────────────

class BatchAllocationResponse(BaseModel):
    """Worker-safe batch allocation detail. Includes unit breakdown."""
    batch_no: str
    units: int
    strips: int
    loose_units: int
    mrp: float


class BatchAllocationAdminResponse(BatchAllocationResponse):
    """Admin-only batch allocation detail. Adds sensitive pricing."""
    batch_id: int
    expiry_date: date
    purchase_price: float
    profit: float


class ProcessOrderResponse(BaseModel):
    """Worker-safe response from /orders/process."""
    medicine_id: int
    total_units: int
    total_strips: int
    total_loose_units: int
    total_price: float
    allocations: List[BatchAllocationResponse]


class ProcessOrderAdminResponse(BaseModel):
    """Admin-only response from /orders/process. Full pricing detail."""
    medicine_id: int
    total_units: int
    total_strips: int
    total_loose_units: int
    total_price: float
    total_cost: float
    total_profit: float
    allocations: List[BatchAllocationAdminResponse]
