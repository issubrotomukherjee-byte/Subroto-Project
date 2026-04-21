"""
Inventory Intelligence routes — read-only analytics endpoints.

All endpoints query existing data.  No writes occur.
Valuation and Dead Stock are admin-only (expose purchase_price / profit data).
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database.connection import get_db
from dependencies.auth import get_current_user, require_admin

from schemas.inventory_intelligence_schema import (
    StockDashboardResponse,
    LowStockResponse,
    ExpiryAlertResponse,
    ValuationResponse,
    DeadStockResponse,
    InventorySearchResponse,
    NearExpiryResponse,
)
from services.inventory_intelligence_service import (
    get_store_dashboard,
    get_low_stock,
    get_expiry_alerts,
    get_stock_valuation,
    get_dead_stock,
    search_inventory,
    get_near_expiry,
    DEFAULT_LOW_STOCK_THRESHOLD,
    DEFAULT_EXPIRY_WARNING_DAYS,
    DEFAULT_DEAD_STOCK_DAYS,
)

router = APIRouter()


# ── Dashboard ────────────────────────────────────────────

@router.get(
    "/store/{store_id}/dashboard",
    response_model=StockDashboardResponse,
    summary="Store stock dashboard",
)
def read_dashboard(
    store_id: int,
    low_stock_threshold: int = Query(
        DEFAULT_LOW_STOCK_THRESHOLD,
        ge=1,
        description="Units below which a batch is considered low-stock",
    ),
    expiry_warning_days: int = Query(
        DEFAULT_EXPIRY_WARNING_DAYS,
        ge=1,
        description="Days until expiry to flag as expiring-soon",
    ),
    db: Session = Depends(get_db),
):
    """Real-time stock summary for a store.

    Returns counts of total medicines, batches, units, MRP value,
    and counts of low-stock / expiring / expired batches.
    Thresholds are configurable via query params.
    """
    return get_store_dashboard(db, store_id, low_stock_threshold, expiry_warning_days)


# ── Low-Stock Alerts ─────────────────────────────────────

@router.get(
    "/store/{store_id}/low-stock",
    response_model=LowStockResponse,
    summary="Low-stock alerts",
)
def read_low_stock(
    store_id: int,
    threshold: int = Query(
        DEFAULT_LOW_STOCK_THRESHOLD,
        ge=1,
        description="Units below which a batch is flagged",
    ),
    db: Session = Depends(get_db),
):
    """List all batches in a store whose unit count is below the threshold.

    Sorted by quantity ascending (most critical first).
    """
    return get_low_stock(db, store_id, threshold)


# ── Expiry Alerts ────────────────────────────────────────

@router.get(
    "/store/{store_id}/expiry-alerts",
    response_model=ExpiryAlertResponse,
    summary="Expiry alerts",
)
def read_expiry_alerts(
    store_id: int,
    warning_days: int = Query(
        DEFAULT_EXPIRY_WARNING_DAYS,
        ge=1,
        description="Days until expiry to include in alerts",
    ),
    db: Session = Depends(get_db),
):
    """List expired and near-expiry batches for a store.

    Each item includes ``days_remaining`` (negative if already expired)
    and ``status`` (``"expired"`` or ``"expiring_soon"``).
    Sorted by expiry date ascending (most urgent first).
    """
    return get_expiry_alerts(db, store_id, warning_days)


# ── Stock Valuation (admin-only) ─────────────────────────

@router.get(
    "/store/{store_id}/valuation",
    response_model=ValuationResponse,
    summary="Stock valuation report",
)
def read_valuation(
    store_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """MRP vs cost valuation grouped by medicine. **Admin-only.**

    Returns per-medicine totals and overall store totals for:
    MRP value, cost value, and potential profit.
    """
    require_admin(user)
    return get_stock_valuation(db, store_id)


# ── Dead Stock (admin-only) ──────────────────────────────

@router.get(
    "/store/{store_id}/dead-stock",
    response_model=DeadStockResponse,
    summary="Dead stock detection",
)
def read_dead_stock(
    store_id: int,
    threshold_days: int = Query(
        DEFAULT_DEAD_STOCK_DAYS,
        ge=1,
        description="Days without a sale to consider as dead stock",
    ),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Identify medicines in stock that haven't been sold recently. **Admin-only.**

    A medicine is flagged if it has no sales in the store within
    ``threshold_days``, or if it has never been sold at all.
    """
    require_admin(user)
    return get_dead_stock(db, store_id, threshold_days)


# ── Inventory Search ─────────────────────────────────────

@router.get(
    "/store/{store_id}/search",
    response_model=InventorySearchResponse,
    summary="Search store inventory",
)
def search_store_inventory(
    store_id: int,
    q: str = Query(
        "",
        description="Medicine name to search (case-insensitive partial match). Empty = all.",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query(
        "name",
        description="Sort field: ``name`` | ``stock`` | ``expiry``",
    ),
    sort_order: str = Query(
        "asc",
        description="Sort direction: ``asc`` | ``desc``",
    ),
    db: Session = Depends(get_db),
):
    """Search medicines within a store's inventory.

    Returns per-medicine aggregates (total / reserved / available stock)
    and batch-level detail (quantities, expiry dates, rack location)
    sorted by nearest expiry within each medicine.

    - **Pagination**: ``page`` + ``page_size`` (medicine-level)
    - **Sorting**: by ``name``, ``stock``, or ``expiry`` (nearest)
    """
    return search_inventory(
        db, store_id, q,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )


# ── Near-Expiry (paginated) ─────────────────────────────

@router.get(
    "/store/{store_id}/near-expiry",
    response_model=NearExpiryResponse,
    summary="Near-expiry stock report",
)
def read_near_expiry(
    store_id: int,
    days: int = Query(
        90,
        ge=1,
        description="Include batches expiring within this many days from today",
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    sort_by: str = Query(
        "expiry",
        description="Sort field: ``expiry`` | ``quantity`` | ``value`` | ``name``",
    ),
    sort_order: str = Query(
        "asc",
        description="Sort direction: ``asc`` | ``desc``",
    ),
    db: Session = Depends(get_db),
):
    """List batches expiring within ``days`` from today, with pagination.

    Forward-looking only (no already-expired items).
    Includes per-item ``stock_value`` (MRP × units) and aggregate
    ``total_at_risk_value`` / ``total_at_risk_units`` across all pages.

    - **Pagination**: ``page`` + ``page_size`` (batch-level)
    - **Sorting**: by ``expiry``, ``quantity``, ``value``, or ``name``
    """
    return get_near_expiry(
        db, store_id, days,
        page=page, page_size=page_size,
        sort_by=sort_by, sort_order=sort_order,
    )

