from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.inventory import Inventory
from models.store import Store
from models.medicine import Medicine
from schemas.inventory_schema import InventoryCreate, InventoryUpdate


def add_stock(db: Session, data: InventoryCreate):
    """Add a new stock entry for a store-medicine pair."""
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

    entry = Inventory(**data.model_dump())
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
    """Update the quantity of an existing stock entry."""
    entry = db.query(Inventory).filter(Inventory.id == inventory_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Inventory entry not found")

    entry.quantity = data.quantity
    db.commit()
    db.refresh(entry)
    return entry
