from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class LoyaltyTransaction(Base):
    __tablename__ = "loyalty_transactions"

    id = Column(Integer, primary_key=True, index=True)
    loyalty_id = Column(Integer, ForeignKey("customer_loyalty.id"), nullable=False)
    points_added = Column(Integer, default=0)
    points_used = Column(Integer, default=0)
    reason = Column(String, nullable=False)  # e.g. "Order #5", "Redeemed"
    created_at = Column(DateTime, server_default=func.now())

    loyalty = relationship("CustomerLoyalty", back_populates="transactions")
