"""
Billing-settings service — singleton config with full audit trail.

The settings table always has exactly ONE row.  On first access it is
auto-seeded with safe defaults so no manual migration is needed.
"""

from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.billing_settings import BillingSettings, BillingSettingsAudit
from schemas.billing_settings_schema import BillingSettingsUpdate


# ── Defaults (used only for initial seed) ────────────────

_DEFAULTS = {
    "default_medicine_discount_percent": 10.0,
    "loyalty_credit_percent": 1.0,
    "max_loyalty_redemption_percent": 20.0,
}


# ── Internal helpers ─────────────────────────────────────

def _get_or_seed(db: Session) -> BillingSettings:
    """Return the singleton settings row, creating it on first access."""
    settings = db.query(BillingSettings).first()
    if settings is None:
        settings = BillingSettings(**_DEFAULTS, updated_by_admin="system")
        db.add(settings)
        db.flush()

        # Audit the seed
        db.add(BillingSettingsAudit(
            **_DEFAULTS,
            changed_by="system",
            action="seed",
        ))
        db.commit()
        db.refresh(settings)
    return settings


# ── Public API ───────────────────────────────────────────

def get_settings(db: Session) -> BillingSettings:
    """Return current billing settings (read-only, any role)."""
    return _get_or_seed(db)


def update_settings(db: Session, data: BillingSettingsUpdate, admin_name: str) -> BillingSettings:
    """Partial-update billing settings.  Admin-only.  Audited."""
    settings = _get_or_seed(db)

    changed = False
    if data.default_medicine_discount_percent is not None:
        settings.default_medicine_discount_percent = data.default_medicine_discount_percent
        changed = True
    if data.loyalty_credit_percent is not None:
        settings.loyalty_credit_percent = data.loyalty_credit_percent
        changed = True
    if data.max_loyalty_redemption_percent is not None:
        settings.max_loyalty_redemption_percent = data.max_loyalty_redemption_percent
        changed = True

    if not changed:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    settings.updated_by_admin = admin_name

    # Audit snapshot (AFTER values)
    db.add(BillingSettingsAudit(
        default_medicine_discount_percent=settings.default_medicine_discount_percent,
        loyalty_credit_percent=settings.loyalty_credit_percent,
        max_loyalty_redemption_percent=settings.max_loyalty_redemption_percent,
        changed_by=admin_name,
        action="update",
    ))

    db.commit()
    db.refresh(settings)
    return settings


def get_audit_log(db: Session) -> list:
    """Return full audit history, newest first."""
    return (
        db.query(BillingSettingsAudit)
        .order_by(BillingSettingsAudit.changed_at.desc())
        .all()
    )
