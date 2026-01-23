"""
=============================================================================
PROJECT ATLAS - Database Configuration
=============================================================================
SQLAlchemy setup that works with both SQLite (dev) and PostgreSQL (prod).

CRITICAL for Multi-Tenant Security:
    All queries MUST include school_id filter. This is enforced at the
    service layer, not here - but the models are designed to make this
    easy and obvious.

Usage:
    from config.database import get_db, engine
    
    # In FastAPI
    @app.get("/students")
    def get_students(db: Session = Depends(get_db)):
        ...
    
    # In scripts
    with get_db_context() as db:
        ...
"""

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings


# =============================================================================
# Engine Creation
# =============================================================================

def create_db_engine():
    """
    Create SQLAlchemy engine based on DATABASE_URL.
    
    Handles differences between SQLite and PostgreSQL:
    - SQLite: Needs check_same_thread=False for FastAPI
    - PostgreSQL: Uses connection pooling
    """
    if settings.is_sqlite:
        # SQLite specific settings
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"check_same_thread": False},  # Required for FastAPI
            echo=settings.is_development,  # Log SQL in dev mode
        )
        
        # Enable foreign keys for SQLite (off by default!)
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        # PostgreSQL settings
        engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,  # Verify connections before use
            pool_size=5,
            max_overflow=10,
            echo=settings.is_development,
        )
    
    return engine


# Create the engine
engine = create_db_engine()

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


# =============================================================================
# Session Management
# =============================================================================

def get_db() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI routes.
    
    Usage:
        @app.get("/students")
        def get_students(db: Session = Depends(get_db)):
            return db.query(Student).all()
    
    The session is automatically closed after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """
    Context manager for scripts and non-FastAPI code.
    
    Usage:
        with get_db_context() as db:
            students = db.query(Student).all()
    
    Automatically handles commit on success, rollback on error.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =============================================================================
# Database Initialization
# =============================================================================

def init_db():
    """
    Create all database tables.
    
    Call this on application startup. Safe to call multiple times -
    SQLAlchemy only creates tables that don't exist.
    
    IMPORTANT: Import all models before calling this!
    """
    from models.base import Base
    
    # Import all models so they register with Base
    from models import school, user, student, transaction, message_log
    
    Base.metadata.create_all(bind=engine)


def drop_all_tables():
    """
    DROP ALL TABLES. Use only for testing!
    
    ⚠️ WARNING: This deletes ALL data. Never call in production.
    """
    if settings.is_production:
        raise RuntimeError("Cannot drop tables in production!")
    
    from models.base import Base
    Base.metadata.drop_all(bind=engine)
