from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from database.base import Base


class Salt(Base):
    __tablename__ = "salts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)

    # One salt → many medicine-salt links
    medicine_salts = relationship("MedicineSalt", back_populates="salt")
