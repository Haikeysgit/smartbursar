"""
=============================================================================
PROJECT ATLAS - Currency Formatting
=============================================================================
Handles Nigerian Naira (₦) formatting and parsing.

Always display amounts with:
    - Naira symbol (₦)
    - Thousands separator (,)
    - Two decimal places for receipts
    - No decimals for display if round number
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Union


# =============================================================================
# Constants
# =============================================================================

NAIRA_SYMBOL = "N"  # Using 'N' for Windows console compatibility (₦ causes encoding issues)
KOBO_IN_NAIRA = 100


# =============================================================================
# Formatting Functions
# =============================================================================

def format_naira(
    amount: Union[Decimal, float, int],
    include_symbol: bool = True,
    include_decimals: bool = True,
    hide_kobo_if_zero: bool = True
) -> str:
    """
    Format an amount as Nigerian Naira.
    
    Args:
        amount: The amount to format
        include_symbol: Whether to include ₦ symbol
        include_decimals: Whether to show decimal places
        hide_kobo_if_zero: If True and kobo is 0, show "₦60,000" not "₦60,000.00"
    
    Returns:
        Formatted string like "₦60,000.00" or "₦60,000"
    
    Examples:
        >>> format_naira(60000)
        '₦60,000'
        
        >>> format_naira(60000.50)
        '₦60,000.50'
        
        >>> format_naira(60000, include_symbol=False)
        '60,000'
        
        >>> format_naira(60000, hide_kobo_if_zero=False)
        '₦60,000.00'
    """
    # Convert to Decimal for precision
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    
    # Round to 2 decimal places
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    # Check if we should hide decimals
    has_kobo = amount % 1 != 0
    show_decimals = include_decimals and (has_kobo or not hide_kobo_if_zero)
    
    # Format with thousand separators
    if show_decimals:
        formatted = f"{amount:,.2f}"
    else:
        formatted = f"{int(amount):,}"
    
    # Add symbol
    if include_symbol:
        return f"{NAIRA_SYMBOL}{formatted}"
    
    return formatted


def format_naira_compact(amount: Union[Decimal, float, int]) -> str:
    """
    Format large amounts in compact form.
    
    Examples:
        >>> format_naira_compact(50000)
        '₦50k'
        
        >>> format_naira_compact(1500000)
        '₦1.5M'
        
        >>> format_naira_compact(500)
        '₦500'
    """
    # Convert to Decimal for precision
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    
    amount = abs(amount)  # Handle negative amounts
    
    if amount >= 1_000_000:
        value = amount / 1_000_000
        # Remove trailing zeros
        if value == int(value):
            return f"{NAIRA_SYMBOL}{int(value)}M"
        return f"{NAIRA_SYMBOL}{value:.1f}M".rstrip('0').rstrip('.')
    
    elif amount >= 1_000:
        value = amount / 1_000
        if value == int(value):
            return f"{NAIRA_SYMBOL}{int(value)}k"
        return f"{NAIRA_SYMBOL}{value:.1f}k".rstrip('0').rstrip('.')
    
    else:
        return format_naira(amount, hide_kobo_if_zero=True)


# =============================================================================
# Parsing Functions
# =============================================================================

def parse_naira(amount_str: str) -> Decimal:
    """
    Parse a Naira amount string to Decimal.
    
    Handles various input formats:
        - "60000"
        - "60,000"
        - "₦60,000"
        - "60k"
        - "60K"
        - "1.5M"
    
    Args:
        amount_str: The amount string to parse
    
    Returns:
        Decimal amount
    
    Raises:
        ValueError: If the string cannot be parsed
    
    Examples:
        >>> parse_naira("₦60,000")
        Decimal('60000')
        
        >>> parse_naira("60k")
        Decimal('60000')
        
        >>> parse_naira("1.5M")
        Decimal('1500000')
    """
    if not amount_str:
        raise ValueError("Amount cannot be empty")
    
    # Clean the string
    cleaned = amount_str.strip()
    
    # Remove currency symbol
    cleaned = cleaned.replace(NAIRA_SYMBOL, "")
    cleaned = cleaned.replace("NGN", "")
    cleaned = cleaned.replace("N", "")  # Common shorthand
    
    # Remove commas and spaces
    cleaned = cleaned.replace(",", "")
    cleaned = cleaned.replace(" ", "")
    
    # Handle compact notation (60k, 1.5M)
    multiplier = 1
    
    if cleaned.lower().endswith("k"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.lower().endswith("m"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    
    # Parse as Decimal
    try:
        value = Decimal(cleaned)
        return value * multiplier
    except Exception:
        raise ValueError(f"Cannot parse '{amount_str}' as a currency amount")


# =============================================================================
# Comparison Helpers
# =============================================================================

def is_significant_amount(amount: Union[Decimal, float, int], threshold: int = 10000) -> bool:
    """
    Check if an amount is significant (warrants extra attention).
    
    Used to prioritize high-value debts for manual intervention.
    
    Args:
        amount: The amount to check
        threshold: Amount in Naira (default ₦10,000)
    
    Returns:
        True if amount >= threshold
    """
    if isinstance(amount, (int, float)):
        amount = Decimal(str(amount))
    return abs(amount) >= threshold


def calculate_percentage(part: Decimal, total: Decimal) -> float:
    """
    Calculate percentage paid.
    
    Used for progress bars in dashboard.
    
    Args:
        part: Amount paid
        total: Total due
    
    Returns:
        Percentage as float (0.0 to 100.0+)
    """
    if total == 0:
        return 100.0 if part >= 0 else 0.0
    
    return float((part / total) * 100)
