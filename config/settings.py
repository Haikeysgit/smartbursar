"""
=============================================================================
PROJECT ATLAS - Application Settings
=============================================================================
Centralized configuration loaded from environment variables.
All settings are validated on startup - if something is wrong, we fail fast.

Usage:
    from config.settings import settings
    print(settings.DATABASE_URL)
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Pydantic will:
    1. Load from .env file if present
    2. Override with actual environment variables
    3. Validate types and required fields
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Ignore unknown env vars
    )
    
    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    DATABASE_URL: str = "sqlite:///./atlas.db"
    
    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_EXPIRE_HOURS: int = 24
    JWT_ALGORITHM: str = "HS256"
    
    # -------------------------------------------------------------------------
    # Super Admin (created on first run)
    # -------------------------------------------------------------------------
    SUPER_ADMIN_EMAIL: str = "admin@atlas.com"
    SUPER_ADMIN_PASSWORD: str = ""  # REQUIRED: Set via environment variable
    
    # -------------------------------------------------------------------------
    # App Settings
    # -------------------------------------------------------------------------
    DEFAULT_COUNTRY_CODE: str = "NG"  # ISO 3166-1 alpha-2
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    MOCK_MODE: bool = True  # Phase 1: Print instead of send
    WHATSAPP_MODE: bool = False  # Phase 2: Use WhatsApp Web (pywhatkit)
    
    # -------------------------------------------------------------------------
    # Timezone (Nigeria = West Africa Time, UTC+1)
    # -------------------------------------------------------------------------
    TIMEZONE: str = "Africa/Lagos"
    
    # -------------------------------------------------------------------------
    # Cost Control
    # -------------------------------------------------------------------------
    MAX_MESSAGES_PER_DAY_PER_SCHOOL: int = 100
    MAX_MONTHLY_SPEND_PER_SCHOOL: int = 20000  # Naira
    
    # -------------------------------------------------------------------------
    # Pricing Model (₦150,000/term for 150 debtors, ₦500 per overage)
    # -------------------------------------------------------------------------
    BASE_PRICE_PER_TERM: int = 150000  # ₦150,000
    BASE_DEBTOR_LIMIT: int = 150  # Included in base price
    OVERAGE_PER_DEBTOR: int = 500  # ₦500 per debtor above limit
    
    # -------------------------------------------------------------------------
    # Phase 2: Messaging APIs (empty for now)
    # -------------------------------------------------------------------------
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    TWILIO_SMS_NUMBER: str = ""
    
    # -------------------------------------------------------------------------
    # Phase 2: AI
    # -------------------------------------------------------------------------
    GEMINI_API_KEY: str = ""
    
    # -------------------------------------------------------------------------
    # Computed Properties
    # -------------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        """True if running in development mode."""
        return self.ENVIRONMENT == "development"
    
    @property
    def is_production(self) -> bool:
        """True if running in production mode."""
        return self.ENVIRONMENT == "production"
    
    @property
    def is_sqlite(self) -> bool:
        """True if using SQLite (development)."""
        return self.DATABASE_URL.startswith("sqlite")
    
    @property
    def project_root(self) -> Path:
        """Returns the project root directory."""
        return Path(__file__).parent.parent


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Using lru_cache means settings are only loaded once from env.
    """
    return Settings()


# Convenience alias
settings = get_settings()


# =============================================================================
# Receipt Number Format
# =============================================================================
# Format: {school_code}-{year}-{student_id:05d}-{payment_seq:02d}
# Example: ABC-2026-00247-01
#
# - school_code: 3-letter code (from School.school_code)
# - year: 4-digit year
# - student_id: 5-digit zero-padded student ID
# - payment_seq: 2-digit payment sequence (01, 02, 03...)

def generate_receipt_number(
    school_code: str,
    year: int,
    student_id: int,
    payment_sequence: int
) -> str:
    """
    Generate a receipt number in the standard format.
    
    Args:
        school_code: 3-letter school identifier (e.g., "ABC")
        year: Year of payment (e.g., 2026)
        student_id: Student's database ID
        payment_sequence: Which payment this is (1, 2, 3...)
    
    Returns:
        Formatted receipt number like "ABC-2026-00247-01"
    
    Why this format?
        - Human readable (can spot school, year at a glance)
        - Computer sortable (lexicographic sorting works)
        - Traceable (student_id links to all payments)
        - Unique (sequence prevents duplicates)
    """
    return f"{school_code.upper()}-{year}-{student_id:05d}-{payment_sequence:02d}"


# =============================================================================
# Pricing Calculation
# =============================================================================

def calculate_school_fee(debtor_count: int) -> dict:
    """
    Calculate the fee for a school based on debtor count.
    
    Pricing Model:
        - Base: ₦150,000/term for up to 150 debtors
        - Overage: ₦500 per debtor above 150
    
    Args:
        debtor_count: Number of students with outstanding balance
    
    Returns:
        dict with base_fee, overage_fee, total_fee, and breakdown
    """
    base_fee = settings.BASE_PRICE_PER_TERM
    base_limit = settings.BASE_DEBTOR_LIMIT
    overage_rate = settings.OVERAGE_PER_DEBTOR
    
    if debtor_count <= base_limit:
        overage_count = 0
        overage_fee = 0
    else:
        overage_count = debtor_count - base_limit
        overage_fee = overage_count * overage_rate
    
    total_fee = base_fee + overage_fee
    
    return {
        "base_fee": base_fee,
        "base_limit": base_limit,
        "debtor_count": debtor_count,
        "overage_count": overage_count,
        "overage_rate": overage_rate,
        "overage_fee": overage_fee,
        "total_fee": total_fee,
    }
