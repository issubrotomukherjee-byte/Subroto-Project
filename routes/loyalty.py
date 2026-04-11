from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database.connection import get_db
from schemas.loyalty_schema import (
    LoyaltyResponse,
    LoyaltyDetailResponse,
    RedeemPointsRequest,
    RedeemPointsResponse,
)
from services.loyalty_service import (
    get_loyalty_info,
    get_loyalty_transactions,
    redeem_points,
)

router = APIRouter()


@router.get("/{customer_id}", response_model=LoyaltyResponse)
def read_loyalty(customer_id: int, db: Session = Depends(get_db)):
    """View current loyalty points and membership tier."""
    return get_loyalty_info(db, customer_id)


@router.get("/{customer_id}/transactions", response_model=LoyaltyDetailResponse)
def read_transactions(customer_id: int, db: Session = Depends(get_db)):
    """View loyalty transaction history."""
    return get_loyalty_transactions(db, customer_id)


@router.post("/{customer_id}/redeem", response_model=RedeemPointsResponse)
def redeem(customer_id: int, data: RedeemPointsRequest, db: Session = Depends(get_db)):
    """Redeem loyalty points for a discount. 1 point = ₹1."""
    return redeem_points(db, customer_id, data.points)
