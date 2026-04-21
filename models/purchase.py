"""
Purchase models — invoice header and line items.

A Purchase represents a stock procurement from a supplier.
Each PurchaseItem links to a medicine and (after stock is added)
to the resulting Inventory row.
"""

from sqlalchemy import Column, Integer, Float, String, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class Purchase(Base):
    """Purchase invoice header."""
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    supplier_name = Column(String, nullable=False, index=True)
    invoice_number = Column(String, nullable=False, index=True)
    invoice_date = Column(Date, nullable=True)

    total_items = Column(Integer, default=0)
    total_quantity = Column(Integer, default=0)     # total units purchased
    total_amount = Column(Float, default=0.0)       # sum of line_totals

    created_at = Column(DateTime, server_default=func.now())

    # Prevent duplicate invoice from same supplier
    __table_args__ = (
        UniqueConstraint("supplier_name", "invoice_number", name="uq_supplier_invoice"),
    )

    store = relationship("Store")
    items = relationship("PurchaseItem", back_populates="purchase", lazy="joined")


class PurchaseItem(Base):
    """Line item on a purchase invoice."""
    __tablename__ = "purchase_items"

    id = Column(Integer, primary_key=True, index=True)
    purchase_id = Column(Integer, ForeignKey("purchases.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)

    # The inventory row that was created/updated for this line
    inventory_id = Column(Integer, ForeignKey("inventory.id"), nullable=True)

    batch_no = Column(String, nullable=False)
    expiry_date = Column(Date, nullable=False)
    quantity = Column(Integer, nullable=False)           # strips purchased
    units_per_strip = Column(Integer, nullable=False)    # from Medicine model
    quantity_units = Column(Integer, nullable=False)      # total units (quantity × ups)
    purchase_price = Column(Float, nullable=False)        # per-unit cost
    mrp = Column(Float, nullable=False)                   # per-unit selling price
    line_total = Column(Float, nullable=False)            # purchase_price × quantity_units

    purchase = relationship("Purchase", back_populates="items")
    medicine = relationship("Medicine")
    inventory = relationship("Inventory")
