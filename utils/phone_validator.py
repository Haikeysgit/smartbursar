"""
=============================================================================
PROJECT ATLAS - Phone Number Validation
=============================================================================
Validates and formats phone numbers to E.164 international format.
Uses Google's libphonenumber library for accurate validation.

RULE: All phone numbers in the database MUST be in E.164 format.
      Example: +2348012345678 (not 08012345678)

Why E.164?
    - WhatsApp API requires it
    - SMS APIs require it
    - International compatibility (Ghana, Kenya, etc.)
    - No ambiguity
"""

from typing import Optional, Tuple

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberType
from phonenumbers import format_number, is_possible_number, is_valid_number
from phonenumbers import number_type as get_number_type
from phonenumbers import PhoneNumberFormat


# =============================================================================
# Supported Countries
# =============================================================================
# ISO 3166-1 alpha-2 codes

SUPPORTED_COUNTRIES = {
    # Phase 1 (Launch)
    "NG": "Nigeria",
    "GH": "Ghana",
    "KE": "Kenya",
    
    # Phase 2 (Expansion)
    "ZA": "South Africa",
    "UG": "Uganda",
    "TZ": "Tanzania",
    "RW": "Rwanda",
    
    # Future (Diaspora)
    "GB": "United Kingdom",
    "US": "United States",
}


# =============================================================================
# Main Validation Function
# =============================================================================

def validate_and_format_phone(
    phone_input: str,
    default_country: str = "NG"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Takes messy phone input and returns clean E.164 format.
    
    Args:
        phone_input: User's input (e.g., "0801234567", "080 123 4567")
        default_country: ISO country code (NG=Nigeria, GH=Ghana, etc.)
    
    Returns:
        Tuple of (formatted_phone, error_message)
        - Success: ("+2348012345678", None)
        - Failure: (None, "Error description")
    
    Examples:
        >>> validate_and_format_phone("08012345678", "NG")
        ('+2348012345678', None)
        
        >>> validate_and_format_phone("0801 234 5678", "NG")
        ('+2348012345678', None)
        
        >>> validate_and_format_phone("+234 801 234 5678", "NG")
        ('+2348012345678', None)
        
        >>> validate_and_format_phone("0244123456", "GH")
        ('+233244123456', None)
        
        >>> validate_and_format_phone("080123", "NG")
        (None, 'Invalid phone number length')
    """
    
    # Clean the input
    phone_input = phone_input.strip()
    
    if not phone_input:
        return None, "Phone number is required"
    
    try:
        # Parse the number
        parsed = phonenumbers.parse(phone_input, default_country)
        
        # Validate it's a possible number (correct length)
        if not is_possible_number(parsed):
            return None, "Invalid phone number length"
        
        # Validate it's a valid number for that region
        if not is_valid_number(parsed):
            return None, "Invalid phone number for this country"
        
        # Check if it's a mobile number (we need mobile for WhatsApp)
        num_type = get_number_type(parsed)
        mobile_types = [
            PhoneNumberType.MOBILE,
            PhoneNumberType.FIXED_LINE_OR_MOBILE,
        ]
        
        if num_type not in mobile_types:
            return None, "Must be a mobile number (for WhatsApp)"
        
        # Format as E.164
        formatted = format_number(parsed, PhoneNumberFormat.E164)
        
        return formatted, None
        
    except NumberParseException as e:
        # User-friendly error messages
        error_map = {
            NumberParseException.INVALID_COUNTRY_CODE: "Invalid country code",
            NumberParseException.NOT_A_NUMBER: "This doesn't look like a phone number",
            NumberParseException.TOO_SHORT_AFTER_IDD: "Phone number is too short",
            NumberParseException.TOO_SHORT_NSN: "Phone number is too short",
            NumberParseException.TOO_LONG: "Phone number is too long",
        }
        error_msg = error_map.get(e.error_type, f"Invalid phone number: {str(e)}")
        return None, error_msg


# =============================================================================
# Bulk Validation (for CSV imports)
# =============================================================================

def validate_phone_list(
    phones: list[str],
    default_country: str = "NG"
) -> Tuple[list[str], list[Tuple[int, str, str]]]:
    """
    Validate a list of phone numbers.
    
    Args:
        phones: List of phone number strings
        default_country: ISO country code
    
    Returns:
        Tuple of (valid_phones, errors)
        - valid_phones: List of formatted E.164 numbers
        - errors: List of (index, original_phone, error_message)
    """
    valid_phones = []
    errors = []
    
    for i, phone in enumerate(phones):
        formatted, error = validate_and_format_phone(phone, default_country)
        
        if formatted:
            valid_phones.append(formatted)
        else:
            errors.append((i, phone, error))
    
    return valid_phones, errors


# =============================================================================
# Display Formatting (for UI)
# =============================================================================

def format_phone_for_display(
    e164_phone: str,
    style: str = "national"
) -> str:
    """
    Format an E.164 phone number for human display.
    
    Args:
        e164_phone: Phone in E.164 format (+2348012345678)
        style: "national" (0801 234 5678) or "international" (+234 801 234 5678)
    
    Returns:
        Formatted phone number for display
    """
    if not e164_phone:
        return ""
    
    try:
        parsed = phonenumbers.parse(e164_phone.strip())
        
        if style == "national":
            return format_number(parsed, PhoneNumberFormat.NATIONAL)
        else:
            return format_number(parsed, PhoneNumberFormat.INTERNATIONAL)
            
    except NumberParseException:
        # Return as-is if parsing fails
        return e164_phone


def get_country_from_phone(e164_phone: str) -> Optional[str]:
    """
    Extract country code from an E.164 phone number.
    
    Args:
        e164_phone: Phone in E.164 format (+2348012345678)
    
    Returns:
        ISO country code (e.g., "NG") or None if unable to determine
    """
    if not e164_phone:
        return None
    
    try:
        parsed = phonenumbers.parse(e164_phone.strip())
        return phonenumbers.region_code_for_number(parsed)
    except NumberParseException:
        return None


# =============================================================================
# Phone Normalization for DB Lookup
# =============================================================================

def normalize_phone_for_lookup(phone: str) -> Tuple[str, str]:
    """
    Normalize incoming phone number for database lookup.
    
    Handles the mismatch between WhatsApp format (2347040344475) 
    and local DB format (07040344475).
    
    Args:
        phone: Incoming phone number (any format)
    
    Returns:
        Tuple of (local_format, international_format) for flexible matching
        
    Examples:
        >>> normalize_phone_for_lookup("2347040344475")
        ('07040344475', '+2347040344475')
        
        >>> normalize_phone_for_lookup("+2348012345678")
        ('08012345678', '+2348012345678')
        
        >>> normalize_phone_for_lookup("08012345678")
        ('08012345678', '+2348012345678')
    """
    if not phone:
        return "", ""
    
    # Clean: strip whitespace, remove + and spaces
    cleaned = phone.strip().replace("+", "").replace(" ", "").replace("-", "")
    
    # Convert to local format (0...)
    if cleaned.startswith("234") and len(cleaned) > 10:
        local_format = "0" + cleaned[3:]
    elif cleaned.startswith("0"):
        local_format = cleaned
    else:
        local_format = cleaned
    
    # Convert to international format (+234...)
    if cleaned.startswith("234"):
        international_format = "+" + cleaned
    elif cleaned.startswith("0") and len(cleaned) >= 10:
        international_format = "+234" + cleaned[1:]
    else:
        international_format = "+" + cleaned
    
    return local_format, international_format

