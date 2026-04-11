from sqlalchemy import Column, Integer, Float, String, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database.base import Base


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)
    store_id = Column(Integer, ForeignKey("stores.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Integer, default=0)
    batch_no = Column(String, nullable=False)
    expiry_date = Column(Date, nullable=False)
    mrp = Column(Float, nullable=False)
    purchase_price = Column(Float, nullable=False)

    # Each (store, medicine, batch) combo must be unique
    __table_args__ = (
        UniqueConstraint("store_id", "medicine_id", "batch_no", name="uq_store_medicine_batch"),
    )

    store = relationship("Store", back_populates="inventory")
    medicine = relationship("Medicine", back_populates="inventory")
