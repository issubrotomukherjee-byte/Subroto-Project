from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=True, unique=True)
    email = Column(String, nullable=True, unique=True)

    # One customer → many orders
    orders = relationship("Order", back_populates="customer")

    # One customer → one loyalty record
    loyalty = relationship("CustomerLoyalty", back_populates="customer", uselist=False)
