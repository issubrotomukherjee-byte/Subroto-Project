from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    total_amount = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=func.now())

    store = relationship("Store", back_populates="orders")
    customer = relationship("Customer", back_populates="orders")
    # One order → many order items
    items = relationship("OrderItem", back_populates="order")
