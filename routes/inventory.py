from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from dependencies.auth import get_current_user, require_admin
from schemas.inventory_schema import (
    InventoryCreate,
    InventoryUpdate,
    InventoryResponse,
    InventoryAdminResponse,
)
from schemas.inventory_adjustment_schema import (
    InventoryAdjustRequest,
    InventoryAdjustResponse,
    AdjustmentLogResponse,
)
from services.inventory_service import create_inventory, get_inventory_by_medicine, update_inventory
from services.inventory_adjustment_service import adjust_inventory, get_adjustment_log

router = APIRouter()


def _enrich_inventory_response(entry, schema_cls):
    """Build an inventory response with computed strips/loose_units."""
    ups = entry.units_per_strip or 10
    qu = entry.quantity_units or 0
    data = schema_cls.model_validate(entry)
    data.strips = qu // ups
    data.loose_units = qu % ups
    return data


@router.post("/", response_model=InventoryResponse, status_code=201)
def add_inventory(data: InventoryCreate, db: Session = Depends(get_db)):
    """Add stock for a store-medicine-batch combo.

    Accepts ``quantity`` in **strips** and ``units_per_strip``.
    Backend converts to units internally.
    """
    entry = create_inventory(db, data)
    db.commit()
    db.refresh(entry)
    return _enrich_inventory_response(entry, InventoryResponse)


@router.get("/medicine/{medicine_id}")
def read_inventory_by_medicine(
    medicine_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get stock entries for a given medicine across all stores (sorted by expiry).

    Response includes both unit and strip breakdowns.
    - **Admin**: response includes ``purchase_price``
    - **Worker**: response excludes ``purchase_price``
    """
    records = get_inventory_by_medicine(db, medicine_id)

    if user["role"] == "admin":
        return [_enrich_inventory_response(r, InventoryAdminResponse) for r in records]
    return [_enrich_inventory_response(r, InventoryResponse) for r in records]


@router.put("/{inventory_id}", response_model=InventoryResponse)
def modify_inventory(inventory_id: int, data: InventoryUpdate, db: Session = Depends(get_db)):
    """Update quantity of an existing stock entry.

    Accepts either ``quantity`` (strips) or ``quantity_units`` (units).
    """
    entry = update_inventory(db, inventory_id, data)
    db.commit()
    db.refresh(entry)
    return _enrich_inventory_response(entry, InventoryResponse)


# ── Stock Adjustment (admin-only) ────────────────────────

@router.post(
    "/adjust",
    response_model=InventoryAdjustResponse,
    status_code=200,
    summary="Adjust stock (increase/decrease)",
)
def adjust_stock(
    data: InventoryAdjustRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Manually adjust stock for an inventory batch. **Admin-only.**

    Use cases: damaged goods, physical count corrections, returns,
    stock write-offs, or manual replenishment.

    - ``adjustment_type``: ``"increase"`` or ``"decrease"``
    - ``quantity``: positive integer (units)
    - ``reason``: mandatory text (audit trail)

    Stock cannot go below zero. Every adjustment is logged to an
    immutable audit table with before/after snapshots.

    Returns the full adjustment record with updated stock levels.
    """
    require_admin(user)
    admin_name = user.get("name", "admin")
    return adjust_inventory(db, data, admin_name)


# ── Adjustment History (admin-only) ──────────────────────

@router.get(
    "/adjustments/store/{store_id}",
    response_model=AdjustmentLogResponse,
    summary="Adjustment audit log",
)
def read_adjustment_log(
    store_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    medicine_id: int = Query(None, description="Optional: filter by medicine ID"),
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """View paginated adjustment history for a store. **Admin-only.**

    Sorted newest-first. Optionally filtered by ``medicine_id``.
    """
    require_admin(user)
    return get_adjustment_log(
        db, store_id,
        page=page, page_size=page_size,
        medicine_id=medicine_id,
    )

