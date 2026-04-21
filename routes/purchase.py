from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from database.connection import get_db
from dependencies.auth import get_current_user, require_admin

from schemas.purchase_schema import (
    PurchaseCreate,
    PurchaseResponse,
    PurchaseListResponse,
    SupplierSummaryResponse,
    TopSuppliersResponse,
    PriceHistoryResponse,
)
from services.purchase_service import (
    create_purchase,
    get_purchase,
    list_purchases,
    supplier_summary,
    top_suppliers,
    price_history,
)

router = APIRouter()


@router.post(
    "/",
    response_model=PurchaseResponse,
    status_code=201,
    summary="Create purchase invoice",
)
def place_purchase(
    data: PurchaseCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a purchase invoice and add stock to inventory. Admin-only.

    For each item:
    - Existing batch: stock is SET after computing new total (expiry must match)
    - New batch: a new inventory entry is created

    Atomic: if any item fails, nothing is committed.
    """
    require_admin(user)
    return create_purchase(db, data)


@router.get(
    "/suppliers/summary",
    response_model=SupplierSummaryResponse,
    summary="Supplier summary stats",
)
def read_supplier_summary(
    store_id: Optional[int] = Query(None, description="Filter by store"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Aggregated stats per supplier. Admin-only."""
    require_admin(user)
    return supplier_summary(db, store_id=store_id, page=page, page_size=page_size)


@router.get(
    "/suppliers/top",
    response_model=TopSuppliersResponse,
    summary="Top suppliers by value",
)
def read_top_suppliers(
    store_id: Optional[int] = Query(None, description="Filter by store"),
    limit: int = Query(5, ge=1, le=50, description="Number of suppliers"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Top N suppliers ranked by total purchase value. Admin-only."""
    require_admin(user)
    return top_suppliers(db, store_id=store_id, limit=limit)


@router.get(
    "/price-history/{medicine_id}",
    response_model=PriceHistoryResponse,
    summary="Medicine price history",
)
def read_price_history(
    medicine_id: int,
    store_id: Optional[int] = Query(None, description="Filter by store"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Purchase price history for a specific medicine. Admin-only."""
    require_admin(user)
    return price_history(
        db,
        medicine_id,
        store_id=store_id,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{purchase_id}",
    response_model=PurchaseResponse,
    summary="Get purchase details",
)
def read_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Return a single purchase invoice with all items. Admin-only."""
    require_admin(user)
    return get_purchase(db, purchase_id)


@router.get(
    "/",
    response_model=PurchaseListResponse,
    summary="List purchases",
)
def read_purchases(
    store_id: Optional[int] = Query(None, description="Filter by store"),
    supplier_name: Optional[str] = Query(None, description="Supplier name (partial, case-insensitive)"),
    date_from: Optional[date] = Query(None, description="From date (invoice_date)"),
    date_to: Optional[date] = Query(None, description="To date (invoice_date)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all purchase invoices with optional filters. Admin-only."""
    require_admin(user)
    return list_purchases(
        db,
        store_id=store_id,
        supplier_name=supplier_name,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
