from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.inventory import Inventory
from models.store import Store
from models.medicine import Medicine
from schemas.inventory_schema import InventoryCreate, InventoryUpdate


def add_stock(db: Session, data: InventoryCreate):
    """Add a new stock entry for a store-medicine pair.

    Accepts strip-based input and converts to units:
        quantity_units = quantity (strips) × units_per_strip
    """
    # Validate foreign keys
    if not db.query(Store).filter(Store.id == data.store_id).first():
        raise HTTPException(status_code=404, detail="Store not found")
    if not db.query(Medicine).filter(Medicine.id == data.medicine_id).first():
        raise HTTPException(status_code=404, detail="Medicine not found")

    # Check for duplicate (same store + medicine + batch)
    existing = (
        db.query(Inventory)
        .filter(
            Inventory.store_id == data.store_id,
            Inventory.medicine_id == data.medicine_id,
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
        medicine_id=data.medicine_id,
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


def get_stock_by_medicine(db: Session, medicine_id: int):
    """Return all stock entries across stores for a given medicine, sorted by expiry (FEFO)."""
    records = (
        db.query(Inventory)
        .filter(Inventory.medicine_id == medicine_id)
        .order_by(Inventory.expiry_date.asc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="No stock found for this medicine")
    return records


def update_stock(db: Session, inventory_id: int, data: InventoryUpdate):
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
        entry.quantity_units = data.quantity_units
        entry.quantity = data.quantity_units // ups
    elif data.quantity is not None:
        entry.quantity = data.quantity
        entry.quantity_units = data.quantity * ups

    db.commit()
    db.refresh(entry)
    return entry
