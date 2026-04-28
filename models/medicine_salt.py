from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from database.base import Base


class MedicineSalt(Base):
    __tablename__ = "medicine_salts"

    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    salt_id = Column(Integer, ForeignKey("salts.id"), nullable=False)
    strength = Column(String, nullable=True)

    # Relationships
    medicine = relationship("Medicine")
    salt = relationship("Salt", back_populates="medicine_salts")
