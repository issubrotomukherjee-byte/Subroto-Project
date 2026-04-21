"""
Purchase Service — create purchase invoices and add stock.

Stock updates are done by calling EXISTING inventory_service functions:
  - create_inventory(db, data) → for new batches
  - update_inventory(db, id, data) → for existing batches

Inventory service NEVER commits — this service controls the full
transaction: single db.commit() on success, full db.rollback() on failure.

units_per_strip is ALWAYS read from the Medicine model.
"""

import math
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from models.purchase import Purchase, PurchaseItem
from models.inventory import Inventory
from models.medicine import Medicine
from models.store import Store
from schemas.purchase_schema import PurchaseCreate
from schemas.inventory_schema import InventoryCreate, InventoryUpdate
from services.inventory_service import create_inventory, update_inventory


# ── Helpers ──────────────────────────────────────────────

def _validate_store(db: Session, store_id: int) -> Store:
    """Raise 404 if store doesn't exist."""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    return store


# ── Create Purchase ──────────────────────────────────────

def create_purchase(db: Session, data: PurchaseCreate) -> dict:
    """Create a purchase invoice and add stock for each item.

    Transaction flow:
      1. Validate store + batch-load all medicines
      2. Check duplicate invoice
      3. Create purchase header (flush for ID)
      4. For each item:
         a. Read units_per_strip from Medicine model
         b. If batch exists → verify expiry match → update_inventory()
         c. If batch new → create_inventory()
         d. Create PurchaseItem record (flush)
      5. Update purchase totals
      6. SINGLE db.commit()

    On ANY failure → full db.rollback().
    """
    try:
        # ── 1. Validate store ────────────────────────────
        _validate_store(db, data.store_id)

        # ── 2. Batch-load all medicines (avoid N+1) ─────
        medicine_ids = list(set(item.medicine_id for item in data.items))
        medicines = (
            db.query(Medicine)
            .filter(Medicine.id.in_(medicine_ids))
            .all()
        )
        med_map = {m.id: m for m in medicines}

        missing = [mid for mid in medicine_ids if mid not in med_map]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Medicine(s) not found: {missing}",
            )

        # ── 3. Check duplicate invoice (app layer) ──────
        duplicate = (
            db.query(Purchase)
            .filter(
                Purchase.supplier_name == data.supplier_name,
                Purchase.invoice_number == data.invoice_number,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Invoice '{data.invoice_number}' from supplier "
                    f"'{data.supplier_name}' already exists (purchase #{duplicate.id})"
                ),
            )

        # ── 4. Create purchase header ────────────────────
        purchase = Purchase(
            store_id=data.store_id,
            supplier_name=data.supplier_name,
            invoice_number=data.invoice_number,
            invoice_date=data.invoice_date or date.today(),
            total_items=0,
            total_quantity=0,
            total_amount=0.0,
        )
        db.add(purchase)
        db.flush()  # get purchase.id

        # ── 5. Process items ─────────────────────────────
        total_quantity = 0
        total_amount = 0.0
        response_items = []

        for item in data.items:
            medicine = med_map[item.medicine_id]
            ups = medicine.units_per_strip or 10  # from Medicine model
            units_added = item.quantity * ups
            line_total = round(item.purchase_price * units_added, 2)

            # Check if batch already exists
            existing_batch = (
                db.query(Inventory)
                .filter(
                    Inventory.store_id == data.store_id,
                    Inventory.medicine_id == item.medicine_id,
                    Inventory.batch_no == item.batch_no,
                )
                .with_for_update()  # row lock
                .first()
            )

            if existing_batch:
                # ── Batch EXISTS → verify expiry integrity ──
                if existing_batch.expiry_date != item.expiry_date:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Batch '{item.batch_no}' for medicine "
                            f"'{medicine.name}' already exists with expiry "
                            f"{existing_batch.expiry_date}. Cannot change to "
                            f"{item.expiry_date}."
                        ),
                    )

                # Increase stock via existing update_inventory()
                # NOTE: update_inventory is a SET operation, not ADD.
                # We pre-compute the new total here, then SET it.
                # No double-add risk — the function replaces quantity_units.
                new_total = (existing_batch.quantity_units or 0) + units_added
                inv_update = InventoryUpdate(quantity_units=new_total)
                inv_entry = update_inventory(
                    db, existing_batch.id, inv_update
                )

            else:
                # ── Batch NEW → create via existing create_inventory() ──
                inv_create = InventoryCreate(
                    medicine_name=medicine.name,
                    store_id=data.store_id,
                    quantity=item.quantity,
                    units_per_strip=ups,
                    batch_no=item.batch_no,
                    expiry_date=item.expiry_date,
                    mrp=item.mrp,
                    purchase_price=item.purchase_price,
                )
                inv_entry = create_inventory(db, inv_create)

            # ── Create PurchaseItem record ───────────────
            pi = PurchaseItem(
                purchase_id=purchase.id,
                medicine_id=item.medicine_id,
                inventory_id=inv_entry.id,
                batch_no=item.batch_no,
                expiry_date=item.expiry_date,
                quantity=item.quantity,
                units_per_strip=ups,
                quantity_units=units_added,
                purchase_price=item.purchase_price,
                mrp=item.mrp,
                line_total=line_total,
            )
            db.add(pi)
            db.flush()

            total_quantity += units_added
            total_amount += line_total

            response_items.append({
                "id": pi.id,
                "medicine_id": item.medicine_id,
                "medicine_name": medicine.name,
                "inventory_id": inv_entry.id,
                "batch_no": item.batch_no,
                "expiry_date": item.expiry_date,
                "quantity": item.quantity,
                "units_per_strip": ups,
                "quantity_units": units_added,
                "purchase_price": item.purchase_price,
                "mrp": item.mrp,
                "line_total": line_total,
            })

        # ── 6. Update purchase totals ────────────────────
        purchase.total_items = len(data.items)
        purchase.total_quantity = total_quantity
        purchase.total_amount = round(total_amount, 2)

        # ── 7. SINGLE COMMIT ────────────────────────────
        db.commit()
        db.refresh(purchase)

        return {
            "id": purchase.id,
            "store_id": purchase.store_id,
            "supplier_name": purchase.supplier_name,
            "invoice_number": purchase.invoice_number,
            "invoice_date": purchase.invoice_date,
            "total_items": purchase.total_items,
            "total_quantity": purchase.total_quantity,
            "total_amount": purchase.total_amount,
            "created_at": purchase.created_at,
            "items": response_items,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── Get Single Purchase ──────────────────────────────────

def get_purchase(db: Session, purchase_id: int) -> dict:
    """Return a single purchase with all items and stock detail."""
    purchase = (
        db.query(Purchase)
        .options(joinedload(Purchase.items))
        .filter(Purchase.id == purchase_id)
        .first()
    )
    if not purchase:
        raise HTTPException(status_code=404, detail="Purchase not found")

    # Batch-load medicine names (avoid N+1)
    med_ids = list(set(pi.medicine_id for pi in purchase.items))
    medicines = db.query(Medicine).filter(Medicine.id.in_(med_ids)).all()
    med_map = {m.id: m.name for m in medicines}

    items = [
        {
            "id": pi.id,
            "medicine_id": pi.medicine_id,
            "medicine_name": med_map.get(pi.medicine_id, f"Medicine #{pi.medicine_id}"),
            "inventory_id": pi.inventory_id,
            "batch_no": pi.batch_no,
            "expiry_date": pi.expiry_date,
            "quantity": pi.quantity,
            "units_per_strip": pi.units_per_strip,
            "quantity_units": pi.quantity_units,
            "purchase_price": pi.purchase_price,
            "mrp": pi.mrp,
            "line_total": pi.line_total,
        }
        for pi in purchase.items
    ]

    return {
        "id": purchase.id,
        "store_id": purchase.store_id,
        "supplier_name": purchase.supplier_name,
        "invoice_number": purchase.invoice_number,
        "invoice_date": purchase.invoice_date,
        "total_items": purchase.total_items,
        "total_quantity": purchase.total_quantity,
        "total_amount": purchase.total_amount,
        "created_at": purchase.created_at,
        "items": items,
    }


# ── List Purchases (paginated + filtered) ────────────────

def list_purchases(
    db: Session,
    store_id: Optional[int] = None,
    supplier_name: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return paginated list of purchases with optional filters.

    Filters:
    - store_id: exact match
    - supplier_name: case-insensitive partial match (ilike)
    - date_from / date_to: filter on invoice_date
    """
    base_filter = []
    if store_id is not None:
        _validate_store(db, store_id)
        base_filter.append(Purchase.store_id == store_id)
    if supplier_name is not None:
        base_filter.append(Purchase.supplier_name.ilike(f"%{supplier_name}%"))
    if date_from is not None:
        base_filter.append(Purchase.invoice_date >= date_from)
    if date_to is not None:
        base_filter.append(Purchase.invoice_date <= date_to)

    total = db.query(Purchase).filter(*base_filter).count()

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

    offset = (page - 1) * page_size
    rows = (
        db.query(Purchase)
        .filter(*base_filter)
        .order_by(Purchase.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "id": r.id,
            "store_id": r.store_id,
            "supplier_name": r.supplier_name,
            "invoice_number": r.invoice_number,
            "invoice_date": r.invoice_date,
            "total_items": r.total_items,
            "total_quantity": r.total_quantity,
            "total_amount": r.total_amount,
            "created_at": r.created_at,
        }
        for r in rows
    ]

    return {
        "store_id": store_id,
        "pagination": pagination,
        "items": items,
    }


# ── Supplier Summary (GROUP BY aggregation) ──────────────

def supplier_summary(
    db: Session,
    store_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Aggregated stats per supplier using SQL GROUP BY.

    Returns: total_purchase_value, total_invoices, avg_invoice_value,
    last_purchase_date — grouped by supplier_name.
    """
    from sqlalchemy import func as sqla_func

    base_filter = []
    if store_id is not None:
        _validate_store(db, store_id)
        base_filter.append(Purchase.store_id == store_id)

    # Count distinct suppliers for pagination
    total = (
        db.query(sqla_func.count(sqla_func.distinct(Purchase.supplier_name)))
        .filter(*base_filter)
        .scalar()
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

    offset = (page - 1) * page_size
    rows = (
        db.query(
            Purchase.supplier_name,
            sqla_func.sum(Purchase.total_amount).label("total_purchase_value"),
            sqla_func.count(Purchase.id).label("total_invoices"),
            sqla_func.avg(Purchase.total_amount).label("avg_invoice_value"),
            sqla_func.max(Purchase.created_at).label("last_purchase_date"),
        )
        .filter(*base_filter)
        .group_by(Purchase.supplier_name)
        .order_by(sqla_func.sum(Purchase.total_amount).desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = [
        {
            "supplier_name": r.supplier_name,
            "total_purchase_value": round(r.total_purchase_value or 0, 2),
            "total_invoices": r.total_invoices,
            "avg_invoice_value": round(r.avg_invoice_value or 0, 2),
            "last_purchase_date": r.last_purchase_date,
        }
        for r in rows
    ]

    return {
        "store_id": store_id,
        "pagination": pagination,
        "items": items,
    }


# ── Top Suppliers ────────────────────────────────────────

def top_suppliers(
    db: Session,
    store_id: Optional[int] = None,
    limit: int = 5,
) -> dict:
    """Top N suppliers ranked by total purchase value."""
    from sqlalchemy import func as sqla_func

    base_filter = []
    if store_id is not None:
        _validate_store(db, store_id)
        base_filter.append(Purchase.store_id == store_id)

    rows = (
        db.query(
            Purchase.supplier_name,
            sqla_func.sum(Purchase.total_amount).label("total_purchase_value"),
            sqla_func.count(Purchase.id).label("total_invoices"),
        )
        .filter(*base_filter)
        .group_by(Purchase.supplier_name)
        .order_by(sqla_func.sum(Purchase.total_amount).desc())
        .limit(limit)
        .all()
    )

    items = [
        {
            "rank": idx + 1,
            "supplier_name": r.supplier_name,
            "total_purchase_value": round(r.total_purchase_value or 0, 2),
            "total_invoices": r.total_invoices,
        }
        for idx, r in enumerate(rows)
    ]

    return {
        "store_id": store_id,
        "limit": limit,
        "items": items,
    }


# ── Price History for a Medicine ─────────────────────────

def price_history(
    db: Session,
    medicine_id: int,
    store_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Purchase price history for a specific medicine.

    Joins PurchaseItem → Purchase to get supplier + date context.
    Includes last_purchase_price and avg_purchase_price as aggregates.
    """
    from sqlalchemy import func as sqla_func

    # Validate medicine exists
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail=f"Medicine {medicine_id} not found")

    # Build filters (join condition handled in query)
    item_filter = [PurchaseItem.medicine_id == medicine_id]
    if store_id is not None:
        _validate_store(db, store_id)
        item_filter.append(Purchase.store_id == store_id)

    # Aggregates (single query)
    agg = (
        db.query(
            sqla_func.avg(PurchaseItem.purchase_price).label("avg_price"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*item_filter)
        .first()
    )
    avg_price = round(agg.avg_price, 2) if agg and agg.avg_price else None

    # Total count for pagination
    total = (
        db.query(PurchaseItem)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*item_filter)
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
            "medicine_id": medicine_id,
            "medicine_name": medicine.name,
            "last_purchase_price": None,
            "avg_purchase_price": avg_price,
            "store_id": store_id,
            "pagination": pagination,
            "items": [],
        }

    # Paginated history (newest first)
    offset = (page - 1) * page_size
    rows = (
        db.query(
            Purchase.supplier_name,
            PurchaseItem.purchase_price,
            PurchaseItem.mrp,
            PurchaseItem.quantity,
            PurchaseItem.quantity_units,
            Purchase.created_at.label("purchase_date"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*item_filter)
        .order_by(Purchase.created_at.desc())
        .offset(offset)
        .limit(page_size)
        .all()
    )

    # First row (newest) is the last_purchase_price
    last_price = rows[0].purchase_price if rows else None

    items = [
        {
            "supplier_name": r.supplier_name,
            "purchase_price": r.purchase_price,
            "mrp": r.mrp,
            "quantity": r.quantity,
            "quantity_units": r.quantity_units,
            "purchase_date": r.purchase_date,
        }
        for r in rows
    ]

    return {
        "medicine_id": medicine_id,
        "medicine_name": medicine.name,
        "last_purchase_price": last_price,
        "avg_purchase_price": avg_price,
        "store_id": store_id,
        "pagination": pagination,
        "items": items,
    }


# ── Smart Supplier ───────────────────────────────────────

def smart_supplier(
    db: Session,
    medicine_id: int,
    store_id: Optional[int] = None,
) -> dict:
    """Smart supplier analysis for a medicine.

    Two SQL queries, zero loops:
      Q1 — overall avg_price + last_purchase_price (ORDER BY + LIMIT 1)
      Q2 — per-supplier GROUP BY with correlated subquery for latest price

    best_supplier = lowest avg price; tie-break = latest invoice_date.
    best_price    = that supplier's most recent price (NOT max price).
    """
    from sqlalchemy import func as sqla_func, select

    # Validate medicine
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail=f"Medicine {medicine_id} not found")

    # Base filter
    base_filter = [PurchaseItem.medicine_id == medicine_id]
    if store_id is not None:
        _validate_store(db, store_id)
        base_filter.append(Purchase.store_id == store_id)

    # ── Q1: overall avg + last purchase price ────────────
    last_row = (
        db.query(
            PurchaseItem.purchase_price,
            Purchase.supplier_name,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*base_filter)
        .order_by(Purchase.invoice_date.desc(), Purchase.created_at.desc())
        .limit(1)
        .first()
    )

    if not last_row:
        raise HTTPException(status_code=404, detail="No purchase data found")

    last_purchase_price = last_row.purchase_price

    avg_row = (
        db.query(
            sqla_func.avg(PurchaseItem.purchase_price).label("avg_price"),
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*base_filter)
        .first()
    )
    avg_price = round(avg_row.avg_price or 0, 2)

    # ── Q2: per-supplier GROUP BY + correlated subquery ──
    # Table aliases so the correlated subquery doesn't collide
    # with the outer query's PurchaseItem / Purchase tables.
    pi_sub = PurchaseItem.__table__.alias("pi_sub")
    p_sub = Purchase.__table__.alias("p_sub")

    sub_where = [
        pi_sub.c.medicine_id == medicine_id,
        p_sub.c.supplier_name == Purchase.__table__.c.supplier_name,
    ]
    if store_id is not None:
        sub_where.append(p_sub.c.store_id == store_id)

    supplier_latest_sq = (
        select(pi_sub.c.purchase_price)
        .select_from(pi_sub.join(p_sub, pi_sub.c.purchase_id == p_sub.c.id))
        .where(*sub_where)
        .order_by(p_sub.c.invoice_date.desc(), p_sub.c.created_at.desc())
        .limit(1)
        .correlate(Purchase.__table__)
        .scalar_subquery()
        .label("last_price_per_supplier")
    )

    suppliers = (
        db.query(
            Purchase.supplier_name,
            sqla_func.avg(PurchaseItem.purchase_price).label("avg_pp"),
            sqla_func.max(Purchase.invoice_date).label("last_date"),
            supplier_latest_sq,
        )
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(*base_filter)
        .group_by(Purchase.supplier_name)
        .order_by(
            sqla_func.avg(PurchaseItem.purchase_price).asc(),
            sqla_func.max(Purchase.invoice_date).desc(),
        )
        .all()
    )

    # Best supplier = first row (lowest avg, latest date tie-break)
    best = suppliers[0]
    best_supplier = best.supplier_name
    best_price = round(best.last_price_per_supplier, 2)

    # ── Derived fields ───────────────────────────────────
    if last_purchase_price < avg_price:
        price_trend = "decreasing"
    elif last_purchase_price > avg_price:
        price_trend = "increasing"
    else:
        price_trend = "stable"

    savings_per_unit = round(last_purchase_price - best_price, 2)

    if savings_per_unit > 0:
        recommendation = (
            f"Switch to {best_supplier} to save ₹{savings_per_unit:.2f}/unit"
        )
    elif len(suppliers) == 1:
        recommendation = f"{best_supplier} is the only supplier on record"
    else:
        recommendation = "Current pricing is optimal"

    return {
        "medicine_id": medicine_id,
        "medicine_name": medicine.name,
        "store_id": store_id,
        "last_purchase_price": round(last_purchase_price, 2),
        "avg_price": avg_price,
        "best_supplier": best_supplier,
        "best_price": best_price,
        "price_trend": price_trend,
        "savings_per_unit": savings_per_unit,
        "recommendation": recommendation,
    }



