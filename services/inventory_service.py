from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.inventory import Inventory
from models.store import Store
from models.medicine import Medicine
from schemas.inventory_schema import InventoryCreate, InventoryUpdate


def _enrich_response(entry: Inventory) -> Inventory:
    """Attach computed strip/loose_unit fields to the ORM object for serialization."""
    ups = entry.units_per_strip or 10
    qu = entry.quantity_units or 0
    entry._strips = qu // ups
    entry._loose_units = qu % ups
    return entry


def _resolve_or_create_medicine(db: Session, medicine_name: str, units_per_strip: int) -> Medicine:
    """Find an existing medicine by name (case-insensitive) or create a new one.

    Uses ``ilike`` for case-insensitive matching so "Paracetamol" and
    "paracetamol" resolve to the same record.
    """
    medicine = (
        db.query(Medicine)
        .filter(Medicine.name.ilike(medicine_name))
        .first()
    )
    if medicine:
        return medicine

    # Auto-create with sensible defaults (price 0 — can be updated later)
    medicine = Medicine(
        name=medicine_name.strip().title(),
        price=0.0,
        units_per_strip=units_per_strip,
    )
    db.add(medicine)
    db.commit()
    db.refresh(medicine)
    return medicine


def create_inventory(db: Session, data: InventoryCreate):
    """Add a new inventory entry (store + medicine + batch).

    Resolves ``medicine_name`` to a medicine ID (auto-creates if new).
    Accepts strip-based input and converts to units internally:
        quantity_units = quantity (strips) × units_per_strip
    """
    # Validate store exists
    if not db.query(Store).filter(Store.id == data.store_id).first():
        raise HTTPException(status_code=404, detail="Store not found")

    # Resolve medicine by name (find or create)
    medicine = _resolve_or_create_medicine(db, data.medicine_name, data.units_per_strip)
    medicine_id = medicine.id

    # Check for duplicate (same store + medicine + batch)
    existing = (
        db.query(Inventory)
        .filter(
            Inventory.store_id == data.store_id,
            Inventory.medicine_id == medicine_id,
            Inventory.batch_no == data.batch_no,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Stock entry already exists for this store-medicine-batch combo. Use the update endpoint instead.",
        )

    # Convert strips → units
    quantity_units = data.quantity * data.units_per_strip

    entry = Inventory(
        store_id=data.store_id,
        medicine_id=medicine_id,
        quantity=data.quantity,                # strips (legacy)
        quantity_units=quantity_units,          # units (primary)
        units_per_strip=data.units_per_strip,
        batch_no=data.batch_no,
        expiry_date=data.expiry_date,
        mrp=data.mrp,
        purchase_price=data.purchase_price,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_inventory_by_medicine(db: Session, medicine_id: int):
    """Return all inventory entries for a given medicine, sorted by expiry (FEFO)."""
    records = (
        db.query(Inventory)
        .filter(Inventory.medicine_id == medicine_id)
        .order_by(Inventory.expiry_date.asc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="No stock found for this medicine")
    return records


def update_inventory(db: Session, inventory_id: int, data: InventoryUpdate):
    """Update stock of an existing inventory entry.

    Accepts either:
    - ``quantity`` (strips) → converts to units
    - ``quantity_units`` (units) → used directly
    """
    entry = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Inventory entry not found")

    ups = entry.units_per_strip or 10

    if data.quantity_units is not None:
        # Direct unit update
        entry.quantity_units = data.quantity_units
        entry.quantity = data.quantity_units // ups
    elif data.quantity is not None:
        # Strip-based update (legacy compat)
        entry.quantity = data.quantity
        entry.quantity_units = data.quantity * ups

    db.commit()
    db.refresh(entry)
    return entry
