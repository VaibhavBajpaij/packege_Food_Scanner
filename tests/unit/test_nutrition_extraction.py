"""Unit tests for Stage 5: Nutrition Table Extraction and Missing Field Audit."""

from food_engine.nutrition_extraction.extractor import NutritionExtractor


def test_standard_per_100g_extraction():
    lines = [
        "NUTRITION INFORMATION",
        "Values per 100g:",
        "Energy: 450 kcal",
        "Protein: 8.0 g",
        "Total Carbohydrates: 65.0 g",
        "Total Sugars: 20.0 g",
        "Dietary Fibre: 5.5 g",
        "Total Fat: 16.0 g",
        "Saturated Fat: 7.0 g",
        "Trans Fat: 0.0 g",
        "Sodium: 400 mg",
    ]
    res = NutritionExtractor.extract(lines)
    assert res["basis"] == "per_100_g"
    nuts = res["nutrients"]

    assert nuts["energy_kcal"]["value"] == 450.0
    assert nuts["energy_kcal"]["status"] == "declared"
    assert nuts["protein_g"]["value"] == 8.0
    assert nuts["carbohydrates_g"]["value"] == 65.0
    assert nuts["total_fat_g"]["value"] == 16.0
    assert nuts["sodium_mg"]["value"] == 400.0

    # Salt was missing on label but should be automatically calculated from sodium
    assert nuts["salt_g"]["status"] == "calculated"
    assert nuts["salt_g"]["value"] == 1.0  # (400 / 1000) * 2.5


def test_missing_fields_never_assigned_zero():
    lines = [
        "NUTRITION FACTS",
        "Energy: 200 kcal",
        "Protein: 5.0 g",
    ]
    res = NutritionExtractor.extract(lines)
    nuts = res["nutrients"]

    # Calcium and Iron were not declared
    assert nuts["calcium_mg"]["value"] is None
    assert nuts["calcium_mg"]["status"] == "missing"
    assert nuts["iron_mg"]["value"] is None
    assert nuts["iron_mg"]["status"] == "missing"

    # Core missing fields tracked
    assert "carbohydrates_g" in res["missing_fields"]
    assert "total_fat_g" in res["missing_fields"]


def test_per_100ml_liquid_basis_and_serving_size():
    lines = [
        "NUTRITION DECLARATION",
        "Serving Size: 250 ml",
        "Per 100 ml",
        "Energy: 45 kcal",
        "Carbohydrates: 11.0 g",
        "Sugars: 10.5 g",
        "Fat: 0.0 g",
    ]
    res = NutritionExtractor.extract(lines)
    assert res["basis"] == "per_100_ml"
    assert res["serving_size_ml"] == 250.0
    assert res["nutrients"]["energy_kcal"]["value"] == 45.0
