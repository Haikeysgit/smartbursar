from typing import Optional
from decimal import Decimal
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, ForeignKey, Numeric
from models.base import Base

class FeeStructure(Base):
    """
    Defines default school fees for a specific class level in a school.
    Allows auto-filling of fee amounts when adding/importing students.
    """
    __tablename__ = 'fee_structures'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey("schools.id"), nullable=False, index=True)
    
    class_level: Mapped[str] = mapped_column(String(50), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    term: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, comment="e.g. First Term")
    
    # Relationships
    school = relationship("School", back_populates="fee_structures")

    def __repr__(self):
        return f"<FeeStructure(class='{self.class_level}', amount={self.amount})>"
