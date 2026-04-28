from pydantic import BaseModel
from typing import Optional


# ── Salt ─────────────────────────────────────────────────────────────────

class SaltCreate(BaseModel):
    name: str


class SaltResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True


# ── MedicineSalt ─────────────────────────────────────────────────────────

class MedicineSaltCreate(BaseModel):
    medicine_id: int
    salt_id: int
    strength: Optional[str] = None


class MedicineSaltResponse(BaseModel):
    id: int
    medicine_id: int
    salt_id: int
    strength: Optional[str] = None

    class Config:
        from_attributes = True


# ── Composition (read-only) ─────────────────────────────────────────────

class CompositionResponse(BaseModel):
    salt_name: str
    strength: Optional[str] = None
