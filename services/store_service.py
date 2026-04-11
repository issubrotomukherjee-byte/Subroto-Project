from sqlalchemy.orm import Session
from models.store import Store
from schemas.store_schema import StoreCreate


def list_stores(db: Session):
    """Return all stores."""
    return db.query(Store).all()


def add_store(db: Session, data: StoreCreate):
    """Create a new store record."""
    store = Store(**data.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store
