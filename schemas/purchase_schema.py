"""
Pydantic schemas for the Purchase Entry system.

Request schemas validate purchase input.
Response schemas provide full invoice detail with stock linkage.

NOTE: ``units_per_strip`` is always read from the Medicine model
      and is NOT accepted as input.
"""

from pydantic import BaseModel, field_validator, model_validator
from typing import Optional, List
from datetime import date, datetime

from schemas.inventory_intelligence_schema import PaginationMeta


# ── Request Schemas ──────────────────────────────────────

class PurchaseItemCreate(BaseModel):
    """Single line item on a purchase invoice.

    ``quantity`` is in strips.  ``units_per_strip`` is read from the
    Medicine model at processing time — never hardcoded or user-supplied.
    """
    medicine_id: int
    batch_no: str
    expiry_date: date
    quantity: int                          # strips
    purchase_price: float                  # per-unit cost
    mrp: float                             # per-unit selling price

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v):
        if v <= 0:
            raise ValueError("quantity must be a positive integer")
        return v

    @field_validator("expiry_date")
    @classmethod
    def expiry_in_future(cls, v):
        if v <= date.today():
            raise ValueError("expiry_date must be a future date")
        return v

    @field_validator("purchase_price", "mrp")
    @classmethod
    def price_positive(cls, v):
        if v <= 0:
            raise ValueError("price must be positive")
        return v

    @model_validator(mode="after")
    def purchase_price_must_not_exceed_mrp(self):
        if self.purchase_price > self.mrp:
            raise ValueError(
                f"purchase_price ({self.purchase_price}) cannot exceed "
                f"mrp ({self.mrp})"
            )
        return self


class PurchaseCreate(BaseModel):
    """POST /api/purchase body — full purchase invoice."""
    store_id: int
    supplier_name: str
    invoice_number: str
    invoice_date: Optional[date] = None    # defaults to today
    items: List[PurchaseItemCreate]

    @field_validator("supplier_name")
    @classmethod
    def supplier_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("supplier_name is required")
        return v.strip()

    @field_validator("invoice_number")
    @classmethod
    def invoice_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("invoice_number is required")
        return v.strip()

    @field_validator("items")
    @classmethod
    def at_least_one_item(cls, v):
        if not v:
            raise ValueError("At least one item is required")
        return v


# ── Response Schemas ─────────────────────────────────────

class PurchaseItemResponse(BaseModel):
    """Line item in a purchase response."""
    id: int
    medicine_id: int
    medicine_name: str
    inventory_id: Optional[int] = None
    batch_no: str
    expiry_date: date
    quantity: int                   # strips
    units_per_strip: int
    quantity_units: int             # total units (quantity × ups)
    purchase_price: float
    mrp: float
    line_total: float

    class Config:
        from_attributes = True


class PurchaseResponse(BaseModel):
    """Full purchase invoice response."""
    id: int
    store_id: int
    supplier_name: str
    invoice_number: str
    invoice_date: Optional[date] = None
    total_items: int
    total_quantity: int             # total units
    total_amount: float
    created_at: Optional[datetime] = None
    items: List[PurchaseItemResponse] = []

    class Config:
        from_attributes = True


class PurchaseListItem(BaseModel):
    """Compact purchase summary for list views."""
    id: int
    store_id: int
    supplier_name: str
    invoice_number: str
    invoice_date: Optional[date] = None
    total_items: int
    total_quantity: int
    total_amount: float
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PurchaseListResponse(BaseModel):
    """Paginated purchase list."""
    store_id: Optional[int] = None
    pagination: PaginationMeta
    items: List[PurchaseListItem] = []


# ── Supplier Intelligence Schemas ────────────────────────

class SupplierSummaryItem(BaseModel):
    """Aggregated stats for a single supplier."""
    supplier_name: str
    total_purchase_value: float
    total_invoices: int
    avg_invoice_value: float
    last_purchase_date: Optional[datetime] = None


class SupplierSummaryResponse(BaseModel):
    """Paginated supplier summary list."""
    store_id: Optional[int] = None
    pagination: PaginationMeta
    items: List[SupplierSummaryItem] = []


class TopSupplierItem(BaseModel):
    """Ranked supplier by total purchase value."""
    rank: int
    supplier_name: str
    total_purchase_value: float
    total_invoices: int


class TopSuppliersResponse(BaseModel):
    """Top N suppliers by total purchase value."""
    store_id: Optional[int] = None
    limit: int
    items: List[TopSupplierItem] = []


# ── Price History Schemas ────────────────────────────────

class PriceHistoryItem(BaseModel):
    """Single purchase record for a medicine."""
    supplier_name: str
    purchase_price: float
    mrp: float
    quantity: int                   # strips
    quantity_units: int             # total units
    purchase_date: Optional[datetime] = None


class PriceHistoryResponse(BaseModel):
    """Price history for a specific medicine across all purchases."""
    medicine_id: int
    medicine_name: str
    last_purchase_price: Optional[float] = None
    avg_purchase_price: Optional[float] = None
    store_id: Optional[int] = None
    pagination: PaginationMeta
    items: List[PriceHistoryItem] = []


# ── Smart Supplier Schema ────────────────────────────────

class SmartSupplierResponse(BaseModel):
    """Smart supplier analysis for a specific medicine."""
    medicine_id: int
    medicine_name: str
    store_id: Optional[int] = None
    last_purchase_price: float
    avg_price: float
    best_supplier: str
    best_price: float
    price_trend: str                       # "increasing" | "decreasing" | "stable"
    savings_per_unit: float
    recommendation: str

