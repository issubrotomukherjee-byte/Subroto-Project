from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database.base import Base


class Store(Base):
    __tablename__ = "stores"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    location = Column(String, nullable=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)

    # One store → many inventory entries
    inventory = relationship("Inventory", back_populates="store")
    # One store → many orders
    orders = relationship("Order", back_populates="store")
