"""
=============================================================================
PROJECT ATLAS - Database Configuration
=============================================================================
SQLAlchemy setup that prioritizes production PostgreSQL connection.
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings

logger = logging.getLogger(__name__)

# =============================================================================
# Engine Creation
# =============================================================================

def get_connection_string():
    """
    Determine the database connection string.
    
    Priority:
    1. OS Environment Variable 'DATABASE_URL' (Production/Railway)
    2. settings.DATABASE_URL (Fallback/Dev)
    3. Local SQLite default
    """
    # 1. Check OS Environment (Strict Priority for Railway)
    db_url = os.getenv("DATABASE_URL")
    
    if db_url:
        # Fix SQLAlchemy compatibility (Heroku/Railway may use 'postgres://')
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url

    # 2. Settings Fallback
    if hasattr(settings, "DATABASE_URL") and settings.DATABASE_URL:
        return settings.DATABASE_URL

    # 3. Local Default (BUT CRASH IF PRODUCTION)
    environment = os.getenv("ENVIRONMENT", "development")
    if environment.lower() in ("production", "prod", "staging"):
         # WARN but do not crash yet - User is having trouble linking DB
         logger.warning("WARNING: Running in PRODUCTION but DATABASE_URL is not set!")
         logger.warning("Data will be lost on redeploy. Please link PostgreSQL soon.")
         # return "sqlite:///./atlas.db" # Fallback allowed for now

    return "sqlite:///./atlas.db"


def create_db_engine():
    """
    Create SQLAlchemy engine with strict connection logic.
    """
    db_url = get_connection_string()
    logger.info(f"Connecting to database: {db_url.split('@')[-1] if '@' in db_url else 'SQLite'}")

    if "sqlite" in db_url:
        # SQLite specific settings
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},  # Required for FastAPI
            echo=False,
        )
        
        # Enable foreign keys for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    else:
        # PostgreSQL settings
        engine = create_engine(
            db_url,
            pool_pre_ping=True,  # Verify connections before use
            pool_size=10,        # Increased for production
            max_overflow=20,
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
    """Dependency for FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context() -> Generator[Session, None, None]:
    """Context manager for scripts."""
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
    Create all database tables if they don't exist.
    """
    try:
        from models.base import Base
        # Import all models so they register with Base
        from models import school, user, student, transaction, message_log
        
        inspector = inspect(engine)
        
        # Check if critical tables exist
        if not inspector.has_table("students"):
            logger.info("Tables missing. Creating all tables...")
            Base.metadata.create_all(bind=engine)
            logger.info("Tables created successfully.")
        else:
            logger.info("Tables already exist. Skipping creation.")
            
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Re-raise to stop startup if DB is down
        raise


def drop_all_tables():
    """DROP ALL TABLES. Use only for testing!"""
    db_url = get_connection_string()
    if "postgres" in db_url and "localhost" not in db_url and "127.0.0.1" not in db_url:
         # Safety check against dropping production DB
         logger.critical("ATTEMPTED TO DROP PRODUCTION TABLES. OPERATION BLOCKED.")
         raise RuntimeError("Cannot drop tables in production environment!")

    from models.base import Base
    Base.metadata.drop_all(bind=engine)
