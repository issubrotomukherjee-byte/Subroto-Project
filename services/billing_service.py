"""
Production-grade billing service.

Flow:
  1. Resolve customer from phone (auto-find / auto-create)
  2. Load admin-configured billing settings
  3. For each item: resolve units → FEFO allocate → deduct stock → record
  4. Compute subtotal (sum of item MRP totals)
  5. Apply admin-configured discount %
  6. Apply loyalty redemption (capped by settings)
  7. Compute net_amount (final payable)
  8. Earn loyalty points on net_amount
  9. Save everything in a single DB transaction
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.order import Order
from models.order_item import OrderItem
from models.order_item_batch import OrderItemBatch
from models.medicine import Medicine
from models.store import Store

from schemas.order_schema import OrderCreate, OrderAddItems, OrderItemCreate

from services.billing_settings_service import get_settings
from services.customer_service import find_or_create_by_phone
from services.loyalty_service import (
    add_points,
    redeem_points_for_order,
    get_or_create_loyalty,
    REDEMPTION_VALUE,
)
from services.fefo_service import (
    get_available_batches,
    apply_fefo,
    calculate_total,
    reduce_stock,
)


# ── helpers ──────────────────────────────────────────────

def _resolve_units(db: Session, item: OrderItemCreate) -> int:
    """Resolve the final unit count for an order item."""
    medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
    if not medicine:
        raise HTTPException(
            status_code=404,
            detail=f"Medicine {item.medicine_id} not found",
        )
    return item.get_units(medicine.units_per_strip)


def _deduct_inventory(
    db: Session,
    store_id: int,
    medicine_id: int,
    required_units: int,
    order_item: OrderItem,
) -> dict:
    """Validate stock and deduct using FEFO.  All operations in UNITS.

    Returns::
        {
            "subtotal":            <sum of batch_mrp × units>,
            "total_purchase_cost": <sum of batch_purchase_price × units>,
            "first_batch_mrp":     <mrp of earliest-expiry batch consumed>,
        }
    """
    batches = get_available_batches(db, store_id, medicine_id)
    allocations = apply_fefo(batches, required_units)
    totals = calculate_total(allocations)
    reduce_stock(db, allocations)

    for alloc in allocations:
        db.add(OrderItemBatch(
            order_item_id=order_item.id,
            inventory_id=alloc["batch_id"],
            quantity=alloc["allocated_qty"],
        ))

    return {
        "subtotal": totals["total_price"],
        "total_purchase_cost": totals["total_purchase_cost"],
        "first_batch_mrp": allocations[0]["mrp"],
    }


def _add_items_to_order(db: Session, order: Order, items: list[OrderItemCreate]) -> float:
    """Append items to an order, deduct inventory (FEFO), update item pricing.

    Returns the raw subtotal (sum of MRP-based item totals) for the added items.
    """
    items_subtotal = 0.0

    for item in items:
        required_units = _resolve_units(db, item)

        order_item = OrderItem(
            order_id=order.id,
            medicine_id=item.medicine_id,
            quantity=required_units,
            unit_price=0.0,
            subtotal=0.0,
            mrp=0.0,
            purchase_price=0.0,
            discount_applied=0.0,
            final_price=0.0,
            profit=0.0,
        )
        db.add(order_item)
        db.flush()

        pricing = _deduct_inventory(
            db, order.store_id, item.medicine_id, required_units, order_item,
        )

        order_item.unit_price = pricing["first_batch_mrp"]
        order_item.subtotal = pricing["subtotal"]
        order_item.mrp = pricing["first_batch_mrp"]
        order_item.purchase_price = pricing["total_purchase_cost"] / required_units
        order_item.final_price = pricing["subtotal"]
        order_item.profit = pricing["subtotal"] - pricing["total_purchase_cost"]

        items_subtotal += pricing["subtotal"]

    return items_subtotal


# ── public API ───────────────────────────────────────────

def create_order(db: Session, data: OrderCreate):
    """Create a new order with full production billing logic.

    1. Resolve customer from phone
    2. FEFO stock deduction for each item
    3. Apply admin-configured discount
    4. Apply loyalty redemption (capped)
    5. Earn loyalty points on net payable
    6. Single transaction — all-or-nothing
    """
    try:
        # ── 1. Load billing settings ────────────────────
        settings = get_settings(db)

        # ── 2. Resolve customer ─────────────────────────
        customer_id = None
        if data.customer_phone:
            customer = find_or_create_by_phone(db, data.customer_phone)
            customer_id = customer.id

        # ── 3. Create order shell ───────────────────────
        order = Order(
            store_id=data.store_id,
            customer_id=customer_id,
            payment_method=data.payment_method,
            total_amount=0.0,
        )
        db.add(order)
        db.flush()

        # ── 4. Add items + FEFO deduction ───────────────
        subtotal = _add_items_to_order(db, order, data.items)

        # ── 5. Apply admin-configured discount ──────────
        discount_pct = settings.default_medicine_discount_percent
        discount_amt = round(subtotal * (discount_pct / 100), 2)
        after_discount = round(subtotal - discount_amt, 2)

        # Distribute discount proportionally across items
        if discount_amt > 0 and subtotal > 0:
            for oi in order.items:
                item_share = round((oi.subtotal / subtotal) * discount_amt, 2)
                oi.discount_applied = item_share
                oi.final_price = round(oi.subtotal - item_share, 2)
                oi.profit = round(oi.final_price - (oi.purchase_price * oi.quantity), 2)

        # ── 6. Apply loyalty redemption (if requested) ──
        loyalty_points_redeemed = 0
        loyalty_discount = 0.0

        if data.redeem_loyalty_points and data.redeem_loyalty_points > 0 and customer_id:
            max_redemption_pct = settings.max_loyalty_redemption_percent
            max_discount = round(after_discount * (max_redemption_pct / 100), 2)

            result = redeem_points_for_order(
                db, customer_id, data.redeem_loyalty_points, max_discount, order.id,
            )
            loyalty_points_redeemed = result["points_redeemed"]
            loyalty_discount = result["discount_amount"]

        # ── 7. Compute net amount ───────────────────────
        net_amount = round(after_discount - loyalty_discount, 2)

        # ── 8. Earn loyalty points on net payable ───────
        loyalty_points_earned = 0
        if customer_id:
            loyalty_credit_pct = settings.loyalty_credit_percent
            earned = int(net_amount * (loyalty_credit_pct / 100))
            if earned > 0:
                add_points(db, customer_id, net_amount, order.id)
                loyalty_points_earned = earned

        # ── 9. Save order totals ────────────────────────
        order.subtotal = subtotal
        order.discount_percent = discount_pct
        order.discount_amount = discount_amt
        order.loyalty_points_redeemed = loyalty_points_redeemed
        order.loyalty_discount = loyalty_discount
        order.net_amount = net_amount
        order.total_amount = net_amount  # backward compat
        order.loyalty_points_earned = loyalty_points_earned

        # ── 10. Commit ──────────────────────────────────
        db.commit()
        db.refresh(order)
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def add_items_to_order(db: Session, order_id: int, data: OrderAddItems):
    """Add more items to an existing order. Inventory is deducted automatically."""
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        added_subtotal = _add_items_to_order(db, order, data.items)
        order.subtotal = (order.subtotal or 0.0) + added_subtotal
        order.total_amount = (order.total_amount or 0.0) + added_subtotal
        order.net_amount = (order.net_amount or 0.0) + added_subtotal
        db.commit()
        db.refresh(order)
        return order

    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_order(db: Session, order_id: int):
    """Return a single order with its items."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def get_order_total(db: Session, order_id: int):
    """Return the calculated total for an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {
        "order_id": order.id,
        "total_amount": order.total_amount,
        "item_count": len(order.items),
    }


def list_orders(db: Session):
    """Return all orders."""
    return db.query(Order).all()


def get_invoice(db: Session, order_id: int) -> dict:
    """Build a printable invoice response for an order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Store info
    store = db.query(Store).filter(Store.id == order.store_id).first()
    store_name = store.name if store else "Unknown"
    store_address = store.address if store else None
    store_phone = store.phone if store else None

    # Customer info
    customer_name = None
    customer_phone = None
    if order.customer and order.customer_id:
        from models.customer import Customer
        cust = db.query(Customer).filter(Customer.id == order.customer_id).first()
        if cust:
            customer_name = cust.name
            customer_phone = cust.phone

    # Items
    items = []
    for oi in order.items:
        med = db.query(Medicine).filter(Medicine.id == oi.medicine_id).first()
        items.append({
            "medicine_name": med.name if med else f"Medicine #{oi.medicine_id}",
            "quantity": oi.quantity,
            "unit_price": oi.mrp,
            "subtotal": oi.subtotal,
        })

    return {
        "order_id": order.id,
        "store_name": store_name,
        "store_address": store_address,
        "store_phone": store_phone,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "payment_method": order.payment_method or "cash",
        "items": items,
        "subtotal": order.subtotal or 0.0,
        "discount_percent": order.discount_percent or 0.0,
        "discount_amount": order.discount_amount or 0.0,
        "loyalty_points_redeemed": order.loyalty_points_redeemed or 0,
        "loyalty_discount": order.loyalty_discount or 0.0,
        "net_amount": order.net_amount or 0.0,
        "loyalty_points_earned": order.loyalty_points_earned or 0,
        "created_at": order.created_at,
    }
