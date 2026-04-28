from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database.connection import get_db
from schemas.salt_schema import (
    SaltCreate,
    SaltResponse,
    MedicineSaltCreate,
    MedicineSaltResponse,
)
from services.salt_service import create_salt, create_medicine_salt

router = APIRouter()


# ── Salt endpoints ───────────────────────────────────────────────────────

@router.post("/", response_model=SaltResponse, status_code=201)
def add_salt(data: SaltCreate, db: Session = Depends(get_db)):
    """Create a new pharmaceutical salt."""
    return create_salt(db, data)


# ── MedicineSalt endpoints ───────────────────────────────────────────────

medicine_salt_router = APIRouter()


@medicine_salt_router.post("/", response_model=MedicineSaltResponse, status_code=201)
def add_medicine_salt(data: MedicineSaltCreate, db: Session = Depends(get_db)):
    """Link a salt to a medicine with per-salt strength."""
    return create_medicine_salt(db, data)
