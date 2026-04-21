from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime


# ── Request ──────────────────────────────────────────────

class BillingSettingsUpdate(BaseModel):
    """Only admin can send this.  All fields optional — partial update."""
    default_medicine_discount_percent: Optional[float] = None
    loyalty_credit_percent: Optional[float] = None
    max_loyalty_redemption_percent: Optional[float] = None

    @field_validator("default_medicine_discount_percent", "loyalty_credit_percent", "max_loyalty_redemption_percent")
    @classmethod
    def must_be_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Value must be >= 0")
        return v

    @field_validator("default_medicine_discount_percent", "max_loyalty_redemption_percent")
    @classmethod
    def must_be_at_most_100(cls, v):
        if v is not None and v > 100:
            raise ValueError("Value must be <= 100")
        return v


# ── Response ─────────────────────────────────────────────

class BillingSettingsResponse(BaseModel):
    default_medicine_discount_percent: float
    loyalty_credit_percent: float
    max_loyalty_redemption_percent: float
    updated_by_admin: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BillingSettingsAuditResponse(BaseModel):
    id: int
    default_medicine_discount_percent: float
    loyalty_credit_percent: float
    max_loyalty_redemption_percent: float
    changed_by: str
    changed_at: Optional[datetime] = None
    action: str

    class Config:
        from_attributes = True


class BillingSettingsAuditListResponse(BaseModel):
    audits: List[BillingSettingsAuditResponse]
