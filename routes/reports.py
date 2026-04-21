"""
Reports routes — analytics endpoints under /api/reports/.

Separated from inventory intelligence to keep the domain clean.
All endpoints are read-only.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from dependencies.auth import get_current_user, require_admin

from schemas.reports_schema import FastMovingResponse
from services.inventory_intelligence_service import get_fast_moving

router = APIRouter()


# ── Fast-Moving Medicines ────────────────────────────────

@router.get(
    "/store/{store_id}/fast-moving",
    response_model=FastMovingResponse,
    summary="Fast-moving medicines report",
)
def read_fast_moving(
    store_id: int,
    days: int = Query(
        30,
        ge=1,
        le=365,
        description="Look-back period in days from today",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query(
        "quantity",
        description="Sort field: ``quantity`` | ``revenue`` | ``orders``",
    ),
    sort_order: str = Query(
        "desc",
        description="Sort direction: ``asc`` | ``desc`` (default desc for top-N)",
    ),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Rank medicines by sales performance over the last ``days`` days. **Admin-only.**

    Returns per-medicine totals: quantity sold, revenue, order count,
    and average quantity per order.

    - **Pagination**: ``page`` + ``page_size`` (medicine-level)
    - **Sorting**: by ``quantity``, ``revenue``, or ``orders``
    - Default sort: top sellers first (desc)
    """
    require_admin(user)
    return get_fast_moving(
        db, store_id, days,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )
