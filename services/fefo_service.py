"""
FEFO (First Expiry, First Out) — modular batch-selection engine.

This module is the single source of truth for batch allocation logic.
It is consumed by billing_service.py and the /orders/process endpoint.

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

    The FEFO ordering is enforced at the **database level** via
    ``ORDER BY expiry_date ASC``, so callers never need to re-sort.

    Raises
    ------
    HTTPException 404
        If the medicine_id does not exist.
    HTTPException 400
        If zero valid (non-expired, qty > 0) batches are found.
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
            Inventory.quantity > 0,
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
    required_quantity: int,
) -> list[dict]:
    """Walk through FEFO-sorted batches and build an allocation plan.

    This is a **pure logic function** — it does NOT mutate the database
    or the ORM objects.  It only reads batch attributes and returns a
    list of allocation dicts.

    Each allocation dict contains::

        {
            "batch_id":        int,   # inventory.id
            "batch_no":        str,
            "expiry_date":     date,
            "mrp":             float,
            "purchase_price":  float,
            "allocated_qty":   int,
            "inventory_ref":   Inventory,  # ORM reference for reduce_stock()
        }

    Raises
    ------
    HTTPException 400
        If total available qty across all batches < required_quantity.
    """
    total_available = sum(b.quantity for b in batches)
    if total_available < required_quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient stock. "
                f"Requested {required_quantity}, available (non-expired) {total_available}."
            ),
        )

    allocations: list[dict] = []
    remaining = required_quantity

    for batch in batches:
        if remaining <= 0:
            break

        take = min(batch.quantity, remaining)
        remaining -= take

        allocations.append({
            "batch_id": batch.id,
            "batch_no": batch.batch_no,
            "expiry_date": batch.expiry_date,
            "mrp": batch.mrp,
            "purchase_price": batch.purchase_price,
            "allocated_qty": take,
            "inventory_ref": batch,      # live ORM object for reduce_stock
        })

    return allocations


# ── 3. PRICING ──────────────────────────────────────────

def calculate_total(allocations: list[dict]) -> dict:
    """Compute totals from a FEFO allocation plan.

    Uses **batch-level MRP** — each batch prices its own consumed units,
    then all are summed.  NO weighted average.

    Returns::

        {
            "total_price":         float,  # sum(mrp × qty)
            "total_purchase_cost": float,  # sum(purchase_price × qty)
            "total_profit":        float,  # total_price - total_purchase_cost
            "total_quantity":      int,
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
    """Deduct allocated quantities from inventory batches.

    Uses the live ORM references stored in each allocation dict
    so changes are tracked by the current SQLAlchemy session.

    The caller is responsible for ``db.commit()`` / ``db.rollback()``.
    """
    for alloc in allocations:
        batch: Inventory = alloc["inventory_ref"]
        batch.quantity -= alloc["allocated_qty"]
