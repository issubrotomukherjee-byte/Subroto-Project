"""
Inventory Intelligence Service — read-only analytics over existing data.

All functions query the existing Inventory, Medicine, Order, and OrderItem
tables.  NO writes, NO new tables, NO modifications to existing models.

Default thresholds are passed as function arguments so they can be
overridden via query params at the route level.
"""

from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException

from models.inventory import Inventory
from models.medicine import Medicine
from models.order import Order
from models.order_item import OrderItem
from models.store import Store


# ── Defaults ─────────────────────────────────────────────

DEFAULT_LOW_STOCK_THRESHOLD = 50   # units
DEFAULT_EXPIRY_WARNING_DAYS = 30   # days
DEFAULT_DEAD_STOCK_DAYS = 90       # days


# ── Helpers ──────────────────────────────────────────────

def _validate_store(db: Session, store_id: int) -> Store:
    """Raise 404 if store doesn't exist."""
    store = db.query(Store).filter(Store.id == store_id).first()
    if not store:
        raise HTTPException(status_code=404, detail=f"Store {store_id} not found")
    return store


def _active_batches(db: Session, store_id: int):
    """Base query: all inventory rows for a store with stock > 0."""
    return (
        db.query(Inventory)
        .filter(
            Inventory.store_id == store_id,
            Inventory.quantity_units > 0,
        )
    )


# ── 1. Dashboard ─────────────────────────────────────────

def get_store_dashboard(
    db: Session,
    store_id: int,
    low_stock_threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
    expiry_warning_days: int = DEFAULT_EXPIRY_WARNING_DAYS,
) -> dict:
    """Build a real-time stock summary for a store."""
    _validate_store(db, store_id)

    today = date.today()
    warning_cutoff = today + timedelta(days=expiry_warning_days)

    batches = _active_batches(db, store_id).all()

    total_medicines = len(set(b.medicine_id for b in batches))
    total_batches = len(batches)
    total_units = sum(b.quantity_units or 0 for b in batches)
    total_mrp_value = round(sum((b.mrp or 0) * (b.quantity_units or 0) for b in batches), 2)

    low_stock_count = sum(
        1 for b in batches if (b.quantity_units or 0) < low_stock_threshold
    )
    expired_count = sum(1 for b in batches if b.expiry_date < today)
    expiring_soon_count = sum(
        1 for b in batches
        if today <= b.expiry_date <= warning_cutoff
    )

    return {
        "store_id": store_id,
        "total_medicines": total_medicines,
        "total_batches": total_batches,
        "total_units": total_units,
        "total_mrp_value": total_mrp_value,
        "low_stock_count": low_stock_count,
        "expiring_soon_count": expiring_soon_count,
        "expired_count": expired_count,
    }


# ── 2. Low-Stock Alerts ─────────────────────────────────

def get_low_stock(
    db: Session,
    store_id: int,
    threshold: int = DEFAULT_LOW_STOCK_THRESHOLD,
) -> dict:
    """Return all batches whose unit count is below the threshold."""
    _validate_store(db, store_id)

    rows = (
        _active_batches(db, store_id)
        .filter(Inventory.quantity_units < threshold)
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .order_by(Inventory.quantity_units.asc())
        .all()
    )

    items = []
    for r in rows:
        items.append({
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine.name,
            "batch_no": r.batch_no,
            "quantity_units": r.quantity_units,
            "units_per_strip": r.units_per_strip,
            "expiry_date": r.expiry_date,
            "mrp": r.mrp,
        })

    return {
        "store_id": store_id,
        "threshold_units": threshold,
        "count": len(items),
        "items": items,
    }


# ── 3. Expiry Alerts ────────────────────────────────────

def get_expiry_alerts(
    db: Session,
    store_id: int,
    warning_days: int = DEFAULT_EXPIRY_WARNING_DAYS,
) -> dict:
    """Return expired + near-expiry batches for a store."""
    _validate_store(db, store_id)

    today = date.today()
    warning_cutoff = today + timedelta(days=warning_days)

    # Get all batches that are either expired or expiring within window
    rows = (
        _active_batches(db, store_id)
        .filter(Inventory.expiry_date <= warning_cutoff)
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .order_by(Inventory.expiry_date.asc())
        .all()
    )

    items = []
    expired_count = 0
    expiring_soon_count = 0

    for r in rows:
        days_remaining = (r.expiry_date - today).days
        if days_remaining < 0:
            status = "expired"
            expired_count += 1
        else:
            status = "expiring_soon"
            expiring_soon_count += 1

        items.append({
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine.name,
            "batch_no": r.batch_no,
            "expiry_date": r.expiry_date,
            "quantity_units": r.quantity_units,
            "days_remaining": days_remaining,
            "status": status,
        })

    return {
        "store_id": store_id,
        "warning_days": warning_days,
        "expired_count": expired_count,
        "expiring_soon_count": expiring_soon_count,
        "items": items,
    }


# ── 4. Stock Valuation ──────────────────────────────────

def get_stock_valuation(db: Session, store_id: int) -> dict:
    """Compute MRP vs cost valuation grouped by medicine. Admin-only data."""
    _validate_store(db, store_id)

    # Aggregate at medicine level
    rows = (
        db.query(
            Inventory.medicine_id,
            Medicine.name.label("medicine_name"),
            func.sum(Inventory.quantity_units).label("total_units"),
            func.sum(Inventory.mrp * Inventory.quantity_units).label("mrp_value"),
            func.sum(Inventory.purchase_price * Inventory.quantity_units).label("cost_value"),
        )
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .filter(
            Inventory.store_id == store_id,
            Inventory.quantity_units > 0,
        )
        .group_by(Inventory.medicine_id, Medicine.name)
        .order_by(Medicine.name)
        .all()
    )

    items = []
    total_mrp = 0.0
    total_cost = 0.0

    for r in rows:
        mrp_val = round(r.mrp_value or 0, 2)
        cost_val = round(r.cost_value or 0, 2)
        profit = round(mrp_val - cost_val, 2)

        total_mrp += mrp_val
        total_cost += cost_val

        items.append({
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine_name,
            "total_units": r.total_units or 0,
            "mrp_value": mrp_val,
            "cost_value": cost_val,
            "potential_profit": profit,
        })

    return {
        "store_id": store_id,
        "total_mrp_value": round(total_mrp, 2),
        "total_cost_value": round(total_cost, 2),
        "total_potential_profit": round(total_mrp - total_cost, 2),
        "item_count": len(items),
        "items": items,
    }


# ── 5. Dead Stock Detection ─────────────────────────────

def get_dead_stock(
    db: Session,
    store_id: int,
    threshold_days: int = DEFAULT_DEAD_STOCK_DAYS,
) -> dict:
    """Identify medicines in stock that haven't sold in N days.

    A medicine is considered "dead stock" if there is no OrderItem linked
    to an Order for this store within the last `threshold_days` days,
    but inventory still exists.
    """
    _validate_store(db, store_id)

    cutoff_date = datetime.now() - timedelta(days=threshold_days)

    # Step 1: Get all medicines that have stock in this store
    stocked = (
        db.query(
            Inventory.medicine_id,
            func.sum(Inventory.quantity_units).label("total_units"),
            func.count(Inventory.id).label("batch_count"),
        )
        .filter(
            Inventory.store_id == store_id,
            Inventory.quantity_units > 0,
        )
        .group_by(Inventory.medicine_id)
        .all()
    )

    if not stocked:
        return {
            "store_id": store_id,
            "threshold_days": threshold_days,
            "count": 0,
            "items": [],
        }

    stocked_ids = [s.medicine_id for s in stocked]

    # Step 2: For each stocked medicine, find the latest sale date in this store
    latest_sales_subq = (
        db.query(
            OrderItem.medicine_id,
            func.max(Order.created_at).label("last_sold_at"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .filter(
            Order.store_id == store_id,
            OrderItem.medicine_id.in_(stocked_ids),
        )
        .group_by(OrderItem.medicine_id)
        .subquery()
    )

    # Step 3: Build lookup of last sale dates
    sale_rows = db.query(latest_sales_subq).all()
    sale_map: dict[int, Optional[datetime]] = {
        row.medicine_id: row.last_sold_at for row in sale_rows
    }

    items = []
    today = datetime.now()

    for s in stocked:
        med_id = s.medicine_id
        last_sold = sale_map.get(med_id)

        # Dead if: never sold, OR last sale before cutoff
        is_dead = (last_sold is None) or (last_sold < cutoff_date)

        if not is_dead:
            continue

        medicine = db.query(Medicine).filter(Medicine.id == med_id).first()
        medicine_name = medicine.name if medicine else f"Medicine #{med_id}"

        days_since = None
        if last_sold is not None:
            days_since = (today - last_sold).days

        items.append({
            "medicine_id": med_id,
            "medicine_name": medicine_name,
            "total_units_in_stock": s.total_units or 0,
            "batch_count": s.batch_count or 0,
            "last_sold_at": last_sold,
            "days_since_last_sale": days_since,
        })

    # Sort: never-sold first, then by longest time since sale
    items.sort(key=lambda x: (x["days_since_last_sale"] is not None, x["days_since_last_sale"] or 0))

    return {
        "store_id": store_id,
        "threshold_days": threshold_days,
        "count": len(items),
        "items": items,
    }


# ── 6. Inventory Search ─────────────────────────────────

# Valid sort columns for search
_SEARCH_SORT_FIELDS = {"name", "stock", "expiry"}


def _paginate(total: int, page: int, page_size: int) -> dict:
    """Build pagination metadata dict."""
    import math
    return {
        "page": page,
        "page_size": page_size,
        "total_items": total,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0,
    }


def search_inventory(
    db: Session,
    store_id: int,
    query: str,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "name",
    sort_order: str = "asc",
) -> dict:
    """Search medicines in a store's inventory with batch-level detail.

    Three-query strategy for efficiency:
      1. Aggregate query — distinct medicines matching ``query`` with totals
      2. Count query — total matching medicines (for pagination)
      3. Batch query — all inventory rows for the paginated slice
    """
    _validate_store(db, store_id)

    if sort_by not in _SEARCH_SORT_FIELDS:
        sort_by = "name"

    today = date.today()

    # ── Sort clause ──────────────────────────────────────
    if sort_by == "name":
        order_col = Medicine.name
    elif sort_by == "stock":
        order_col = func.sum(Inventory.quantity_units)
    else:  # "expiry"
        order_col = func.min(Inventory.expiry_date)

    if sort_order.lower() == "desc":
        order_col = order_col.desc()
    else:
        order_col = order_col.asc()

    # ── Base filter ──────────────────────────────────────
    base_filter = [
        Inventory.store_id == store_id,
        Inventory.quantity_units > 0,
    ]
    if query.strip():
        base_filter.append(Medicine.name.ilike(f"%{query.strip()}%"))

    # ── Q1: Total count of matching medicines ────────────
    total_count = (
        db.query(func.count(func.distinct(Inventory.medicine_id)))
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .filter(*base_filter)
        .scalar()
    ) or 0

    pagination = _paginate(total_count, page, page_size)

    if total_count == 0:
        return {
            "store_id": store_id,
            "query": query,
            "pagination": pagination,
            "items": [],
        }

    # ── Q2: Aggregated medicines (paginated) ─────────────
    offset = (page - 1) * page_size

    med_agg = (
        db.query(
            Inventory.medicine_id,
            Medicine.name.label("medicine_name"),
            func.sum(Inventory.quantity_units).label("total_stock"),
            func.count(Inventory.id).label("batch_count"),
            func.min(Inventory.expiry_date).label("nearest_expiry"),
        )
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .filter(*base_filter)
        .group_by(Inventory.medicine_id, Medicine.name)
        .order_by(order_col)
        .offset(offset)
        .limit(page_size)
        .all()
    )

    med_ids = [m.medicine_id for m in med_agg]

    # ── Q3: All batches for the paginated medicines ──────
    batches = (
        db.query(Inventory)
        .filter(
            Inventory.store_id == store_id,
            Inventory.medicine_id.in_(med_ids),
            Inventory.quantity_units > 0,
        )
        .order_by(Inventory.expiry_date.asc())
        .all()
    )

    # Group batches by medicine_id
    batch_map: dict[int, list] = {}
    for b in batches:
        batch_map.setdefault(b.medicine_id, []).append(b)

    # ── Build response items ─────────────────────────────
    items = []
    for m in med_agg:
        med_batches = batch_map.get(m.medicine_id, [])
        total_stock = m.total_stock or 0

        items.append({
            "medicine_id": m.medicine_id,
            "medicine_name": m.medicine_name,
            "total_stock": total_stock,
            "reserved_stock": 0,          # no reservation system yet
            "available_stock": total_stock,
            "nearest_expiry": m.nearest_expiry,
            "batch_count": m.batch_count or 0,
            "batches": [
                {
                    "inventory_id": b.id,
                    "batch_no": b.batch_no,
                    "quantity_units": b.quantity_units,
                    "units_per_strip": b.units_per_strip,
                    "expiry_date": b.expiry_date,
                    "days_until_expiry": (b.expiry_date - today).days,
                    "mrp": b.mrp,
                    "rack_location": None,  # future field
                }
                for b in med_batches
            ],
        })

    return {
        "store_id": store_id,
        "query": query,
        "pagination": pagination,
        "items": items,
    }


# ── 7. Near-Expiry (Paginated) ──────────────────────────

# Valid sort columns for near-expiry
_NEAR_EXPIRY_SORT_FIELDS = {"expiry", "quantity", "value", "name"}


def get_near_expiry(
    db: Session,
    store_id: int,
    days: int = 90,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "expiry",
    sort_order: str = "asc",
) -> dict:
    """Return batches expiring within ``days`` from today, with pagination.

    Unlike ``get_expiry_alerts``, this endpoint:
    - Is purely forward-looking (no expired items)
    - Supports pagination and sorting
    - Includes per-item ``stock_value`` and aggregated totals
    """
    _validate_store(db, store_id)

    if sort_by not in _NEAR_EXPIRY_SORT_FIELDS:
        sort_by = "expiry"

    today = date.today()
    cutoff = today + timedelta(days=days)

    base_filter = [
        Inventory.store_id == store_id,
        Inventory.quantity_units > 0,
        Inventory.expiry_date >= today,
        Inventory.expiry_date <= cutoff,
    ]

    # ── Sort clause ──────────────────────────────────────
    sort_map = {
        "expiry": Inventory.expiry_date,
        "quantity": Inventory.quantity_units,
        "value": (Inventory.mrp * Inventory.quantity_units),
        "name": Medicine.name,
    }
    order_col = sort_map[sort_by]
    if sort_order.lower() == "desc":
        order_col = order_col.desc()
    else:
        order_col = order_col.asc()

    # ── Totals (full set, unpaginated) ───────────────────
    totals = (
        db.query(
            func.count(Inventory.id).label("cnt"),
            func.coalesce(func.sum(Inventory.quantity_units), 0).label("total_units"),
            func.coalesce(
                func.sum(Inventory.mrp * Inventory.quantity_units), 0
            ).label("total_value"),
        )
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .filter(*base_filter)
        .first()
    )

    total_count = totals.cnt or 0
    pagination = _paginate(total_count, page, page_size)

    if total_count == 0:
        return {
            "store_id": store_id,
            "days_threshold": days,
            "total_at_risk_value": 0.0,
            "total_at_risk_units": 0,
            "pagination": pagination,
            "items": [],
        }

    # ── Paginated data ───────────────────────────────────
    offset = (page - 1) * page_size

    rows = (
        db.query(Inventory)
        .join(Medicine, Inventory.medicine_id == Medicine.id)
        .filter(*base_filter)
        .order_by(order_col)
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = []
    for r in rows:
        qty = r.quantity_units or 0
        items.append({
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine.name,
            "batch_no": r.batch_no,
            "expiry_date": r.expiry_date,
            "days_until_expiry": (r.expiry_date - today).days,
            "quantity_units": qty,
            "units_per_strip": r.units_per_strip,
            "mrp": r.mrp,
            "stock_value": round(r.mrp * qty, 2),
        })

    return {
        "store_id": store_id,
        "days_threshold": days,
        "total_at_risk_value": round(float(totals.total_value), 2),
        "total_at_risk_units": int(totals.total_units),
        "pagination": pagination,
        "items": items,
    }


# ── 8. Fast-Moving Medicines ────────────────────────────

# Valid sort columns for fast-moving
_FAST_MOVING_SORT_FIELDS = {"quantity", "revenue", "orders"}


def get_fast_moving(
    db: Session,
    store_id: int,
    days: int = 30,
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "quantity",
    sort_order: str = "desc",
) -> dict:
    """Rank medicines by sales performance in the last ``days`` days.

    Aggregates OrderItem data joined with Order (filtered by store + date).
    Supports sorting by quantity_sold, revenue, or order_count.
    """
    _validate_store(db, store_id)

    if sort_by not in _FAST_MOVING_SORT_FIELDS:
        sort_by = "quantity"

    today = date.today()
    period_start = today - timedelta(days=days)

    base_filter = [
        Order.store_id == store_id,
        Order.created_at >= datetime.combine(period_start, datetime.min.time()),
    ]

    # ── Sort clause ──────────────────────────────────────
    qty_col = func.sum(OrderItem.quantity)
    rev_col = func.sum(OrderItem.subtotal)
    ord_col = func.count(func.distinct(OrderItem.order_id))

    sort_map = {
        "quantity": qty_col,
        "revenue": rev_col,
        "orders": ord_col,
    }
    order_col = sort_map[sort_by]
    if sort_order.lower() == "asc":
        order_col = order_col.asc()
    else:
        order_col = order_col.desc()

    # ── Total count of distinct medicines sold ───────────
    total_count = (
        db.query(func.count(func.distinct(OrderItem.medicine_id)))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(*base_filter)
        .scalar()
    ) or 0

    pagination = _paginate(total_count, page, page_size)

    if total_count == 0:
        return {
            "store_id": store_id,
            "days": days,
            "period_start": period_start,
            "period_end": today,
            "pagination": pagination,
            "items": [],
        }

    # ── Aggregated data (paginated) ──────────────────────
    offset = (page - 1) * page_size

    rows = (
        db.query(
            OrderItem.medicine_id,
            Medicine.name.label("medicine_name"),
            func.sum(OrderItem.quantity).label("total_quantity_sold"),
            func.sum(OrderItem.subtotal).label("total_revenue"),
            func.count(func.distinct(OrderItem.order_id)).label("order_count"),
        )
        .join(Order, OrderItem.order_id == Order.id)
        .join(Medicine, OrderItem.medicine_id == Medicine.id)
        .filter(*base_filter)
        .group_by(OrderItem.medicine_id, Medicine.name)
        .order_by(order_col)
        .offset(offset)
        .limit(page_size)
        .all()
    )

    items = []
    for idx, r in enumerate(rows, start=offset + 1):
        qty_sold = r.total_quantity_sold or 0
        orders = r.order_count or 1
        items.append({
            "rank": idx,
            "medicine_id": r.medicine_id,
            "medicine_name": r.medicine_name,
            "total_quantity_sold": qty_sold,
            "total_revenue": round(float(r.total_revenue or 0), 2),
            "order_count": orders,
            "avg_quantity_per_order": round(qty_sold / orders, 2),
        })

    return {
        "store_id": store_id,
        "days": days,
        "period_start": period_start,
        "period_end": today,
        "pagination": pagination,
        "items": items,
    }
