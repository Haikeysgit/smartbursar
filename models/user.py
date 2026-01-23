"""
=============================================================================
PROJECT ATLAS - User Model (Authentication)
=============================================================================
Users who can log into the dashboard.

Two types:
    1. SUPER_ADMIN: Can see all schools (God Mode)
    2. SCHOOL_ADMIN: Can only see their school's data

SECURITY:
    - school_id is None for SUPER_ADMIN (they're not tied to one school)
    - SCHOOL_ADMIN must have a valid school_id
    - Passwords are hashed with bcrypt
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional

import bcrypt
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.school import School


class User(Base, TimestampMixin):
    """
    A user who can log into the dashboard.
    """
    __tablename__ = "users"
    
    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # -------------------------------------------------------------------------
    # School Link (CRITICAL FOR SECURITY)
    # -------------------------------------------------------------------------
    school_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("schools.id", ondelete="CASCADE"),
        nullable=True,  # NULL for SUPER_ADMIN
        comment="NULL for super admin, otherwise links to school"
    )
    
    # -------------------------------------------------------------------------
    # Auth Credentials
    # -------------------------------------------------------------------------
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    
    # -------------------------------------------------------------------------
    # Role & Status
    # -------------------------------------------------------------------------
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="SCHOOL_ADMIN",
        comment="SUPER_ADMIN or SCHOOL_ADMIN"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    
    # -------------------------------------------------------------------------
    # Session Tracking
    # -------------------------------------------------------------------------
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    # -------------------------------------------------------------------------
    # Relationships
    # -------------------------------------------------------------------------
    school: Mapped[Optional["School"]] = relationship(
        "School",
        back_populates="users",
    )
    
    # -------------------------------------------------------------------------
    # Methods
    # -------------------------------------------------------------------------
    def set_password(self, password: str) -> None:
        """
        Hash and store a password.
        
        Uses bcrypt with automatic salt generation.
        This is the ONLY way to set a password!
        """
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')
    
    def check_password(self, password: str) -> bool:
        """
        Verify a password against the stored hash.
        
        Returns True if password matches, False otherwise.
        """
        password_bytes = password.encode('utf-8')
        hash_bytes = self.password_hash.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hash_bytes)
    
    @property
    def is_super_admin(self) -> bool:
        """True if user is a super admin."""
        return self.role == "SUPER_ADMIN"
    
    @property
    def is_school_admin(self) -> bool:
        """True if user is a school admin."""
        return self.role == "SCHOOL_ADMIN"


# =============================================================================
# Helper Functions
# =============================================================================

def create_user(
    email: str,
    password: str,
    role: str = "SCHOOL_ADMIN",
    school_id: Optional[int] = None,
) -> User:
    """
    Create a new user with hashed password.
    
    Args:
        email: User's email (must be unique)
        password: Plain text password (will be hashed)
        role: "SUPER_ADMIN" or "SCHOOL_ADMIN"
        school_id: Required for SCHOOL_ADMIN, None for SUPER_ADMIN
    
    Returns:
        User instance (not yet committed to database)
    
    Raises:
        ValueError: If SCHOOL_ADMIN without school_id
    """
    if role == "SCHOOL_ADMIN" and school_id is None:
        raise ValueError("SCHOOL_ADMIN must have a school_id")
    
    if role == "SUPER_ADMIN" and school_id is not None:
        raise ValueError("SUPER_ADMIN should not have a school_id")
    
    user = User(
        email=email.lower().strip(),
        role=role,
        school_id=school_id,
    )
    user.set_password(password)
    
    return user
