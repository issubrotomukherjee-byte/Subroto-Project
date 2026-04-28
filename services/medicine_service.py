from sqlalchemy.orm import Session
from sqlalchemy import case, func, desc
from fastapi import HTTPException
from models.medicine import Medicine
from models.medicine_salt import MedicineSalt
from models.purchase import Purchase, PurchaseItem
from schemas.medicine_schema import MedicineCreate


def list_medicines(db: Session):
    """Return all medicines."""
    return db.query(Medicine).all()


def get_medicine(db: Session, medicine_id: int):
    """Return a single medicine by ID."""
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


def search_medicines(db: Session, name: str, limit: int = 10):
    """Case-insensitive partial match on name, brand_name, manufacturer.

    Returns at most ``limit`` results, ordered alphabetically.
    """
    pattern = f"%{name}%"
    return (
        db.query(Medicine)
        .filter(
            Medicine.name.ilike(pattern)
            | Medicine.brand_name.ilike(pattern)
            | Medicine.manufacturer.ilike(pattern)
        )
        .order_by(Medicine.name)
        .limit(limit)
        .all()
    )


def add_medicine(db: Session, data: MedicineCreate):
    """Create a new medicine record."""
    medicine = Medicine(**data.model_dump())
    db.add(medicine)
    db.commit()
    db.refresh(medicine)
    return medicine


def resolve_medicine(db: Session, query: str, limit: int = 10):
    """Resolve a medicine name to id for frontend autocomplete.

    Returns at most ``limit`` results sorted with exact matches first.
    """
    query = query.strip()
    if len(query) < 2:
        return []

    pattern = f"%{query}%"
    return (
        db.query(Medicine)
        .filter(
            Medicine.name.ilike(pattern)
            | Medicine.brand_name.ilike(pattern)
            | Medicine.manufacturer.ilike(pattern)
        )
        .distinct()
        .order_by(
            case(
                (func.lower(Medicine.name) == query.lower(), 0),
                else_=1,
            ),
            Medicine.name.asc(),
        )
        .limit(limit)
        .all()
    )


# ── Substitutes ──────────────────────────────────────────────────────────

def _get_latest_mrp(db: Session, medicine_id: int):
    """Return the latest MRP for a medicine from purchase items."""
    row = (
        db.query(PurchaseItem.mrp)
        .join(Purchase, PurchaseItem.purchase_id == Purchase.id)
        .filter(PurchaseItem.medicine_id == medicine_id)
        .order_by(
            desc(Purchase.invoice_date),
            desc(Purchase.created_at),
        )
        .first()
    )
    return row[0] if row else None


def get_substitutes_with_price(db: Session, medicine_id: int):
    """Find substitute medicines sharing the exact same salt composition.

    Returns up to 10 substitutes with selling-price comparison.
    """
    # 1. Validate medicine exists
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")

    # 2. Get composition of the reference medicine: set of (salt_id, strength)
    ref_salts = (
        db.query(MedicineSalt.salt_id, MedicineSalt.strength)
        .filter(MedicineSalt.medicine_id == medicine_id)
        .all()
    )
    if not ref_salts:
        return []

    ref_set = {(s.salt_id, s.strength) for s in ref_salts}
    salt_count = len(ref_set)

    # 3. Find candidate medicines that share ALL the same (salt_id, strength)
    #    pairs — and have exactly the same number of salts (no extras).
    #    Use OR-based conditions (SQLite-compatible, no tuple IN).
    from sqlalchemy import and_, or_
    salt_conditions = or_(
        *[
            and_(
                MedicineSalt.salt_id == sid,
                MedicineSalt.strength == sstr,
            )
            for sid, sstr in ref_set
        ]
    )
    candidates = (
        db.query(MedicineSalt.medicine_id)
        .filter(
            MedicineSalt.medicine_id != medicine_id,
            salt_conditions,
        )
        .group_by(MedicineSalt.medicine_id)
        .having(func.count(MedicineSalt.id) == salt_count)
        .limit(10)
        .all()
    )
    candidate_ids = [c[0] for c in candidates]
    if not candidate_ids:
        return []

    # Filter out candidates that have extra salts beyond the reference set
    final_ids = []
    for cid in candidate_ids:
        c_salts = (
            db.query(MedicineSalt.salt_id, MedicineSalt.strength)
            .filter(MedicineSalt.medicine_id == cid)
            .all()
        )
        if {(s.salt_id, s.strength) for s in c_salts} == ref_set:
            final_ids.append(cid)

    if not final_ids:
        return []

    # 4. Fetch substitute medicine records
    substitutes = (
        db.query(Medicine)
        .filter(Medicine.id.in_(final_ids))
        .order_by(Medicine.name)
        .all()
    )

    # 5. Get reference price (latest MRP)
    ref_price = _get_latest_mrp(db, medicine_id)

    # 6. Build response with price comparison
    results = []
    for med in substitutes:
        med_price = _get_latest_mrp(db, med.id)

        price_diff_pct = None
        price_label = "price unavailable"

        if med_price is not None and ref_price is not None and ref_price > 0:
            pct = ((med_price - ref_price) / ref_price) * 100
            price_diff_pct = round(pct)
            if abs(pct) < 1:
                price_label = "same price"
            elif pct < 0:
                price_label = f"{abs(round(pct))}% cheaper"
            else:
                price_label = f"{round(pct)}% expensive"
        elif med_price is not None and ref_price is None:
            price_label = "price unavailable"

        results.append({
            "id": med.id,
            "name": med.name,
            "brand_name": med.brand_name,
            "strength": med.strength,
            "price": med_price,
            "price_difference_percent": price_diff_pct,
            "price_label": price_label,
        })

    return results


# ── Unified details ──────────────────────────────────────────────────────

def get_medicine_details(db: Session, medicine_id: int):
    """Return full medicine details: info + composition + substitutes + price.

    Reuses existing service functions — no duplicated queries.
    """
    from services.salt_service import get_medicine_composition

    # 1. Medicine info (raises 404 if missing)
    medicine = get_medicine(db, medicine_id)

    # 2. Composition
    raw_composition = get_medicine_composition(db, medicine_id)
    composition = [
        {"salt": c["salt_name"], "strength": c["strength"]}
        for c in raw_composition
    ]

    # 3. Selling price — reuse the same _get_latest_mrp helper
    price = _get_latest_mrp(db, medicine_id)

    # 4. Substitutes — reuse existing function (already handles all edge cases)
    substitutes = get_substitutes_with_price(db, medicine_id)

    return {
        "id": medicine.id,
        "name": medicine.name,
        "brand_name": medicine.brand_name,
        "strength": medicine.strength,
        "price": price,
        "composition": composition,
        "substitutes": substitutes,
    }
