from pydantic import BaseModel, model_validator, field_validator
from typing import Optional, List
from datetime import date, datetime


# ── Request schemas ──────────────────────────────────────

class OrderItemCreate(BaseModel):
    """Order item input — accepts EITHER units OR strips (not both).

    - ``units``: number of tablets/capsules directly
    - ``strips``: converted to units using medicine's units_per_strip
    - ``quantity``: legacy field, treated as units for backward compat
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
        """Resolve the final unit count."""
        if self.units is not None:
            return self.units
        if self.strips is not None:
            return self.strips * units_per_strip
        return self.quantity


class OrderCreate(BaseModel):
    """Production-grade order placement request.

    - ``customer_phone``: auto-finds or creates customer
    - ``payment_method``: ``"cash"`` or ``"upi"``
    - ``redeem_loyalty_points``: points to redeem (capped by settings)
    - Discount is applied automatically from admin-configured settings
    """
    store_id: int
    customer_phone: Optional[str] = None
    payment_method: str = "cash"
    redeem_loyalty_points: Optional[int] = None
    items: List[OrderItemCreate]

    @field_validator("payment_method")
    @classmethod
    def validate_payment_method(cls, v):
        v = v.lower().strip()
        if v not in ("cash", "upi"):
            raise ValueError("payment_method must be 'cash' or 'upi'")
        return v

    @field_validator("redeem_loyalty_points")
    @classmethod
    def validate_redeem(cls, v):
        if v is not None and v < 0:
            raise ValueError("redeem_loyalty_points must be >= 0")
        return v


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
    payment_method: Optional[str] = None
    subtotal: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    loyalty_points_redeemed: Optional[int] = None
    loyalty_discount: Optional[float] = None
    net_amount: Optional[float] = None
    total_amount: float
    loyalty_points_earned: Optional[int] = None
    items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderAdminResponse(BaseModel):
    """Admin-only order response with full pricing detail."""
    id: int
    store_id: int
    customer_id: Optional[int] = None
    payment_method: Optional[str] = None
    subtotal: Optional[float] = None
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    loyalty_points_redeemed: Optional[int] = None
    loyalty_discount: Optional[float] = None
    net_amount: Optional[float] = None
    total_amount: float
    loyalty_points_earned: Optional[int] = None
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


# ── Invoice response ────────────────────────────────────

class InvoiceItemResponse(BaseModel):
    medicine_name: str
    quantity: int            # units
    unit_price: float        # MRP per unit
    subtotal: float          # MRP × qty

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    """Printable invoice JSON for GET /api/orders/{id}/invoice."""
    order_id: int
    store_name: str
    store_address: Optional[str] = None
    store_phone: Optional[str] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    payment_method: str

    items: List[InvoiceItemResponse]

    subtotal: float
    discount_percent: float
    discount_amount: float
    loyalty_points_redeemed: int
    loyalty_discount: float
    net_amount: float
    loyalty_points_earned: int

    created_at: Optional[datetime] = None
