"""Unit tests for Label OCR and Multi-Image Ingestion (Scenarios 7, 8, 9, 18, 22).

Verifies:
- Scenario 7: OCR extraction reads actual image pixels (no synthetic fallbacks or metadata tricks).
- Scenario 8: Nutrition table and ingredients list in the same image.
- Scenario 9: Nutrition table and ingredients supplied in separate images.
- Scenario 18: Uncertain OCR triggers review required / uncertainty flag rather than fabricating data.
- Scenario 22: Ingredient and allergen extraction preserves original text.
"""

from pathlib import Path
from PIL import Image
import numpy as np

from food_engine.engine import FoodIntelligenceEngine
from food_engine.ingredient_parser.parser import IngredientParser
from food_engine.ocr.ocr_engine import OCREngine


def test_scenario_7_ocr_reads_actual_image_pixels():
    """Scenario 7: OCR extraction operates on actual image pixels, returning coordinates & confidence."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    biscuit_img = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"
    assert biscuit_img.exists()

    ocr_engine = OCREngine(repo_root=repo_root)
    result = ocr_engine.run_ocr(biscuit_img)

    assert "paddleocr" in result["engine"]
    assert "PP-OCRv4" in result["model_version"]
    assert result["line_count"] > 10
    assert len(result["lines"]) > 10

    # Ensure bounding polygon box coordinates and confidence exist on real detections
    first_line = result["lines"][0]
    assert "text" in first_line
    assert "confidence" in first_line
    assert float(first_line["confidence"]) > 0.50
    assert "bounding_box" in first_line
    assert len(first_line["bounding_box"]) == 4  # 4 polygon corners


def test_scenario_8_nutrition_and_ingredients_single_image():
    """Scenario 8: Nutrition table and ingredients list in the same image."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    biscuit_img = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"

    engine = FoodIntelligenceEngine(repo_root=repo_root)
    payload = engine.process_image(biscuit_img, package_weight_g=120.0)

    # Both nutrition and ingredients are populated from one image
    nuts = payload["nutrition"]["nutrients"]
    assert nuts["energy_kcal"]["value"] == 460.0
    assert nuts["protein_g"]["value"] == 7.5

    ing = payload["ingredients"]
    assert len(ing["parsed_ingredients"]) >= 4
    assert "Wheat" in ing["declared_allergens"]
    assert "Milk / Dairy" in ing["declared_allergens"]
    assert "Soybeans / Soy" in ing["declared_allergens"]


def test_scenario_9_nutrition_and_ingredients_separate_images(tmp_path):
    """Scenario 9: Nutrition table and ingredients supplied in separate images."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    biscuit_img_path = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"
    pil_img = Image.open(biscuit_img_path)

    # Biscuit packet layout: top part (y: 0 to 280) has ingredients/allergens;
    # lower part (y: 280 to 850) has Nutrition Facts table.
    w, h = pil_img.size
    ing_crop = pil_img.crop((0, 0, w, 280))
    nut_crop = pil_img.crop((0, 270, w, 850))

    nut_path = tmp_path / "panel_nutrition.png"
    ing_path = tmp_path / "panel_ingredients.png"
    nut_crop.save(nut_path)
    ing_crop.save(ing_path)

    engine = FoodIntelligenceEngine(repo_root=repo_root)
    payload = engine.scan_package_label(
        nutrition_image=nut_path,
        ingredients_image=ing_path,
        package_weight_g=120.0,
    )

    # Validate that both nutrition from panel 1 and ingredients from panel 2 were unified
    assert payload["nutrition"]["nutrients"]["energy_kcal"]["value"] == 460.0
    assert payload["nutrition"]["nutrients"]["protein_g"]["value"] == 7.5
    assert payload["nutrition"]["nutrients"]["carbohydrates_g"]["value"] == 68.0

    ing = payload["ingredients"]
    assert "Wheat" in ing["declared_allergens"]
    assert len(ing["parsed_ingredients"]) >= 2
    assert "dual_images" in payload["input_image"]


def test_scenario_18_uncertain_ocr_triggers_review_not_fabricated():
    """Scenario 18: Uncertain or garbled OCR text triggers review required rather than fabricated data."""
    # Garbled OCR lines with low confidence and no recognizable nutrient names
    garbled_lines = [
        {"text": "X9#8kj a?!!", "confidence": 0.25, "bounding_box": [[0, 0], [10, 0], [10, 10], [0, 10]]},
        {"text": "~~qqwwoop~~", "confidence": 0.30, "bounding_box": [[0, 20], [10, 20], [10, 30], [0, 30]]},
    ]
    engine = FoodIntelligenceEngine()
    payload = engine.process_image(
        image_input="tests/fixtures/sample_biscuit_packet.png",
        override_ocr_lines=[l["text"] for l in garbled_lines],
    )

    # Must flag manual review required and must NOT fabricate zero values
    assert payload["data_quality"]["manual_review_required"] is True
    nuts = payload["nutrition"]["nutrients"]
    for k in ["energy_kcal", "protein_g", "carbohydrates_g", "total_fat_g"]:
        assert nuts[k]["status"] == "missing"
        assert nuts[k]["value"] is None  # Missing values are never fabricated


def test_scenario_22_ingredients_and_allergens_preserve_original_text():
    """Scenario 22: Ingredient and allergen extraction preserves raw printed text."""
    raw_text = "INGREDIENTS: Wheat Flour (62%), Sugar, Palm Oil, Cocoa Solids (4.5%), Emulsifier (INS 322). CONTAINS WHEAT AND SOY. MAY CONTAIN TRACES OF MILK AND TREE NUTS."
    parsed = IngredientParser.parse_from_text(raw_text)

    # Preserves original text exactly
    assert "Wheat Flour (62%)" in parsed["original_text"]
    assert "Cocoa Solids (4.5%)" in parsed["original_text"]

    # Separates declared allergens from trace precautionary statements
    assert "Wheat" in parsed["declared_allergens"]
    assert "Soybeans / Soy" in parsed["declared_allergens"]
    assert "Milk / Dairy" in parsed["potential_traces"]
    assert any("Tree Nuts" in t for t in parsed["potential_traces"])
    assert parsed["review_required"] is True
