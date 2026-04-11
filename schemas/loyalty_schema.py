from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date


# --- Response schemas ---

class LoyaltyResponse(BaseModel):
    customer_id: int
    points: int
    membership_type: str
    expiry: Optional[date] = None

    class Config:
        from_attributes = True


class LoyaltyTransactionResponse(BaseModel):
    id: int
    points_added: int
    points_used: int
    reason: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class LoyaltyDetailResponse(BaseModel):
    customer_id: int
    points: int
    membership_type: str
    expiry: Optional[date] = None
    transactions: List[LoyaltyTransactionResponse] = []


# --- Request schemas ---

class RedeemPointsRequest(BaseModel):
    points: int


class RedeemPointsResponse(BaseModel):
    customer_id: int
    points_redeemed: int
    points_remaining: int
    discount_amount: float
    message: str
