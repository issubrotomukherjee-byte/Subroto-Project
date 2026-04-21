from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.connection import get_db
from dependencies.auth import get_current_user, require_admin
from models.medicine import Medicine
from schemas.order_schema import (
    OrderCreate,
    OrderAddItems,
    OrderResponse,
    OrderAdminResponse,
    OrderTotalResponse,
    InvoiceResponse,
    ProcessOrderRequest,
    ProcessOrderResponse,
    ProcessOrderAdminResponse,
    BatchAllocationResponse,
    BatchAllocationAdminResponse,
)
from schemas.billing_settings_schema import (
    BillingSettingsUpdate,
    BillingSettingsResponse,
    BillingSettingsAuditListResponse,
)
from services.billing_service import (
    create_order,
    add_items_to_order,
    get_order,
    get_order_total,
    list_orders,
    get_invoice,
)
from services.billing_settings_service import (
    get_settings,
    update_settings,
    get_audit_log,
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


# ── Settings endpoints (admin-only) ─────────────────────

@router.get("/settings", response_model=BillingSettingsResponse)
def read_settings(db: Session = Depends(get_db)):
    """View current billing settings (any role)."""
    return get_settings(db)


@router.put("/settings", response_model=BillingSettingsResponse)
def update_billing_settings(
    data: BillingSettingsUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Update billing settings. Admin-only. Fully audited."""
    require_admin(user)
    admin_name = user.get("name", "admin")
    return update_settings(db, data, admin_name)


@router.get("/settings/audit", response_model=BillingSettingsAuditListResponse)
def read_settings_audit(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """View full audit trail of billing settings changes. Admin-only."""
    require_admin(user)
    audits = get_audit_log(db)
    return {"audits": audits}


# ── Order endpoints ─────────────────────────────────────

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
    """Place a new order with production-grade billing.

    - Auto-resolves or creates customer from ``customer_phone``
    - Applies admin-configured discount from billing settings
    - Redeems loyalty points (capped by ``max_loyalty_redemption_percent``)
    - Earns loyalty points on final payable
    - Uses FEFO stock deduction from inventory batches
    - Prevents sale if insufficient stock
    """
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


@router.get("/{order_id}/invoice", response_model=InvoiceResponse)
def read_invoice(order_id: int, db: Session = Depends(get_db)):
    """Return printable invoice JSON for an order."""
    return get_invoice(db, order_id)


# ── FEFO process endpoint ───────────────────────────────

@router.post("/process", status_code=200)
def process_order(
    data: ProcessOrderRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Process a single-medicine order using FEFO batch selection.

    Accepts ``units``, ``strips``, or ``quantity`` (legacy, = units).
    Response includes strip/loose_unit breakdown per batch.
    Worker sees only batch_no, units, strips, mrp.
    Admin sees full pricing including purchase_price and profit.
    """
    try:
        medicine = db.query(Medicine).filter(Medicine.id == data.medicine_id).first()
        if not medicine:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Medicine {data.medicine_id} not found")

        required_units = data.get_units(medicine.units_per_strip)

        batches = get_available_batches(db, data.store_id, data.medicine_id)
        allocations = apply_fefo(batches, required_units)
        totals = calculate_total(allocations)
        reduce_stock(db, allocations)
        db.commit()

        total_units = totals["total_quantity"]
        ups_display = medicine.units_per_strip
        total_strips = total_units // ups_display
        total_loose = total_units % ups_display

        if user["role"] == "admin":
            admin_allocs = [
                BatchAllocationAdminResponse(
                    batch_id=a["batch_id"],
                    batch_no=a["batch_no"],
                    expiry_date=a["expiry_date"],
                    mrp=a["mrp"],
                    purchase_price=a["purchase_price"],
                    units=a["allocated_qty"],
                    strips=a["allocated_qty"] // a["units_per_strip"],
                    loose_units=a["allocated_qty"] % a["units_per_strip"],
                    profit=round((a["mrp"] - a["purchase_price"]) * a["allocated_qty"], 2),
                )
                for a in allocations
            ]
            return ProcessOrderAdminResponse(
                medicine_id=data.medicine_id,
                total_units=total_units,
                total_strips=total_strips,
                total_loose_units=total_loose,
                total_price=totals["total_price"],
                total_cost=totals["total_purchase_cost"],
                total_profit=totals["total_profit"],
                allocations=admin_allocs,
            )
        else:
            worker_allocs = [
                BatchAllocationResponse(
                    batch_no=a["batch_no"],
                    units=a["allocated_qty"],
                    strips=a["allocated_qty"] // a["units_per_strip"],
                    loose_units=a["allocated_qty"] % a["units_per_strip"],
                    mrp=a["mrp"],
                )
                for a in allocations
            ]
            return ProcessOrderResponse(
                medicine_id=data.medicine_id,
                total_units=total_units,
                total_strips=total_strips,
                total_loose_units=total_loose,
                total_price=totals["total_price"],
                allocations=worker_allocs,
            )

    except Exception:
        db.rollback()
        raise
