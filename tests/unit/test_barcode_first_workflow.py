"""Unit tests for Barcode-First Food Scanner Workflow (Scenarios 1 - 6).

Verifies:
- Scenario 1: Valid barcode with a complete product record -> action_required='proceed'
- Scenario 2: Valid barcode with a known product but missing nutrition fields -> action_required='scan_label_recommended'
- Scenario 3: Unknown barcode -> action_required='scan_label_required'
- Scenario 4: Barcode absent -> graceful handling, action_required='scan_label_required'
- Scenario 5: Barcode unreadable or invalid checksum -> action_required='scan_label_required'
- Scenario 6: Successful fallback to back-of-package scanning when barcode lookup is incomplete
"""

from pathlib import Path
from food_engine.engine import FoodIntelligenceEngine
from food_engine.validation.barcode_validator import BarcodeValidator, calculate_ean_check_digit


def test_scenario_1_valid_barcode_complete_product():
    """Scenario 1: Valid barcode with a complete product record."""
    engine = FoodIntelligenceEngine()
    # Code 0000101209159 exists in products.db with complete macros and ingredients
    res = engine.scan_barcode("0000101209159")

    assert res["workflow_step"] == "barcode_scan"
    assert res["barcode_validation"]["is_valid"] is True
    assert res["barcode_validation"]["format"] == "EAN-13"
    assert res["product_match"]["status"] == "exact_barcode_match"
    assert res["product_match"]["product_name"] is not None
    assert res["completeness_audit"]["is_complete"] is True
    assert res["action_required"] == "proceed"
    assert "complete nutrition facts" in res["prompt_message"]
    assert res["product_data"] is not None


def test_scenario_2_valid_barcode_incomplete_nutrients(monkeypatch):
    """Scenario 2: Valid barcode with a known product but missing nutrition fields."""
    engine = FoodIntelligenceEngine()

    # Simulate a product matcher returning a product with missing macros
    fake_incomplete_product = {
        "status": "exact_barcode_match",
        "match_type": "exact_barcode",
        "product_name": "Sample Biscuit Incomplete",
        "barcode": "8901030000003",
        "brand": "TestBrand",
        "source": "Open Food Facts",
        "confidence": 1.0,
        "matched_data": {
            "product_name": "Sample Biscuit Incomplete",
            "brands": "TestBrand",
            "code": "8901030000003",
            "ingredients_text": "Wheat flour, sugar",
            "serving_size": "30 g",
            "nutrients": {
                # Only energy declared, protein, fat, carbohydrates missing
                "energy_kcal": 450.0,
            }
        }
    }
    monkeypatch.setattr(engine.product_matcher, "match", lambda *args, **kwargs: fake_incomplete_product)

    res = engine.scan_barcode("8901030000003")

    assert res["barcode_validation"]["is_valid"] is True
    assert res["product_match"]["status"] == "exact_barcode_match"
    assert res["completeness_audit"]["is_complete"] is False
    assert res["action_required"] == "scan_label_recommended"
    assert "nutrition information is incomplete" in res["prompt_message"]
    assert "protein_g" in res["completeness_audit"]["missing_fields"]
    assert "carbohydrates_g" in res["completeness_audit"]["missing_fields"]
    assert "total_fat_g" in res["completeness_audit"]["missing_fields"]


def test_scenario_3_unknown_barcode():
    """Scenario 3: Unknown barcode with valid format/checksum."""
    engine = FoodIntelligenceEngine()
    # 9999999999994 has valid Modulo-10 checksum but does not exist in local database
    res = engine.scan_barcode("9999999999994", allow_online=False)

    assert res["barcode_validation"]["is_valid"] is True
    assert res["barcode_validation"]["status"] == "valid"
    assert res["product_match"]["status"] == "unmatched"
    assert res["completeness_audit"]["is_complete"] is False
    assert res["action_required"] == "scan_label_required"
    assert "not found in the database" in res["prompt_message"]


def test_scenario_4_barcode_absent():
    """Scenario 4: Barcode is absent or None."""
    engine = FoodIntelligenceEngine()
    res = engine.scan_barcode(None)

    assert res["barcode_validation"]["is_valid"] is False
    assert res["barcode_validation"]["status"] == "absent"
    assert res["product_match"]["status"] == "unmatched"
    assert res["action_required"] == "scan_label_required"
    assert "absent" in res["prompt_message"]


def test_scenario_5_barcode_unreadable_or_invalid():
    """Scenario 5: Barcode unreadable, malformed, or has invalid checksum."""
    engine = FoodIntelligenceEngine()

    # Invalid checksum
    res_bad_chk = engine.scan_barcode("8901030000001")
    assert res_bad_chk["barcode_validation"]["is_valid"] is False
    assert res_bad_chk["barcode_validation"]["status"] == "invalid_checksum"
    assert res_bad_chk["action_required"] == "scan_label_required"
    assert "invalid_checksum" in res_bad_chk["prompt_message"]

    # Malformed length
    res_short = engine.scan_barcode("12345")
    assert res_short["barcode_validation"]["is_valid"] is False
    assert res_short["barcode_validation"]["status"] == "malformed_length"
    assert res_short["action_required"] == "scan_label_required"

    # Non-numeric
    res_non_num = engine.scan_barcode("890103000000X")
    assert res_non_num["barcode_validation"]["is_valid"] is False
    assert res_non_num["barcode_validation"]["status"] == "non_numeric"


def test_scenario_6_successful_fallback_to_label_scan():
    """Scenario 6: Successful fallback to back-of-package scanning when barcode lookup is incomplete."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    biscuit_img = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"
    assert biscuit_img.exists()

    engine = FoodIntelligenceEngine(repo_root=repo_root)

    # 1. Barcode step returns scan_label_recommended
    barcode_res = engine.scan_barcode("9999999999994", allow_online=False)
    assert barcode_res["action_required"] == "scan_label_required"

    # 2. Fallback to back-of-package label scan
    label_res = engine.scan_package_label(
        label_image=biscuit_img,
        barcode=barcode_res["barcode_validation"]["normalized_code"],
        package_weight_g=120.0,
    )

    # Verify that label OCR succeeded and populated complete nutrition
    assert label_res["nutrition"]["nutrients"]["energy_kcal"]["value"] == 460.0
    assert label_res["nutrition"]["nutrients"]["energy_kcal"]["status"] == "declared"
    assert label_res["nutrition"]["nutrients"]["protein_g"]["value"] == 7.5
    assert label_res["nutrition"]["nutrients"]["carbohydrates_g"]["value"] == 68.0
    assert label_res["nutrition"]["nutrients"]["total_fat_g"]["value"] == 18.0
    assert label_res["ingredients"]["parsed_ingredients"]
    assert "Wheat" in label_res["ingredients"]["declared_allergens"]
