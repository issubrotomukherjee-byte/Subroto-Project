from pydantic import BaseModel
from typing import Optional, List
from datetime import date


# ── Request schemas ──────────────────────────────────────

class OrderItemCreate(BaseModel):
    medicine_id: int
    quantity: int


class OrderCreate(BaseModel):
    store_id: int
    customer_id: Optional[int] = None
    items: List[OrderItemCreate]


class OrderAddItems(BaseModel):
    items: List[OrderItemCreate]


class ProcessOrderRequest(BaseModel):
    """Input for the lightweight /orders/process endpoint."""
    store_id: int
    medicine_id: int
    quantity: int


# ── Response schemas ─────────────────────────────────────

class OrderItemResponse(BaseModel):
    """Worker-safe order item response. No purchase_price or profit."""
    id: int
    medicine_id: int
    quantity: int
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
    """Worker-safe batch allocation detail."""
    batch_no: str
    quantity: int
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
    total_quantity: int
    total_price: float
    allocations: List[BatchAllocationResponse]


class ProcessOrderAdminResponse(BaseModel):
    """Admin-only response from /orders/process. Full pricing detail."""
    medicine_id: int
    total_quantity: int
    total_price: float
    total_cost: float
    total_profit: float
    allocations: List[BatchAllocationAdminResponse]
