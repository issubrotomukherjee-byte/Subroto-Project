from sqlalchemy import Column, Integer, String, Float, Boolean
from sqlalchemy.orm import relationship
from database.base import Base


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True, unique=True)
    salt = Column(String, nullable=True)
    price = Column(Float, nullable=False)
    units_per_strip = Column(Integer, default=10, nullable=False)

    # New fields
    brand_name = Column(String, nullable=True)
    manufacturer = Column(String, nullable=True)
    dosage_form = Column(String, nullable=True)
    strength = Column(String, nullable=True)
    hsn_code = Column(String, nullable=True)
    schedule_type = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=True)

    # One medicine → many inventory entries (one per store)
    inventory = relationship("Inventory", back_populates="medicine")
    # One medicine → many order items
    order_items = relationship("OrderItem", back_populates="medicine")

