from datetime import date
from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.order import Order
from models.order_item import OrderItem
from models.order_item_batch import OrderItemBatch
from models.medicine import Medicine
from models.inventory import Inventory
from schemas.order_schema import OrderCreate, OrderAddItems, OrderItemCreate
from services.loyalty_service import add_points, get_membership_discount
from services.fefo_service import get_available_batches, apply_fefo, calculate_total, reduce_stock


# ── helpers ──────────────────────────────────────────────

def _resolve_units(db: Session, item: OrderItemCreate) -> int:
    """Resolve the final unit count for an order item.

    If ``strips`` is provided, looks up the medicine's units_per_strip
    to convert.  If ``units`` or ``quantity`` (legacy) is provided,
    uses that directly.
    """
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
    """Validate stock and deduct using FEFO via the modular fefo_service.

    All operations are in UNITS (tablets/capsules).

    Returns a dict with batch-level pricing aggregated across consumed
    batches::

        {
            "subtotal":            <sum of batch_mrp × units_from_that_batch>,
            "total_purchase_cost": <sum of batch_purchase_price × units_from_that_batch>,
            "first_batch_mrp":     <mrp of earliest-expiry batch consumed>,
        }
    """
    # 1. Fetch FEFO-sorted batches
    batches = get_available_batches(db, store_id, medicine_id)

    # 2. Build allocation plan in units (pure logic, no DB mutation)
    allocations = apply_fefo(batches, required_units)

    # 3. Calculate totals using batch-level MRP
    totals = calculate_total(allocations)

    # 4. Deduct stock from inventory (quantity_units)
    reduce_stock(db, allocations)

    # 5. Create audit records (which batch supplied how many units)
    for alloc in allocations:
        db.add(OrderItemBatch(
            order_item_id=order_item.id,
            inventory_id=alloc["batch_id"],
            quantity=alloc["allocated_qty"],    # in units
        ))

    return {
        "subtotal": totals["total_price"],
        "total_purchase_cost": totals["total_purchase_cost"],
        "first_batch_mrp": allocations[0]["mrp"],
    }


def _add_items_to_order(db: Session, order: Order, items: list[OrderItemCreate]):
    """Append items to an order, deduct inventory (FEFO), and update total.

    Accepts input in units, strips, or legacy quantity.
    All internal processing is in UNITS.
    """
    for item in items:
        # Resolve to units
        required_units = _resolve_units(db, item)

        # Create the order item first so we have its id for batch records.
        # Placeholder values are overwritten after inventory deduction.
        order_item = OrderItem(
            order_id=order.id,
            medicine_id=item.medicine_id,
            quantity=required_units,      # stored in UNITS
            unit_price=0.0,
            subtotal=0.0,
            mrp=0.0,
            purchase_price=0.0,
            discount_applied=0.0,
            final_price=0.0,
            profit=0.0,
        )
        db.add(order_item)
        db.flush()  # populate order_item.id

        # Deduct inventory and create batch audit records
        pricing = _deduct_inventory(
            db, order.store_id, item.medicine_id, required_units, order_item,
        )

        # Fill in pricing from batch-level data
        order_item.unit_price = pricing["first_batch_mrp"]
        order_item.subtotal = pricing["subtotal"]
        order_item.mrp = pricing["first_batch_mrp"]
        order_item.purchase_price = pricing["total_purchase_cost"] / required_units
        order_item.discount_applied = 0.0
        order_item.final_price = pricing["subtotal"]
        order_item.profit = pricing["subtotal"] - pricing["total_purchase_cost"]

        order.total_amount += pricing["subtotal"]

    return order


# ── public API ───────────────────────────────────────────

def create_order(db: Session, data: OrderCreate):
    """Create a new order with initial items. Inventory is deducted automatically.
    If customer_id is provided:
      - Membership discount is applied to the total.
      - Loyalty points (1% of final total) are awarded.

    The entire operation is wrapped in a transaction: if any step
    fails (insufficient stock, expired-only batches, etc.) ALL
    database changes are rolled back.
    """
    try:
        order = Order(
            store_id=data.store_id,
            customer_id=data.customer_id,
            total_amount=0.0,
        )
        db.add(order)
        db.flush()  # populate order.id

        _add_items_to_order(db, order, data.items)

        # ── Loyalty integration ──────────────────────────────
        if data.customer_id:
            # Apply membership discount
            discount_pct = get_membership_discount(db, data.customer_id)
            if discount_pct > 0:
                discount_amt = order.total_amount * (discount_pct / 100)
                order.total_amount -= discount_amt

                # Distribute discount proportionally across items
                for oi in order.items:
                    item_share = (oi.subtotal / (order.total_amount + discount_amt)) * discount_amt
                    oi.discount_applied = round(item_share, 2)
                    oi.final_price = round(oi.subtotal - oi.discount_applied, 2)
                    oi.profit = round(oi.final_price - (oi.purchase_price * oi.quantity), 2)

            # Award loyalty points (1% of final total)
            add_points(db, data.customer_id, order.total_amount, order.id)

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

        _add_items_to_order(db, order, data.items)
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
