"""Unit tests for Unified Food Package Scanner, Barcode Normalization, and OCR Recovery.

Verifies:
1. 11-digit UPC-A with missing leading zero normalizes to valid 12-digit UPC-A.
2. 7-digit EAN-8 with missing leading zero normalizes to valid 8-digit EAN-8.
3. Checksum mismatch generates candidate with corrected check digit.
4. Extracting printed barcode numbers from OCR text lines.
5. Graceful product matching when barcode has scan noise or is absent.
6. Tested images catalog loader finds real packaging photos with metadata.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.validation.barcode_validator import BarcodeValidator, calculate_ean_check_digit
from food_engine.product_matching.matcher import ProductMatcher
from app import load_tested_images_catalog, decode_barcode_from_image


def test_11_digit_upc_a_leading_zero_normalization():
    """11-digit UPC-A (where leading 0 was omitted by scanner or user) is normalized to valid 12-digit UPC-A."""
    # 028400070560 is Doritos UPC-A. If scanner drops leading zero: '28400070560'
    res = BarcodeValidator.validate("28400070560")
    assert res.is_valid is True
    assert res.format == "UPC-A"
    assert res.normalized_code == "028400070560"
    assert "028400070560" in res.lookup_candidates
    assert "0028400070560" in res.lookup_candidates


def test_7_digit_ean_8_leading_zero_normalization():
    """7-digit code where prepending 0 forms valid EAN-8 is normalized."""
    # Test with standard EAN-8 where leading zero makes valid Modulo 10
    # Let's construct a valid 8-digit EAN-8 starting with 0:
    # Digits: 0 + 123456 -> check digit:
    chk = calculate_ean_check_digit("0123456")
    code_8 = f"0123456{chk}"
    code_7 = f"123456{chk}"

    res = BarcodeValidator.validate(code_7)
    assert res.is_valid is True
    assert res.format == "EAN-8"
    assert res.normalized_code == code_8


def test_checksum_mismatch_populates_corrected_candidate():
    """Invalid checksum does not wipe lookup candidates; includes corrected checksum candidate."""
    # 8901030000003 is valid EAN-13. Change last digit to 9.
    bad_code = "8901030000009"
    res = BarcodeValidator.validate(bad_code)
    assert res.is_valid is False
    assert res.status == "invalid_checksum"
    assert "8901030000003" in res.lookup_candidates
    assert bad_code in res.lookup_candidates


def test_extract_barcode_from_ocr_lines():
    """Extracts printed barcode numbers from OCR text lines."""
    # Case 1: Indian EAN-13 printed on package label
    lines = [
        "NUTRITION INFORMATION",
        "Per 100g",
        "8901058017687",
        "Net Weight: 70g",
    ]
    extracted = BarcodeValidator.extract_barcode_from_ocr_lines(lines)
    assert extracted == "8901058017687"

    # Case 2: Spaced digits under barcode bars (e.g. 0 28400 07056 0)
    lines_spaced = [
        "Manufactured in USA",
        "0 28400 07056 0",
        "Best Before 2026",
    ]
    extracted_spaced = BarcodeValidator.extract_barcode_from_ocr_lines(lines_spaced)
    assert extracted_spaced == "028400070560"


def test_product_matcher_falls_through_when_barcode_invalid_but_ocr_present():
    """Product matcher does not abort early if barcode is invalid when OCR text is provided."""
    matcher = ProductMatcher(repo_root=REPO_ROOT)
    # Give an invalid barcode but valid OCR text of a known product
    res = matcher.match(
        barcode="12345678999",  # invalid checksum or length
        ocr_lines=["Parle-G", "Gluco Biscuits", "Parle Products Pvt Ltd"],
    )
    # Should not abort with match_type='invalid_barcode'; should evaluate brand/name or OCR
    assert res["match_type"] != "invalid_barcode"


def test_tested_images_catalog_loader():
    """Verifies that the 40 real food packet images catalog loads correctly."""
    catalog = load_tested_images_catalog()
    assert isinstance(catalog, list)
    assert len(catalog) >= 30
    india_samples = [c for c in catalog if c.get("country") == "India"]
    world_samples = [c for c in catalog if c.get("country") != "India"]
    assert len(india_samples) >= 10
    assert len(world_samples) >= 20
    for item in catalog[:5]:
        assert Path(item["local_path"]).exists()
