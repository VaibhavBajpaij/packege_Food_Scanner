"""Unit tests for Difficult Nutrition Label Cases (Scenarios 10 - 17).

Verifies:
- Scenario 10: Decimal comma and decimal point handling (e.g. 5.3 g and 5,3 g).
- Scenario 11: <1 g and <= 0.5 g inequality handling (never convert <1g to 1g, preserve bound).
- Scenario 12: Correct separation of nutrient amounts and percentage RI/DV columns (14% RI is not 14g).
- Scenario 13: Correct serving basis and unit normalization (per 100g vs per serving).
- Scenario 14: Sodium/salt conversions with recorded calculation provenance.
- Scenario 15: Printed zero values retained as declared values (value=0.0, status='declared').
- Scenario 16: Missing fields never silently converted to zero (value=None, status='missing').
- Scenario 17: Adjacent nutrient rows do not bleed into each other (trans fat not assigned to saturated fat).
"""

from food_engine.nutrition_extraction.extractor import NutritionExtractor, parse_number
from food_engine.nutrition_extraction.structured import extract_structured
from food_engine.nutrition_calculation.calculator import NutritionCalculator


def test_scenario_10_decimal_points_and_commas():
    """Scenario 10: Decimals formatted with dot or European comma are parsed accurately."""
    assert parse_number("5.3") == 5.3
    assert parse_number("5,3") == 5.3
    assert parse_number("0.75") == 0.75
    assert parse_number("0,75") == 0.75
    assert parse_number("1,098") == 1098.0  # Indian/EU thousands separator

    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Protein 5,3 g", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
        {"text": "Total Fat 12.8 g", "confidence": 0.95, "bounding_box": [[10, 70], [150, 70], [150, 90], [10, 90]]},
    ]
    res = extract_structured(ocr_records)
    assert res["nutrients"]["protein_g"]["value"] == 5.3
    assert res["nutrients"]["total_fat_g"]["value"] == 12.8


def test_scenario_11_inequality_handling():
    """Scenario 11: Inequalities like <1 g and <= 0.5 g are preserved with upper_bound=True and never converted to 1 g."""
    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Total Fat < 1 g", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
        {"text": "Sugars <= 0.5 g", "confidence": 0.95, "bounding_box": [[10, 70], [150, 70], [150, 90], [10, 90]]},
        {"text": "Trans Fat less than 0.1 g", "confidence": 0.95, "bounding_box": [[10, 100], [150, 100], [150, 120], [10, 120]]},
    ]
    res = extract_structured(ocr_records)
    tf = res["nutrients"]["total_fat_g"]
    assert tf["value"] == 1.0
    assert tf["upper_bound"] is True
    assert tf["comparator"] == "<"

    sug = res["nutrients"]["sugars_g"]
    assert sug["value"] == 0.5
    assert sug["upper_bound"] is True
    assert sug["comparator"] == "≤"

    trans = res["nutrients"]["trans_fat_g"]
    assert trans["value"] == 0.1
    assert trans["upper_bound"] is True
    assert trans["comparator"] == "<"


def test_scenario_12_percentage_dv_ri_separation():
    """Scenario 12: %DV / %RI column numbers are strictly separated and never parsed as nutrient quantities."""
    # Line has both amount '14 g' and daily value '18%' or protein with '20% DV'
    ocr_records = [
        {"text": "Nutrition Facts", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Per 100g % Daily Value", "confidence": 0.95, "bounding_box": [[10, 35], [250, 35], [250, 50], [10, 50]]},
        {"text": "Protein 7.5 g 15%", "confidence": 0.95, "bounding_box": [[10, 60], [250, 60], [250, 80], [10, 80]]},
        {"text": "Total Fat 18 g 23%", "confidence": 0.95, "bounding_box": [[10, 90], [250, 90], [250, 110], [10, 110]]},
    ]
    res = extract_structured(ocr_records)
    # Must pick 7.5g and 18g, NEVER 15g or 23g
    assert res["nutrients"]["protein_g"]["value"] == 7.5
    assert res["nutrients"]["total_fat_g"]["value"] == 18.0


def test_scenario_13_serving_basis_and_unit_normalization():
    """Scenario 13: Correct basis detection (per 100g vs per serving) and mg to g normalization."""
    # Test mg to g conversion for sodium vs salt
    ocr_records = [
        {"text": "Nutrition Facts per serving (30g)", "confidence": 0.95, "bounding_box": [[10, 10], [250, 10], [250, 30], [10, 30]]},
        {"text": "Energy 150 kcal", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
        {"text": "Sodium 120 mg", "confidence": 0.95, "bounding_box": [[10, 70], [150, 70], [150, 90], [10, 90]]},
    ]
    res = extract_structured(ocr_records)
    assert res["basis"] == "per_serving"
    assert res["serving_size_g"] == 30.0
    assert res["nutrients"]["sodium_mg"]["value"] == 120.0
    assert res["nutrients"]["sodium_mg"]["unit"] == "mg"


def test_scenario_14_sodium_salt_conversions_provenance():
    """Scenario 14: Sodium to salt conversion records calculation provenance."""
    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Salt 1.0 g", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
    ]
    res = extract_structured(ocr_records)
    assert res["nutrients"]["salt_g"]["status"] == "declared"
    assert res["nutrients"]["salt_g"]["value"] == 1.0

    # Sodium must be calculated with provenance 'calculated'
    assert res["nutrients"]["sodium_mg"]["status"] == "calculated"
    assert res["nutrients"]["sodium_mg"]["value"] == 400.0  # 1.0g salt = 400mg sodium


def test_scenario_15_printed_zeros_retained_as_declared():
    """Scenario 15: Printed zero values (e.g. '0 g Trans Fat') are retained as declared zeros."""
    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Trans Fat 0 g", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
        {"text": "Cholesterol 0 mg", "confidence": 0.95, "bounding_box": [[10, 70], [150, 70], [150, 90], [10, 90]]},
    ]
    res = extract_structured(ocr_records)
    assert res["nutrients"]["trans_fat_g"]["value"] == 0.0
    assert res["nutrients"]["trans_fat_g"]["status"] == "declared"

    assert res["nutrients"]["cholesterol_mg"]["value"] == 0.0
    assert res["nutrients"]["cholesterol_mg"]["status"] == "declared"


def test_scenario_16_missing_fields_never_converted_to_zero():
    """Scenario 16: Fields absent from packaging are strictly 'missing' with value None, never 0.0."""
    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Energy 200 kcal", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 60], [10, 60]]},
    ]
    res = extract_structured(ocr_records)
    # Vitamin D and Calcium are not on this label
    assert res["nutrients"]["vitamin_d_mcg"]["status"] == "missing"
    assert res["nutrients"]["vitamin_d_mcg"]["value"] is None

    assert res["nutrients"]["calcium_mg"]["status"] == "missing"
    assert res["nutrients"]["calcium_mg"]["value"] is None


def test_scenario_17_adjacent_nutrient_rows_do_not_bleed():
    """Scenario 17: Adjacent rows (e.g. Saturated Fat followed immediately by Trans Fat) do not bleed."""
    ocr_records = [
        {"text": "Nutrition Facts per 100g", "confidence": 0.95, "bounding_box": [[10, 10], [200, 10], [200, 30], [10, 30]]},
        {"text": "Total Fat 15 g", "confidence": 0.95, "bounding_box": [[10, 40], [150, 40], [150, 58], [10, 58]]},
        {"text": "Saturated Fat 8 g", "confidence": 0.95, "bounding_box": [[10, 60], [150, 60], [150, 78], [10, 78]]},
        {"text": "Trans Fat 0.2 g", "confidence": 0.95, "bounding_box": [[10, 80], [150, 80], [150, 98], [10, 98]]},
    ]
    res = extract_structured(ocr_records)
    assert res["nutrients"]["total_fat_g"]["value"] == 15.0
    assert res["nutrients"]["saturated_fat_g"]["value"] == 8.0
    assert res["nutrients"]["trans_fat_g"]["value"] == 0.2
