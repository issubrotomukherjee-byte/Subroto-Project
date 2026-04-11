from sqlalchemy import Column, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
from database.base import Base


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    # ── Pricing snapshot from inventory batch at time of sale ──
    mrp = Column(Float, nullable=False)
    purchase_price = Column(Float, nullable=False)
    discount_applied = Column(Float, default=0.0)
    final_price = Column(Float, nullable=False)
    profit = Column(Float, nullable=False)

    order = relationship("Order", back_populates="items")
    medicine = relationship("Medicine", back_populates="order_items")
    batches = relationship("OrderItemBatch", back_populates="order_item")
