from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from dependencies.auth import get_current_user
from schemas.order_schema import (
    OrderCreate,
    OrderAddItems,
    OrderResponse,
    OrderAdminResponse,
    OrderTotalResponse,
    ProcessOrderRequest,
    ProcessOrderResponse,
    ProcessOrderAdminResponse,
    BatchAllocationResponse,
    BatchAllocationAdminResponse,
)
from services.billing_service import (
    create_order,
    add_items_to_order,
    get_order,
    get_order_total,
    list_orders,
)
from services.fefo_service import (
    get_available_batches,
    apply_fefo,
    calculate_total,
    reduce_stock,
)

router = APIRouter()


# ── helpers ──────────────────────────────────────────────

def _serialize_order(order, user: dict):
    """Serialize order based on user role."""
    if user["role"] == "admin":
        return OrderAdminResponse.model_validate(order)
    return OrderResponse.model_validate(order)


# ── existing endpoints ───────────────────────────────────

@router.get("/")
def read_orders(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List all orders."""
    orders = list_orders(db)
    if user["role"] == "admin":
        return [OrderAdminResponse.model_validate(o) for o in orders]
    return [OrderResponse.model_validate(o) for o in orders]


@router.post("/", status_code=201)
def place_order(
    data: OrderCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new order with items. Inventory is reduced automatically."""
    order = create_order(db, data)
    return _serialize_order(order, user)


@router.get("/{order_id}")
def read_order(
    order_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Get a single order with its items."""
    order = get_order(db, order_id)
    return _serialize_order(order, user)


@router.post("/{order_id}/items")
def add_items(
    order_id: int,
    data: OrderAddItems,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Add more items to an existing order. Inventory is reduced automatically."""
    order = add_items_to_order(db, order_id, data)
    return _serialize_order(order, user)


@router.get("/{order_id}/total", response_model=OrderTotalResponse)
def read_total(order_id: int, db: Session = Depends(get_db)):
    """Get the calculated total for an order."""
    return get_order_total(db, order_id)


# ── FEFO process endpoint ───────────────────────────────

@router.post("/process", status_code=200)
def process_order(
    data: ProcessOrderRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Process a single-medicine order using FEFO batch selection.

    Flow
    ----
    1. Fetch valid batches sorted by expiry (DB-level FEFO).
    2. Allocate required quantity across batches (earliest first).
    3. Calculate total using batch-level MRP (no weighted average).
    4. Deduct stock from consumed batches.
    5. Return role-based response:
       - **Worker**: batch_no, quantity, mrp
       - **Admin**: full details including purchase_price and profit

    Designed for future integration with pick-to-light, RFID tray,
    and gravity-based dispensing systems.
    """
    try:
        # 1. Fetch FEFO-sorted batches
        batches = get_available_batches(db, data.store_id, data.medicine_id)

        # 2. Build allocation plan (pure logic, no DB mutation)
        allocations = apply_fefo(batches, data.quantity)

        # 3. Calculate totals using batch-level MRP
        totals = calculate_total(allocations)

        # 4. Deduct stock
        reduce_stock(db, allocations)
        db.commit()

        # 5. Build role-based response
        if user["role"] == "admin":
            admin_allocs = [
                BatchAllocationAdminResponse(
                    batch_id=a["batch_id"],
                    batch_no=a["batch_no"],
                    expiry_date=a["expiry_date"],
                    mrp=a["mrp"],
                    purchase_price=a["purchase_price"],
                    quantity=a["allocated_qty"],
                    profit=round((a["mrp"] - a["purchase_price"]) * a["allocated_qty"], 2),
                )
                for a in allocations
            ]
            return ProcessOrderAdminResponse(
                medicine_id=data.medicine_id,
                total_quantity=totals["total_quantity"],
                total_price=totals["total_price"],
                total_cost=totals["total_purchase_cost"],
                total_profit=totals["total_profit"],
                allocations=admin_allocs,
            )
        else:
            worker_allocs = [
                BatchAllocationResponse(
                    batch_no=a["batch_no"],
                    quantity=a["allocated_qty"],
                    mrp=a["mrp"],
                )
                for a in allocations
            ]
            return ProcessOrderResponse(
                medicine_id=data.medicine_id,
                total_quantity=totals["total_quantity"],
                total_price=totals["total_price"],
                allocations=worker_allocs,
            )

    except Exception as exc:
        db.rollback()
        raise
