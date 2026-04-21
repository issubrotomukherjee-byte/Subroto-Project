"""
Inventory Adjustment Service — stock corrections with full audit trail.

Handles manual stock increases/decreases (damaged goods, miscounts,
returns, etc.) while maintaining an immutable adjustment log.

All mutations happen inside a single DB transaction.
"""

import math
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.inventory import Inventory
from models.inventory_adjustment import InventoryAdjustment
from models.medicine import Medicine
from models.store import Store
from schemas.inventory_adjustment_schema import InventoryAdjustRequest


def _validate_store(db: Session, store_id: int) -> Store:
    """Raise 404 if store doesn't exist."""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    return store


def adjust_inventory(
    db: Session,
    data: InventoryAdjustRequest,
    admin_name: str,
) -> dict:
    """Adjust stock for an existing inventory batch.

    1. Validate store, medicine, batch all exist
    2. Compute new quantity (prevent negative)
    3. Update inventory row
    4. Create immutable audit log entry
    5. Commit as single transaction

    Returns full adjustment detail including before/after snapshots.
    """
    try:
        # ── 1. Validate entities ─────────────────────────
        _validate_store(db, data.store_id)

        medicine = db.query(Medicine).filter(Medicine.id == data.medicine_id).first()
        if not medicine:
            raise HTTPException(
                status_code=404,
                detail=f"Medicine {data.medicine_id} not found",
            )

        # Find the specific batch
        entry = (
            db.query(Inventory)
            .filter(
                Inventory.store_id == data.store_id,
                Inventory.medicine_id == data.medicine_id,
                Inventory.batch_no == data.batch_no,
            )
            .with_for_update()  # row-level lock for concurrency safety
            .first()
        )

        if not entry:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Batch '{data.batch_no}' not found for medicine "
                    f"{data.medicine_id} in store {data.store_id}"
                ),
            )

        # ── 2. Compute new quantity ──────────────────────
        current_units = entry.quantity_units or 0

        if data.adjustment_type == "increase":
            new_units = current_units + data.quantity
        else:  # decrease
            new_units = current_units - data.quantity

            if new_units < 0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot decrease by {data.quantity} units. "
                        f"Current stock is only {current_units} units."
                    ),
                )

        # ── 3. Update inventory ──────────────────────────
        quantity_before = current_units
        entry.quantity_units = new_units

        # Keep legacy strips field in sync
        ups = entry.units_per_strip or 10
        entry.quantity = new_units // ups

        # ── 4. Create audit log entry ────────────────────
        adjustment = InventoryAdjustment(
            inventory_id=entry.id,
            store_id=data.store_id,
            medicine_id=data.medicine_id,
            batch_no=data.batch_no,
            adjustment_type=data.adjustment_type,
            quantity=data.quantity,
            quantity_before=quantity_before,
            quantity_after=new_units,
            reason=data.reason,
            adjusted_by=admin_name,
        )
        db.add(adjustment)

        # ── 5. Commit ───────────────────────────────────
        db.commit()
        db.refresh(entry)
        db.refresh(adjustment)

        # ── 6. Build response ───────────────────────────
        return {
            "adjustment_id": adjustment.id,
            "inventory_id": entry.id,
            "store_id": data.store_id,
            "medicine_id": data.medicine_id,
            "medicine_name": medicine.name,
            "batch_no": data.batch_no,
            "adjustment_type": data.adjustment_type,
            "quantity_adjusted": data.quantity,
            "quantity_before": quantity_before,
            "quantity_after": new_units,
            "units_per_strip": entry.units_per_strip,
            "strips_after": new_units // ups,
            "loose_units_after": new_units % ups,
            "reason": data.reason,
            "adjusted_by": admin_name,
            "created_at": adjustment.created_at,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_adjustment_log(
    db: Session,
    store_id: int,
    page: int = 1,
    page_size: int = 20,
    medicine_id: Optional[int] = None,
) -> dict:
    """Return paginated adjustment history for a store.

    Optionally filtered by ``medicine_id``.
    Sorted newest-first.
    """
    _validate_store(db, store_id)

    base_filter = [InventoryAdjustment.store_id == store_id]
    if medicine_id is not None:
        base_filter.append(InventoryAdjustment.medicine_id == medicine_id)

    # Total count
    total = (
        db.query(InventoryAdjustment)
        .filter(*base_filter)
        .count()
    )

    pagination = {
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0,
    }

    if total == 0:
        return {
            "store_id": store_id,
            "pagination": pagination,
            "items": [],
        }

    # Paginated data
    offset = (page - 1) * page_size
    rows = (
        db.query(InventoryAdjustment)
        .filter(*base_filter)
        .order_by(InventoryAdjustment.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "id": r.id,
            "inventory_id": r.inventory_id,
            "store_id": r.store_id,
            "medicine_id": r.medicine_id,
            "batch_no": r.batch_no,
            "adjustment_type": r.adjustment_type,
            "quantity": r.quantity,
            "quantity_before": r.quantity_before,
            "quantity_after": r.quantity_after,
            "reason": r.reason,
            "adjusted_by": r.adjusted_by,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    return {
        "store_id": store_id,
        "pagination": pagination,
        "items": items,
    }
