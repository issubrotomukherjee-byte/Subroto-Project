"""
Inventory Adjustment audit log model.

Every stock adjustment (manual increase/decrease) is recorded here
as an immutable audit trail.  One row per adjustment operation.
"""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class InventoryAdjustment(Base):
    """Immutable audit log for every manual stock adjustment."""
    __tablename__ = "inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=False)
    store_id = Column(Integer, nullable=False, index=True)
    medicine_id = Column(Integer, nullable=False, index=True)
    batch_no = Column(String, nullable=False)

    adjustment_type = Column(String, nullable=False)  # "increase" | "decrease"
    quantity = Column(Integer, nullable=False)         # always positive
    quantity_before = Column(Integer, nullable=False)  # snapshot before
    quantity_after = Column(Integer, nullable=False)   # snapshot after

    reason = Column(String, nullable=False)
    adjusted_by = Column(String, nullable=False)       # admin name/role
    created_at = Column(DateTime, server_default=func.now(), index=True)

    inventory = relationship("Inventory")
