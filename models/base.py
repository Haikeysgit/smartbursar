"""
=============================================================================
PROJECT ATLAS - SQLAlchemy Base Model
=============================================================================
All models inherit from this Base class.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """
    Base class for all database models.
    
    Provides:
    - Automatic table name generation (lowercase class name + 's')
    - Common timestamp columns (created_at, updated_at)
    - Nice __repr__ for debugging
    """
    
    # Automatically generate table names from class name
    # e.g., Student -> students, MessageLog -> message_logs
    @classmethod
    def __tablename__(cls) -> str:
        # Convert CamelCase to snake_case and pluralize
        import re
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
        return name + 's'
    
    def __repr__(self) -> str:
        """Nice representation for debugging."""
        class_name = self.__class__.__name__
        attrs = []
        for col in self.__table__.columns:
            if col.name in ('id', 'name', 'email', 'school_id', 'student_id'):
                value = getattr(self, col.name, None)
                attrs.append(f"{col.name}={value!r}")
        return f"<{class_name}({', '.join(attrs)})>"


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamps.
    
    Usage: 
        class MyModel(Base, TimestampMixin):
            ...
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
