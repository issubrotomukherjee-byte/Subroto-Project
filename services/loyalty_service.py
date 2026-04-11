from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.customer_loyalty import CustomerLoyalty
from models.loyalty_transaction import LoyaltyTransaction
from models.customer import Customer

# ── Tier thresholds & discounts ───────────────────────────

TIERS = [
    {"name": "Gold", "min_points": 2000, "discount_pct": 10},
    {"name": "Silver", "min_points": 500, "discount_pct": 5},
    {"name": "Bronze", "min_points": 0, "discount_pct": 0},
]

# Points earned per order = 1% of bill → 1 point per ₹100
POINTS_PER_RUPEE = 0.01

# Redemption rate: 1 point = ₹1
REDEMPTION_VALUE = 1.0


# ── Helpers ───────────────────────────────────────────────

def _calculate_tier(points: int) -> str:
    """Return the membership tier for a given point balance."""
    for tier in TIERS:
        if points >= tier["min_points"]:
            return tier["name"]
    return "Bronze"


def get_or_create_loyalty(db: Session, customer_id: int) -> CustomerLoyalty:
    """Return existing loyalty record or create a new one."""
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    loyalty = db.query(CustomerLoyalty).filter(CustomerLoyalty.customer_id == customer_id).first()
    if not loyalty:
        loyalty = CustomerLoyalty(customer_id=customer_id, points=0, membership_type="Bronze")
        db.add(loyalty)
        db.flush()
    return loyalty


# ── Public API ────────────────────────────────────────────

def add_points(db: Session, customer_id: int, order_total: float, order_id: int):
    """Award loyalty points for an order (1% of total). Auto-upgrades tier."""
    loyalty = get_or_create_loyalty(db, customer_id)

    earned = int(order_total * POINTS_PER_RUPEE)
    if earned <= 0:
        return loyalty

    loyalty.points += earned
    loyalty.membership_type = _calculate_tier(loyalty.points)

    txn = LoyaltyTransaction(
        loyalty_id=loyalty.id,
        points_added=earned,
        points_used=0,
        reason=f"Order #{order_id}",
    )
    db.add(txn)
    return loyalty


def redeem_points(db: Session, customer_id: int, points_to_redeem: int):
    """Redeem loyalty points. Returns info about the redemption."""
    loyalty = get_or_create_loyalty(db, customer_id)

    if points_to_redeem <= 0:
        raise HTTPException(status_code=400, detail="Points to redeem must be positive")
    if points_to_redeem > loyalty.points:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient points. Available: {loyalty.points}",
        )

    loyalty.points -= points_to_redeem
    loyalty.membership_type = _calculate_tier(loyalty.points)

    discount_amount = points_to_redeem * REDEMPTION_VALUE

    txn = LoyaltyTransaction(
        loyalty_id=loyalty.id,
        points_added=0,
        points_used=points_to_redeem,
        reason="Points redeemed",
    )
    db.add(txn)
    db.commit()
    db.refresh(loyalty)

    return {
        "customer_id": customer_id,
        "points_redeemed": points_to_redeem,
        "points_remaining": loyalty.points,
        "discount_amount": discount_amount,
        "message": f"₹{discount_amount:.2f} discount applied. Remaining: {loyalty.points} pts.",
    }


def get_loyalty_info(db: Session, customer_id: int):
    """Return current loyalty status for a customer."""
    loyalty = get_or_create_loyalty(db, customer_id)
    return {
        "customer_id": customer_id,
        "points": loyalty.points,
        "membership_type": loyalty.membership_type,
        "expiry": loyalty.expiry,
    }


def get_loyalty_transactions(db: Session, customer_id: int):
    """Return loyalty record with full transaction history."""
    loyalty = get_or_create_loyalty(db, customer_id)

    transactions = (
        db.query(LoyaltyTransaction)
        .filter(LoyaltyTransaction.loyalty_id == loyalty.id)
        .order_by(LoyaltyTransaction.created_at.desc())
        .all()
    )

    return {
        "customer_id": customer_id,
        "points": loyalty.points,
        "membership_type": loyalty.membership_type,
        "expiry": loyalty.expiry,
        "transactions": transactions,
    }


def get_membership_discount(db: Session, customer_id: int) -> float:
    """Return discount percentage based on membership tier."""
    loyalty = get_or_create_loyalty(db, customer_id)
    for tier in TIERS:
        if loyalty.membership_type == tier["name"]:
            return tier["discount_pct"]
    return 0.0
