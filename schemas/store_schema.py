from pydantic import BaseModel
from typing import Optional


class StoreCreate(BaseModel):
    name: str
    location: Optional[str] = None


class StoreResponse(BaseModel):
    id: int
    name: str
    location: Optional[str] = None

    class Config:
        from_attributes = True
