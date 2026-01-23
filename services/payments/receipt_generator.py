"""
=============================================================================
PROJECT ATLAS - Receipt Generator
=============================================================================
Generates professional PDF receipts for payments.

Uses ReportLab to create receipts that include:
    - School logo (if available)
    - Receipt number
    - Student and payment details
    - Balance information
    - School contact info

The receipt format matches Nigerian business standards.
"""

import base64
import io
from datetime import datetime, date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

from utils.currency import format_naira
from utils.date_helpers import format_date_nigerian


# =============================================================================
# Receipt Data Structure
# =============================================================================

class ReceiptData:
    """Data needed to generate a receipt."""
    
    def __init__(
        self,
        # School info
        school_name: str,
        school_address: str,
        school_phone: str,
        school_logo_base64: Optional[str] = None,
        
        # Receipt info
        receipt_number: str = "",
        date: datetime = None,
        
        # Student info
        student_name: str = "",
        class_level: str = "",
        parent_name: str = "",
        
        # Payment info
        fees_total: Decimal = Decimal("0"),
        previous_paid: Decimal = Decimal("0"),
        this_payment: Decimal = Decimal("0"),
        balance_after: Decimal = Decimal("0"),
        payment_method: str = "",
        
        # Optional
        due_date: Optional[datetime] = None,
    ):
        self.school_name = school_name
        self.school_address = school_address
        self.school_phone = school_phone
        self.school_logo_base64 = school_logo_base64
        
        self.receipt_number = receipt_number
        self.date = date or datetime.now()
        
        self.student_name = student_name
        self.class_level = class_level
        self.parent_name = parent_name
        
        self.fees_total = fees_total
        self.previous_paid = previous_paid
        self.this_payment = this_payment
        self.balance_after = balance_after
        self.payment_method = payment_method
        
        self.due_date = due_date
    
    @property
    def total_paid(self) -> Decimal:
        """Total amount paid including this payment."""
        return self.previous_paid + self.this_payment
    
    @property
    def is_fully_paid(self) -> bool:
        """True if balance is zero or negative."""
        return self.balance_after <= 0
    
    @property
    def status_text(self) -> str:
        """Human-readable payment status."""
        if self.balance_after < 0:
            return "OVERPAID"
        elif self.balance_after == 0:
            return "PAID IN FULL"
        else:
            return "PARTIAL PAYMENT"


# =============================================================================
# PDF Generation
# =============================================================================

def generate_receipt_pdf(data: ReceiptData) -> bytes:
    """
    Generate a PDF receipt and return as bytes.
    
    Args:
        data: ReceiptData object with all required information
    
    Returns:
        PDF file as bytes (can be saved to file or sent via WhatsApp)
    """
    # Create PDF in memory
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    width, height = A4  # 595.27 x 841.89 points
    
    # Starting Y position (from top)
    y = height - 1*inch
    
    # -------------------------------------------------------------------------
    # School Logo and Header
    # -------------------------------------------------------------------------
    if data.school_logo_base64:
        try:
            # Decode base64 logo
            logo_data = base64.b64decode(data.school_logo_base64)
            logo_buffer = io.BytesIO(logo_data)
            
            # Draw logo centered
            c.drawImage(
                logo_buffer,
                (width - 1.5*inch) / 2,  # Center horizontally
                y - 1*inch,
                width=1.5*inch,
                height=1*inch,
                preserveAspectRatio=True,
                mask='auto'
            )
            y -= 1.2*inch
        except Exception:
            # Skip logo if there's any error
            pass
    
    # School Name
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, y, data.school_name.upper())
    y -= 0.3*inch
    
    # School Address
    c.setFont("Helvetica", 10)
    c.drawCentredString(width/2, y, data.school_address)
    y -= 0.2*inch
    
    # School Phone
    c.drawCentredString(width/2, y, f"Tel: {data.school_phone}")
    y -= 0.4*inch
    
    # -------------------------------------------------------------------------
    # Receipt Title
    # -------------------------------------------------------------------------
    # Draw a line
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(1*inch, y, width - 1*inch, y)
    y -= 0.3*inch
    
    c.setFont("Helvetica-Bold", 14)
    c.drawCentredString(width/2, y, "PAYMENT RECEIPT")
    y -= 0.3*inch
    
    c.line(1*inch, y, width - 1*inch, y)
    y -= 0.4*inch
    
    # -------------------------------------------------------------------------
    # Receipt Details
    # -------------------------------------------------------------------------
    left_margin = 1*inch
    right_margin = width - 1*inch
    
    c.setFont("Helvetica", 11)
    
    def draw_row(label: str, value: str, bold_value: bool = False):
        nonlocal y
        c.setFont("Helvetica", 11)
        c.drawString(left_margin, y, label)
        if bold_value:
            c.setFont("Helvetica-Bold", 11)
        c.drawRightString(right_margin, y, value)
        y -= 0.25*inch
    
    # Receipt info
    draw_row("Receipt No:", data.receipt_number, bold_value=True)
    receipt_date = data.date if isinstance(data.date, date_type) else data.date.date()
    draw_row("Date:", format_date_nigerian(receipt_date))
    if isinstance(data.date, datetime):
        draw_row("Time:", data.date.strftime("%I:%M %p"))
    else:
        draw_row("Time:", "N/A")
    
    y -= 0.2*inch
    
    # Student info
    draw_row("Student:", data.student_name, bold_value=True)
    draw_row("Class:", data.class_level)
    draw_row("Parent:", data.parent_name)
    
    y -= 0.2*inch
    
    # -------------------------------------------------------------------------
    # Payment Breakdown
    # -------------------------------------------------------------------------
    c.line(left_margin, y, right_margin, y)
    y -= 0.3*inch
    
    draw_row("TERM FEES:", format_naira(data.fees_total))
    draw_row("Previous Payment:", format_naira(data.previous_paid))
    draw_row("This Payment:", format_naira(data.this_payment), bold_value=True)
    
    y -= 0.15*inch
    
    draw_row("TOTAL PAID:", format_naira(data.total_paid), bold_value=True)
    draw_row("BALANCE DUE:", format_naira(data.balance_after), bold_value=True)
    
    y -= 0.15*inch
    
    draw_row("Payment Method:", data.payment_method.replace("_", " ").title())
    
    y -= 0.2*inch
    
    # -------------------------------------------------------------------------
    # Status Section
    # -------------------------------------------------------------------------
    c.line(left_margin, y, right_margin, y)
    y -= 0.4*inch
    
    # Status with color
    c.setFont("Helvetica-Bold", 12)
    
    if data.is_fully_paid:
        c.setFillColor(colors.green)
        status_text = f"Status: {data.status_text} ✓"
    else:
        c.setFillColor(colors.orange)
        status_text = f"Status: {data.status_text}"
    
    c.drawString(left_margin, y, status_text)
    c.setFillColor(colors.black)
    y -= 0.35*inch
    
    # Due date message if partial payment
    if data.balance_after > 0 and data.due_date:
        c.setFont("Helvetica", 10)
        due_date_val = data.due_date if isinstance(data.due_date, date_type) else data.due_date.date()
        due_text = f"Please pay remaining {format_naira(data.balance_after)} by {format_date_nigerian(due_date_val)}"
        c.drawString(left_margin, y, due_text)
        y -= 0.3*inch
    
    # -------------------------------------------------------------------------
    # Footer
    # -------------------------------------------------------------------------
    footer_y = 1.2*inch
    
    c.line(left_margin, footer_y + 0.3*inch, right_margin, footer_y + 0.3*inch)
    
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.gray)
    c.drawCentredString(width/2, footer_y, f"For inquiries: {data.school_phone}")
    c.drawCentredString(width/2, footer_y - 0.2*inch, "Thank you! 🙏")
    c.drawCentredString(width/2, footer_y - 0.4*inch, "Generated by SmartBursar - Turn Debts Into Alerts")
    
    # -------------------------------------------------------------------------
    # Finalize
    # -------------------------------------------------------------------------
    c.showPage()
    c.save()
    
    # Get PDF bytes
    buffer.seek(0)
    return buffer.getvalue()


def save_receipt_to_file(data: ReceiptData, output_path: Path) -> Path:
    """
    Generate a receipt and save to a file.
    
    Args:
        data: ReceiptData object
        output_path: Where to save the PDF
    
    Returns:
        Path to the saved file
    """
    pdf_bytes = generate_receipt_pdf(data)
    
    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write file
    with open(output_path, 'wb') as f:
        f.write(pdf_bytes)
    
    return output_path


# =============================================================================
# Helper Function
# =============================================================================

def create_receipt_from_transaction(
    transaction,  # Transaction model instance
    student,      # Student model instance
    school,       # School model instance
) -> ReceiptData:
    """
    Create a ReceiptData object from database models.
    
    This is a convenience function to easily generate receipts
    from the database models.
    """
    return ReceiptData(
        # School info
        school_name=school.school_name,
        school_address=school.address,
        school_phone=school.phone,
        school_logo_base64=school.logo_base64,
        
        # Receipt info
        receipt_number=transaction.receipt_number,
        date=transaction.date,
        
        # Student info
        student_name=student.full_name,
        class_level=student.class_level,
        parent_name=student.parent_name,
        
        # Payment info
        fees_total=student.fees_total_due,
        previous_paid=transaction.balance_before - student.fees_total_due + transaction.amount,
        this_payment=transaction.amount,
        balance_after=transaction.balance_after,
        payment_method=transaction.method,
        
        # Optional
        due_date=student.due_date,
    )
