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


# ── helpers ──────────────────────────────────────────────

def _deduct_inventory(
    db: Session,
    store_id: int,
    item: OrderItemCreate,
    order_item: OrderItem,
) -> float:
    """Validate stock and deduct using FEFO (First Expiry, First Out).

    Rules
    -----
    1. Expired batches (expiry_date < today) are excluded.
    2. Remaining valid batches are consumed earliest-expiry-first.
    3. If the requested quantity spans multiple batches, the deduction
       is split across them automatically.
    4. Every individual batch deduction is recorded in `order_item_batches`
       for return processing and audit.
    5. Raises HTTP 400 if total valid stock is insufficient.
    """
    medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
    if not medicine:
        raise HTTPException(
            status_code=404,
            detail=f"Medicine {item.medicine_id} not found",
        )

    today = date.today()

    # Get all NON-EXPIRED, in-stock batches sorted by expiry (earliest first)
    batches = (
        db.query(Inventory)
        .filter(
            Inventory.store_id == store_id,
            Inventory.medicine_id == item.medicine_id,
            Inventory.quantity > 0,
            Inventory.expiry_date >= today,          # ← skip expired stock
        )
        .order_by(Inventory.expiry_date.asc())
        .all()
    )

    total_available = sum(b.quantity for b in batches)
    if total_available < item.quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Insufficient valid stock for medicine {item.medicine_id}. "
                f"Requested {item.quantity}, available (non-expired) {total_available}."
            ),
        )

    # Deduct from earliest-expiry batches first, recording each split
    remaining = item.quantity
    for batch in batches:
        if remaining <= 0:
            break

        deduct = min(batch.quantity, remaining)
        batch.quantity -= deduct
        remaining -= deduct

        # Audit record: which batch supplied how many units
        db.add(OrderItemBatch(
            order_item_id=order_item.id,
            inventory_id=batch.id,
            quantity=deduct,
        ))

    subtotal = medicine.price * item.quantity
    return subtotal


def _add_items_to_order(db: Session, order: Order, items: list[OrderItemCreate]):
    """Append items to an order, deduct inventory (FEFO), and update total."""
    for item in items:
        medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        if not medicine:
            raise HTTPException(
                status_code=404,
                detail=f"Medicine {item.medicine_id} not found",
            )

        # Create the order item first so we have its id for batch records
        order_item = OrderItem(
            order_id=order.id,
            medicine_id=item.medicine_id,
            quantity=item.quantity,
            unit_price=medicine.price,
            subtotal=medicine.price * item.quantity,
        )
        db.add(order_item)
        db.flush()  # populate order_item.id

        # Deduct inventory and create batch audit records
        subtotal = _deduct_inventory(db, order.store_id, item, order_item)
        order_item.subtotal = subtotal
        order.total_amount += subtotal

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

