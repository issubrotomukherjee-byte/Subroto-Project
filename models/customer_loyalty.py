from sqlalchemy import Column, Integer, String, Date, ForeignKey
from sqlalchemy.orm import relationship
from database.base import Base


class CustomerLoyalty(Base):
    __tablename__ = "customer_loyalty"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True)
    points = Column(Integer, default=0)
    membership_type = Column(String, default="Bronze")  # Bronze / Silver / Gold
    expiry = Column(Date, nullable=True)

    customer = relationship("Customer", back_populates="loyalty")
    transactions = relationship("LoyaltyTransaction", back_populates="loyalty")
