"""Integration tests for the complete end-to-end Food Intelligence Engine."""

from pathlib import Path
from food_engine.engine import FoodIntelligenceEngine


def test_biscuit_packet_end_to_end():
    repo_root = Path(__file__).resolve().parent.parent.parent
    biscuit_img = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"
    assert biscuit_img.exists()

    engine = FoodIntelligenceEngine(repo_root=repo_root)
    result = engine.process_image(
        image_input=biscuit_img,
        package_weight_g=120.0
    )

    # Validate output schema fields
    assert result["engine_version"] == "0.1.0"
    assert result["image_metadata"]["width"] == 800
    assert result["image_metadata"]["height"] == 1000

    # Validate ingredients & allergens
    ing = result["ingredients"]
    assert "Wheat" in ing["declared_allergens"]
    assert "Milk / Dairy" in ing["declared_allergens"]
    assert "Soybeans / Soy" in ing["declared_allergens"]
    assert ing["review_required"] is True

    # Validate nutrients per 100g
    nuts = result["nutrition"]["nutrients"]
    assert nuts["energy_kcal"]["value"] == 460.0
    assert nuts["protein_g"]["value"] == 7.5
    assert nuts["carbohydrates_g"]["value"] == 68.0
    assert nuts["sugars_g"]["value"] == 24.5
    assert nuts["total_fat_g"]["value"] == 18.0
    assert nuts["sodium_mg"]["value"] == 380.0
    assert nuts["salt_g"]["value"] == 0.95

    # Validate package scaling (120g net weight = 1.2x)
    pkg = result["calculated_package_totals"]["calculated_nutrients"]
    assert pkg["energy_kcal"]["value"] == 552.0
    assert pkg["protein_g"]["value"] == 9.0
    assert pkg["carbohydrates_g"]["value"] == 81.6
    assert pkg["sodium_mg"]["value"] == 456.0

    # Validate health alerts
    alerts = result["evidence_based_alerts"]
    titles = [a["title"] for a in alerts]
    assert "High Sugar Content" in titles
    assert "High Saturated Fat Content" in titles
    assert "Declared Allergen: Wheat" in titles


def test_beverage_bottle_end_to_end():
    repo_root = Path(__file__).resolve().parent.parent.parent
    juice_img = repo_root / "tests" / "fixtures" / "sample_juice_bottle.png"
    assert juice_img.exists()

    engine = FoodIntelligenceEngine(repo_root=repo_root)
    result = engine.process_image(
        image_input=juice_img,
        package_volume_ml=250.0
    )

    assert result["nutrition"]["basis"] == "per_100_ml"
    nuts = result["nutrition"]["nutrients"]
    assert nuts["energy_kcal"]["value"] == 48.0
    assert nuts["carbohydrates_g"]["value"] == 11.4
    assert nuts["vitamin_c_mg"]["value"] == 24.0

    # 250ml scaling = 2.5x
    pkg = result["calculated_package_totals"]["calculated_nutrients"]
    assert pkg["energy_kcal"]["value"] == 120.0
    assert pkg["vitamin_c_mg"]["value"] == 60.0


def test_offline_local_clean_restart():
    """Simulates fresh initialization with network disconnected."""
    engine = FoodIntelligenceEngine()
    # Check that matcher and databases load cleanly without internet
    res = engine.product_matcher.match(barcode="0000101209159")
    assert res["status"] == "exact_barcode_match"
    assert res["barcode"] == "0000101209159"
