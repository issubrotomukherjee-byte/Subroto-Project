"""
Pydantic schemas for reporting endpoints (/api/reports/...).

Separated from inventory_intelligence_schema to keep the reports
domain independent.  All schemas are RESPONSE-only.
"""

from pydantic import BaseModel
from typing import List
from datetime import date

from schemas.inventory_intelligence_schema import PaginationMeta


# ── Fast-Moving Medicines ────────────────────────────────

class FastMovingItem(BaseModel):
    """One medicine ranked by sales performance."""
    rank: int
    medicine_id: int
    medicine_name: str
    total_quantity_sold: int       # units sold in period
    total_revenue: float          # sum of order_item subtotals
    order_count: int              # distinct orders containing this medicine
    avg_quantity_per_order: float  # total_quantity / order_count

    class Config:
        from_attributes = True


class FastMovingResponse(BaseModel):
    """Paginated fast-moving medicines report for a store."""
    store_id: int
    days: int
    period_start: date
    period_end: date
    pagination: PaginationMeta
    items: List[FastMovingItem] = []
