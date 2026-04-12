from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from database.base import Base


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, unique=True)
    salt = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    units_per_strip = Column(Integer, default=10, nullable=False)

    # One medicine → many inventory entries (one per store)
    inventory = relationship("Inventory", back_populates="medicine")
    # One medicine → many order items
    order_items = relationship("OrderItem", back_populates="medicine")
