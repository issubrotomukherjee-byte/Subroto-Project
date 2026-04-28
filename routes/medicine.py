from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from database.connection import get_db
from schemas.medicine_schema import MedicineCreate, MedicineResponse, MedicineSearchResponse, MedicineResolveResponse, MedicineSubstituteResponse, MedicineDetailsResponse
from schemas.salt_schema import CompositionResponse
from services.medicine_service import (
    list_medicines,
    get_medicine,
    search_medicines,
    add_medicine,
    resolve_medicine,
    get_substitutes_with_price,
    get_medicine_details,
)
from services.salt_service import (
    get_medicine_composition,
    search_medicine_by_name,
)

router = APIRouter()


@router.get("/", response_model=List[MedicineResponse])
def read_all(db: Session = Depends(get_db)):
    """Get all medicines."""
    return list_medicines(db)


@router.get("/search", response_model=List[MedicineSearchResponse])
def search(
    q: str = Query(..., min_length=1, description="Medicine name to search"),
    db: Session = Depends(get_db),
):
    """Search medicines by name (case-insensitive partial match).

    Returns top 10 results with ``id`` and ``name`` only — designed for
    frontend autocomplete / search-select workflows.
    """
    return search_medicines(db, q)


@router.get("/search-advanced", response_model=List[MedicineSearchResponse])
def advanced_search(
    q: str = Query(..., min_length=1, description="Search query"),
    db: Session = Depends(get_db),
):
    """Search medicines across name, salt fields.

    Returns lightweight results ``[{id, name}]`` for autocomplete.
    """
    return search_medicine_by_name(db, q)


@router.get("/resolve", response_model=List[MedicineResolveResponse])
def resolve_medicine_api(
    q: str = Query("", description="Medicine name to resolve"),
    db: Session = Depends(get_db),
):
    """Resolve medicine name → id for frontend autocomplete."""
    return resolve_medicine(db, q)


@router.get("/{medicine_id}/substitutes", response_model=List[MedicineSubstituteResponse])
def get_substitutes_api(medicine_id: int, db: Session = Depends(get_db)):
    """Get substitute medicines with selling-price comparison."""
    return get_substitutes_with_price(db, medicine_id)


@router.get("/{medicine_id}/details", response_model=MedicineDetailsResponse)
def get_medicine_details_api(medicine_id: int, db: Session = Depends(get_db)):
    """Get full medicine details: info, composition, price, and substitutes."""
    return get_medicine_details(db, medicine_id)


@router.get("/{medicine_id}", response_model=MedicineResponse)
def read_one(medicine_id: int, db: Session = Depends(get_db)):
    """Get a single medicine by ID."""
    return get_medicine(db, medicine_id)


@router.get("/{medicine_id}/composition", response_model=List[CompositionResponse])
def composition(medicine_id: int, db: Session = Depends(get_db)):
    """Get the salt composition of a medicine."""
    return get_medicine_composition(db, medicine_id)


@router.post("/", response_model=MedicineResponse, status_code=201)
def create(medicine: MedicineCreate, db: Session = Depends(get_db)):
    """Add a new medicine."""
    return add_medicine(db, medicine)
