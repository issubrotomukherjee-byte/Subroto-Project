from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database.connection import get_db
from schemas.medicine_schema import MedicineCreate, MedicineResponse
from services.medicine_service import (
    list_medicines,
    get_medicine,
    search_medicines,
    add_medicine,
)

router = APIRouter()


@router.get("/", response_model=List[MedicineResponse])
def read_all(db: Session = Depends(get_db)):
    """Get all medicines."""
    return list_medicines(db)


@router.get("/search", response_model=List[MedicineResponse])
def search(name: str = Query(..., min_length=1, description="Medicine name to search"), db: Session = Depends(get_db)):
    """Search medicines by name (case-insensitive partial match)."""
    return search_medicines(db, name)


@router.get("/{medicine_id}", response_model=MedicineResponse)
def read_one(medicine_id: int, db: Session = Depends(get_db)):
    """Get a single medicine by ID."""
    return get_medicine(db, medicine_id)


@router.post("/", response_model=MedicineResponse, status_code=201)
def create(medicine: MedicineCreate, db: Session = Depends(get_db)):
    """Add a new medicine."""
    return add_medicine(db, medicine)
