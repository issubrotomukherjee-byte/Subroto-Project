"""
Centralised billing settings — single-row config table.

Only admins may update.  Every change is recorded in the audit table.
"""

from sqlalchemy import Column, Integer, Float, String, DateTime
from sqlalchemy.sql import func
from database.base import Base


class BillingSettings(Base):
    """Single-row table holding global billing configuration.

    Seeded on first access with safe defaults.
    """
    __tablename__ = "billing_settings"

    id = Column(Integer, primary_key=True, index=True)
    default_medicine_discount_percent = Column(Float, nullable=False, default=10.0)
    loyalty_credit_percent = Column(Float, nullable=False, default=1.0)
    max_loyalty_redemption_percent = Column(Float, nullable=False, default=20.0)
    updated_by_admin = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class BillingSettingsAudit(Base):
    """Immutable audit log for every billing-settings change."""
    __tablename__ = "billing_settings_audit"

    id = Column(Integer, primary_key=True, index=True)
    # Snapshot of values AFTER the change
    default_medicine_discount_percent = Column(Float, nullable=False)
    loyalty_credit_percent = Column(Float, nullable=False)
    max_loyalty_redemption_percent = Column(Float, nullable=False)
    changed_by = Column(String, nullable=False)
    changed_at = Column(DateTime, server_default=func.now())
    action = Column(String, nullable=False)  # "seed" | "update"
