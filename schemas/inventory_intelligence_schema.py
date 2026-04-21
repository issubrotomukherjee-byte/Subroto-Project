"""
Pydantic schemas for Inventory Intelligence endpoints.

All schemas are RESPONSE-only — these endpoints are read-only analytics
built on top of existing Inventory, Medicine, Order, and OrderItem data.
"""

from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime


# ── Dashboard ────────────────────────────────────────────

class StockDashboardResponse(BaseModel):
    """Real-time store-level stock summary."""
    store_id: int
    total_medicines: int          # distinct medicine count
    total_batches: int            # total inventory rows
    total_units: int              # sum of quantity_units
    total_mrp_value: float        # sum(mrp × quantity_units)
    low_stock_count: int          # batches below threshold
    expiring_soon_count: int      # batches expiring within N days
    expired_count: int            # batches already expired


# ── Low-Stock Alerts ─────────────────────────────────────

class LowStockItem(BaseModel):
    medicine_id: int
    medicine_name: str
    batch_no: str
    quantity_units: int
    units_per_strip: Optional[int] = None
    expiry_date: date
    mrp: float

    class Config:
        from_attributes = True


class LowStockResponse(BaseModel):
    store_id: int
    threshold_units: int
    count: int
    items: List[LowStockItem] = []


# ── Expiry Alerts ────────────────────────────────────────

class ExpiryAlertItem(BaseModel):
    medicine_id: int
    medicine_name: str
    batch_no: str
    expiry_date: date
    quantity_units: int
    days_remaining: int           # negative if already expired
    status: str                   # "expired" | "expiring_soon"

    class Config:
        from_attributes = True


class ExpiryAlertResponse(BaseModel):
    store_id: int
    warning_days: int
    expired_count: int
    expiring_soon_count: int
    items: List[ExpiryAlertItem] = []


# ── Stock Valuation (admin-only) ─────────────────────────

class ValuationItem(BaseModel):
    medicine_id: int
    medicine_name: str
    total_units: int
    mrp_value: float              # sum(mrp × units) for this medicine
    cost_value: float             # sum(purchase_price × units)
    potential_profit: float       # mrp_value - cost_value

    class Config:
        from_attributes = True


class ValuationResponse(BaseModel):
    store_id: int
    total_mrp_value: float
    total_cost_value: float
    total_potential_profit: float
    item_count: int
    items: List[ValuationItem] = []


# ── Dead Stock (admin-only) ──────────────────────────────

class DeadStockItem(BaseModel):
    medicine_id: int
    medicine_name: str
    total_units_in_stock: int
    batch_count: int
    last_sold_at: Optional[datetime] = None
    days_since_last_sale: Optional[int] = None  # None if never sold

    class Config:
        from_attributes = True


class DeadStockResponse(BaseModel):
    store_id: int
    threshold_days: int
    count: int
    items: List[DeadStockItem] = []


# ── Pagination Metadata ─────────────────────────────────

class PaginationMeta(BaseModel):
    """Reusable pagination metadata attached to paginated responses."""
    page: int
    page_size: int
    total_items: int
    total_pages: int


# ── Inventory Search ─────────────────────────────────────

class InventoryBatchDetail(BaseModel):
    """Single batch row within a medicine's inventory."""
    inventory_id: int
    batch_no: str
    quantity_units: int
    units_per_strip: Optional[int] = None
    expiry_date: date
    days_until_expiry: int
    mrp: float
    rack_location: Optional[str] = None   # reserved for future model field

    class Config:
        from_attributes = True


class InventorySearchItem(BaseModel):
    """One medicine with aggregated stock and batch-level breakdown."""
    medicine_id: int
    medicine_name: str
    total_stock: int              # sum of quantity_units across batches
    reserved_stock: int           # 0 until reservation system exists
    available_stock: int          # total_stock − reserved_stock
    nearest_expiry: Optional[date] = None
    batch_count: int
    batches: List[InventoryBatchDetail] = []

    class Config:
        from_attributes = True


class InventorySearchResponse(BaseModel):
    """Paginated medicine search within a store's inventory."""
    store_id: int
    query: str
    pagination: PaginationMeta
    items: List[InventorySearchItem] = []


# ── Near-Expiry (paginated) ──────────────────────────────

class NearExpiryItem(BaseModel):
    """Single batch expiring within the threshold window."""
    medicine_id: int
    medicine_name: str
    batch_no: str
    expiry_date: date
    days_until_expiry: int
    quantity_units: int
    units_per_strip: Optional[int] = None
    mrp: float
    stock_value: float            # mrp × quantity_units

    class Config:
        from_attributes = True


class NearExpiryResponse(BaseModel):
    """Paginated near-expiry report for a store."""
    store_id: int
    days_threshold: int
    total_at_risk_value: float
    total_at_risk_units: int
    pagination: PaginationMeta
    items: List[NearExpiryItem] = []
