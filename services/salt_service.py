from sqlalchemy.orm import Session
from fastapi import HTTPException

from models.salt import Salt
from models.medicine_salt import MedicineSalt
from models.medicine import Medicine
from schemas.salt_schema import SaltCreate, MedicineSaltCreate


# ── Salt CRUD ────────────────────────────────────────────────────────────

def create_salt(db: Session, data: SaltCreate) -> Salt:
    """Create a new salt; rejects duplicate names."""
    existing = db.query(Salt).filter(Salt.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Salt '{data.name}' already exists",
        )
    salt = Salt(name=data.name)
    db.add(salt)
    db.commit()
    db.refresh(salt)
    return salt


# ── MedicineSalt CRUD ────────────────────────────────────────────────────

def create_medicine_salt(db: Session, data: MedicineSaltCreate) -> MedicineSalt:
    """Link a salt to a medicine with optional per-salt strength."""
    # Validate medicine exists
    medicine = db.query(Medicine).filter(Medicine.id == data.medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")

    # Validate salt exists
    salt = db.query(Salt).filter(Salt.id == data.salt_id).first()
    if not salt:
        raise HTTPException(status_code=404, detail="Salt not found")

    link = MedicineSalt(**data.model_dump())
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


# ── Composition query ────────────────────────────────────────────────────

def get_medicine_composition(db: Session, medicine_id: int):
    """Return list of {salt_name, strength} for a medicine."""
    # Validate medicine exists
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")

    rows = (
        db.query(MedicineSalt, Salt)
        .join(Salt, MedicineSalt.salt_id == Salt.id)
        .filter(MedicineSalt.medicine_id == medicine_id)
        .all()
    )
    return [
        {"salt_name": salt.name, "strength": ms.strength}
        for ms, salt in rows
    ]


# ── Advanced search ──────────────────────────────────────────────────────

def search_medicine_by_name(db: Session, query: str, limit: int = 10):
    """Search medicines across name, brand_name, manufacturer, and salt.

    Returns lightweight results (id + name) for autocomplete.
    """
    pattern = f"%{query}%"
    return (
        db.query(Medicine)
        .filter(
            Medicine.name.ilike(pattern)
            | Medicine.brand_name.ilike(pattern)
            | Medicine.manufacturer.ilike(pattern)
            | Medicine.salt.ilike(pattern)
        )
        .order_by(Medicine.name)
        .limit(limit)
        .all()
    )
