from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database.connection import get_db
from schemas.store_schema import StoreCreate, StoreResponse
from services.store_service import list_stores, add_store

router = APIRouter()


@router.get("/", response_model=List[StoreResponse])
def read_all(db: Session = Depends(get_db)):
    """Get all stores."""
    return list_stores(db)


@router.post("/", response_model=StoreResponse, status_code=201)
def create(store: StoreCreate, db: Session = Depends(get_db)):
    """Create a new store."""
    return add_store(db, store)
