from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # ── Payment ─────────────────────────────────────────
    payment_method = Column(String, default="cash")  # "cash" | "upi"

    # ── Totals ──────────────────────────────────────────
    subtotal = Column(Float, default=0.0)             # sum of item MRP totals
    discount_percent = Column(Float, default=0.0)     # admin-configured %
    discount_amount = Column(Float, default=0.0)      # ₹ discount applied

    loyalty_points_redeemed = Column(Integer, default=0)
    loyalty_discount = Column(Float, default=0.0)     # ₹ value of redeemed points

    net_amount = Column(Float, default=0.0)           # final payable
    total_amount = Column(Float, default=0.0)         # = net_amount (backward compat)

    loyalty_points_earned = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())

    store = relationship("Store", back_populates="orders")
    customer = relationship("Customer", back_populates="orders")
    # One order → many order items
    items = relationship("OrderItem", back_populates="order")
