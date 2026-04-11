from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.medicine import Medicine
from schemas.medicine_schema import MedicineCreate


def list_medicines(db: Session):
    """Return all medicines."""
    return db.query(Medicine).all()


def get_medicine(db: Session, medicine_id: int):
    """Return a single medicine by ID."""
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


def search_medicines(db: Session, name: str):
    """Case-insensitive partial match on medicine name."""
    return (
        db.query(Medicine)
        .filter(Medicine.name.ilike(f"%{name}%"))
        .all()
    )


def add_medicine(db: Session, data: MedicineCreate):
    """Create a new medicine record."""
    medicine = Medicine(**data.model_dump())
    db.add(medicine)
    db.commit()
    db.refresh(medicine)
    return medicine
