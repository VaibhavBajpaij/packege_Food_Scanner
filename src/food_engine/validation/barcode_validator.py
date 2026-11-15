"""Barcode validation, normalization, and format detection for packaged food products.

Supports standard packaged food barcode formats:
- EAN-13: 13 digits (International Article Number)
- UPC-A: 12 digits (Universal Product Code)
- EAN-8: 8 digits (Short format for small packaging)
- UPC-E: 8 digits (or 6-digit zero-suppressed code expanded to 12-digit UPC-A)
- GTIN-14: 14 digits (Wholesale packaging / case code)

Enforces:
- Strict preservation of significant leading zeros.
- Standard Modulo 10 check digit verification.
- Graceful error reporting for unreadable, invalid, or malformed barcodes.
"""

from dataclasses import dataclass, field
import re
from typing import List, Optional


@dataclass
class BarcodeValidationResult:
    """Structured result of barcode validation and normalization."""
    raw_code: str
    is_valid: bool
    format: Optional[str] = None  # "EAN-13", "UPC-A", "EAN-8", "UPC-E", "GTIN-14"
    normalized_code: Optional[str] = None
    lookup_candidates: List[str] = field(default_factory=list)
    status: str = "valid"  # "valid", "absent", "non_numeric", "malformed_length", "invalid_checksum"
    error_message: Optional[str] = None


def calculate_ean_check_digit(digits: str) -> int:
    """Calculates the standard Modulo 10 check digit for an EAN/UPC digit sequence.
    
    The sequence is processed from right to left (excluding the check digit):
    Odd positions from right get weight 3, even positions get weight 1.
    """
    total = 0
    weight = 3
    for d in reversed(digits):
        total += int(d) * weight
        weight = 1 if weight == 3 else 3
    return (10 - (total % 10)) % 10


def expand_upc_e_to_upc_a(upc_e: str) -> Optional[str]:
    """Expands an 8-digit or 6-digit UPC-E code to a 12-digit UPC-A code."""
    code = upc_e.strip()
    if len(code) == 8:
        # Number system digit (first) and check digit (last)
        num_system = code[0]
        payload = code[1:7]
        # check_digit = code[7]
    elif len(code) == 6:
        num_system = "0"
        payload = code
    else:
        return None

    if not payload.isdigit() or len(payload) != 6:
        return None

    d1, d2, d3, d4, d5, d6 = payload

    if d6 in "012":
        mfg = num_system + d1 + d2 + d6 + "00"
        prod = "00" + d3 + d4 + d5
    elif d6 == "3":
        mfg = num_system + d1 + d2 + d3 + "00"
        prod = "000" + d4 + d5
    elif d6 == "4":
        mfg = num_system + d1 + d2 + d3 + d4 + "0"
        prod = "0000" + d5
    else:  # d6 in '56789'
        mfg = num_system + d1 + d2 + d3 + d4 + d5
        prod = "0000" + d6

    candidate_11 = mfg + prod
    check_digit = str(calculate_ean_check_digit(candidate_11))
    return candidate_11 + check_digit


class BarcodeValidator:
    """Validates and normalizes barcodes for food product lookup."""

    @classmethod
    def validate(cls, raw_barcode: Optional[str]) -> BarcodeValidationResult:
        """Validates barcode format, check digit, and normalizes candidate lookup strings."""
        if raw_barcode is None or not str(raw_barcode).strip():
            return BarcodeValidationResult(
                raw_code="",
                is_valid=False,
                status="absent",
                error_message="Barcode is absent or empty.",
            )

        clean = re.sub(r"[\s\-_]+", "", str(raw_barcode).strip())

        if not clean.isdigit():
            return BarcodeValidationResult(
                raw_code=str(raw_barcode),
                is_valid=False,
                status="non_numeric",
                error_message=f"Barcode contains non-digit characters: '{clean}'",
            )

        length = len(clean)

        # 1. EAN-8 (8 digits)
        if length == 8:
            expected_chk = calculate_ean_check_digit(clean[:-1])
            actual_chk = int(clean[-1])
            if actual_chk != expected_chk:
                # Check if it could be a UPC-E with check digit
                upc_a_expanded = expand_upc_e_to_upc_a(clean)
                if upc_a_expanded and int(upc_a_expanded[-1]) == actual_chk:
                    return BarcodeValidationResult(
                        raw_code=str(raw_barcode),
                        is_valid=True,
                        format="UPC-E",
                        normalized_code=clean,
                        lookup_candidates=[clean, upc_a_expanded, "0" + upc_a_expanded],
                        status="valid",
                    )
                return BarcodeValidationResult(
                    raw_code=str(raw_barcode),
                    is_valid=False,
                    format="EAN-8",
                    normalized_code=clean,
                    status="invalid_checksum",
                    error_message=f"Invalid EAN-8 checksum: expected {expected_chk}, got {actual_chk}",
                )
            return BarcodeValidationResult(
                raw_code=str(raw_barcode),
                is_valid=True,
                format="EAN-8",
                normalized_code=clean,
                lookup_candidates=[clean],
                status="valid",
            )

        # 2. UPC-E 6-digit variant
        if length == 6:
            expanded = expand_upc_e_to_upc_a(clean)
            if expanded:
                return BarcodeValidationResult(
                    raw_code=str(raw_barcode),
                    is_valid=True,
                    format="UPC-E",
                    normalized_code=clean,
                    lookup_candidates=[clean, expanded, "0" + expanded],
                    status="valid",
                )

        # 3. UPC-A (12 digits)
        if length == 12:
            expected_chk = calculate_ean_check_digit(clean[:-1])
            actual_chk = int(clean[-1])
            if actual_chk != expected_chk:
                return BarcodeValidationResult(
                    raw_code=str(raw_barcode),
                    is_valid=False,
                    format="UPC-A",
                    normalized_code=clean,
                    status="invalid_checksum",
                    error_message=f"Invalid UPC-A checksum: expected {expected_chk}, got {actual_chk}",
                )
            # UPC-A can be looked up as 12-digit UPC-A or 13-digit EAN-13 (prefixed with '0')
            ean13_equiv = "0" + clean
            return BarcodeValidationResult(
                raw_code=str(raw_barcode),
                is_valid=True,
                format="UPC-A",
                normalized_code=clean,
                lookup_candidates=[clean, ean13_equiv],
                status="valid",
            )

        # 4. EAN-13 (13 digits)
        if length == 13:
            expected_chk = calculate_ean_check_digit(clean[:-1])
            actual_chk = int(clean[-1])
            if actual_chk != expected_chk:
                return BarcodeValidationResult(
                    raw_code=str(raw_barcode),
                    is_valid=False,
                    format="EAN-13",
                    normalized_code=clean,
                    status="invalid_checksum",
                    error_message=f"Invalid EAN-13 checksum: expected {expected_chk}, got {actual_chk}",
                )
            candidates = [clean]
            # If starts with '0', the 12-digit suffix is a valid UPC-A
            if clean.startswith("0"):
                candidates.append(clean[1:])
            return BarcodeValidationResult(
                raw_code=str(raw_barcode),
                is_valid=True,
                format="EAN-13",
                normalized_code=clean,
                lookup_candidates=candidates,
                status="valid",
            )

        # 5. GTIN-14 (14 digits)
        if length == 14:
            expected_chk = calculate_ean_check_digit(clean[:-1])
            actual_chk = int(clean[-1])
            if actual_chk != expected_chk:
                return BarcodeValidationResult(
                    raw_code=str(raw_barcode),
                    is_valid=False,
                    format="GTIN-14",
                    normalized_code=clean,
                    status="invalid_checksum",
                    error_message=f"Invalid GTIN-14 checksum: expected {expected_chk}, got {actual_chk}",
                )
            candidates = [clean]
            if clean.startswith("0"):
                candidates.append(clean[1:])
                if clean[1:].startswith("0"):
                    candidates.append(clean[2:])
            return BarcodeValidationResult(
                raw_code=str(raw_barcode),
                is_valid=True,
                format="GTIN-14",
                normalized_code=clean,
                lookup_candidates=candidates,
                status="valid",
            )

        # Unsupported length
        return BarcodeValidationResult(
            raw_code=str(raw_barcode),
            is_valid=False,
            normalized_code=clean,
            status="malformed_length",
            error_message=f"Barcode length of {length} digits is not a standard format (must be 8, 12, 13, or 14 digits).",
        )
