"""
FEFO (First Expiry, First Out) — modular batch-selection engine.

All internal logic operates in UNITS (tablets/capsules).
The ``quantity_units`` field is the source of truth for stock levels.

Designed for future integration with:
  - Pick-to-light hardware
  - RFID tray systems
  - Gravity-based dispensing
"""

from datetime import date
from typing import List

from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.inventory import Inventory
from models.medicine import Medicine


# ── 1. DATABASE QUERY ────────────────────────────────────

def get_available_batches(
    db: Session,
    store_id: int,
    medicine_id: int,
) -> List[Inventory]:
    """Fetch all non-expired batches with stock > 0, ordered by expiry ASC.

    Uses ``quantity_units`` (units) as the stock availability check.
    FEFO ordering is enforced at the **database level**.

    Raises
    ------
    HTTPException 404
        If the medicine_id does not exist.
    HTTPException 400
        If zero valid (non-expired, units > 0) batches are found.
    """
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(
            status_code=404,
            detail=f"Medicine {medicine_id} not found",
        )

    batches = (
        db.query(Inventory)
        .filter(
            Inventory.store_id == store_id,
            Inventory.medicine_id == medicine_id,
            Inventory.quantity_units > 0,
            Inventory.expiry_date >= date.today(),
        )
        .order_by(Inventory.expiry_date.asc())
        .all()
    )

    if not batches:
        raise HTTPException(
            status_code=400,
            detail=f"No valid (non-expired) stock for medicine {medicine_id} in store {store_id}.",
        )

    return batches


# ── 2. FEFO ALLOCATION ──────────────────────────────────

def apply_fefo(
    batches: List[Inventory],
    required_units: int,
) -> list[dict]:
    """Walk through FEFO-sorted batches and build an allocation plan in UNITS.

    This is a **pure logic function** — it does NOT mutate the database
    or the ORM objects.  It only reads batch attributes.

    Each allocation dict contains::

        {
            "batch_id":         int,
            "batch_no":         str,
            "expiry_date":      date,
            "mrp":              float,
            "purchase_price":   float,
            "units_per_strip":  int,
            "allocated_qty":    int,     # in UNITS
            "inventory_ref":    Inventory,
        }

    Raises
    ------
    HTTPException 400
        If total available units across all batches < required_units.
    """
    total_available = sum(b.quantity_units for b in batches)
    if total_available < required_units:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock. "
                f"Requested {required_units} units, "
                f"available (non-expired) {total_available} units."
            ),
        )

    allocations: list[dict] = []
    remaining = required_units

    for batch in batches:
        if remaining <= 0:
            break

        take = min(batch.quantity_units, remaining)
        remaining -= take

        allocations.append({
            "batch_id": batch.id,
            "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date,
            "mrp": batch.mrp,
            "purchase_price": batch.purchase_price,
            "units_per_strip": batch.units_per_strip or 10,
            "allocated_qty": take,          # in UNITS
            "inventory_ref": batch,
        })

    return allocations


# ── 3. PRICING ──────────────────────────────────────────

def calculate_total(allocations: list[dict]) -> dict:
    """Compute totals from a FEFO allocation plan.

    MRP and purchase_price are **per-unit** prices.
    Uses batch-level pricing — NO weighted average.

    Returns::

        {
            "total_price":         float,
            "total_purchase_cost": float,
            "total_profit":        float,
            "total_quantity":      int,    # in UNITS
        }
    """
    total_price = 0.0
    total_purchase_cost = 0.0
    total_quantity = 0

    for alloc in allocations:
        qty = alloc["allocated_qty"]
        total_price += alloc["mrp"] * qty
        total_purchase_cost += alloc["purchase_price"] * qty
        total_quantity += qty

    return {
        "total_price": round(total_price, 2),
        "total_purchase_cost": round(total_purchase_cost, 2),
        "total_profit": round(total_price - total_purchase_cost, 2),
        "total_quantity": total_quantity,
    }


# ── 4. STOCK UPDATE ────────────────────────────────────

def reduce_stock(db: Session, allocations: list[dict]) -> None:
    """Deduct allocated units from inventory batches.

    Deducts from ``quantity_units`` (the primary stock field).
    Also updates the legacy ``quantity`` (strips) field for backward compat.

    The caller is responsible for ``db.commit()`` / ``db.rollback()``.
    """
    for alloc in allocations:
        batch: Inventory = alloc["inventory_ref"]
        batch.quantity_units -= alloc["allocated_qty"]

        # Keep legacy strips field in sync (best-effort)
        ups = batch.units_per_strip or 10
        batch.quantity = batch.quantity_units // ups
