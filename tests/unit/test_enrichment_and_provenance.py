"""Unit tests for Data Enrichment, Precedence, Conflicts, Robustness & Cleanup (Scenarios 19, 20, 21, 23, 24).

Verifies:
- Scenario 19: Database enrichment fills missing fields without overwriting label-declared values.
- Scenario 20: Conflicting sources are recorded and handled predictably.
- Scenario 21: Incorrect or unrelated product matches are rejected.
- Scenario 23: API failures, timeouts, and offline mode are handled safely.
- Scenario 24: Cleanup does not break imports, CLI entry points, or production workflows.
"""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

import pytest

from food_engine.engine import FoodIntelligenceEngine
from food_engine.product_matching.matcher import ProductMatcher
from food_engine.product_matching.nutrient_fusion import NutrientFusion
from food_engine.reporting.output_builder import format_text_report
from food_engine.validation.barcode_validator import BarcodeValidator


def test_scenario_19_enrichment_preserves_declared_and_fills_missing():
    """Scenario 19: Database enrichment fills missing fields without overwriting label-declared values."""
    # Label declared values
    ocr_nutrients = {
        "energy_kcal": {"value": 250.0, "unit": "kcal", "status": "declared", "confidence": 0.95},
        "protein_g": {"value": 5.0, "unit": "g", "status": "declared", "confidence": 0.92},
        "carbohydrates_g": {"value": None, "unit": "g", "status": "missing", "confidence": None},
        "total_fat_g": {"value": None, "unit": "g", "status": "missing", "confidence": None},
        "dietary_fibre_g": {"value": None, "unit": "g", "status": "missing", "confidence": None},
    }

    # Matched DB record with different numbers
    matched_product = {
        "status": "exact_barcode_match",
        "match_type": "exact_barcode",
        "product_name": "Test Snack Bar",
        "source": "Open Food Facts (Verified)",
        "matched_data": {
            "nutrients": {
                "energy_kcal": 280.0,       # DB has 280, but label declared 250 -> MUST KEEP 250!
                "protein_g": 6.5,           # DB has 6.5, but label declared 5.0 -> MUST KEEP 5.0!
                "carbohydrates_g": 35.0,    # Label was missing -> ENRICH 35.0!
                "total_fat_g": 11.0,        # Label was missing -> ENRICH 11.0!
                "dietary_fibre_g": 4.2,     # Label was missing -> ENRICH 4.2!
            }
        }
    }

    fused, missing, conflicts = NutrientFusion.fuse_nutrients(
        ocr_nutrients=ocr_nutrients,
        matched_product=matched_product,
    )

    # 1. Declared values must NEVER be overwritten
    assert fused["energy_kcal"]["value"] == 250.0
    assert fused["energy_kcal"]["status"] == "declared"
    assert fused["energy_kcal"]["source"] == "printed_package_label"

    assert fused["protein_g"]["value"] == 5.0
    assert fused["protein_g"]["status"] == "declared"
    assert fused["protein_g"]["source"] == "printed_package_label"

    # 2. Missing fields must be enriched from DB with reference_derived status
    assert fused["carbohydrates_g"]["value"] == 35.0
    assert fused["carbohydrates_g"]["status"] == "reference_derived"
    assert fused["carbohydrates_g"]["source"] == "Open Food Facts (Verified)"

    assert fused["total_fat_g"]["value"] == 11.0
    assert fused["total_fat_g"]["status"] == "reference_derived"

    assert fused["dietary_fibre_g"]["value"] == 4.2
    assert fused["dietary_fibre_g"]["status"] == "reference_derived"


def test_scenario_20_conflicting_sources_recorded_predictably():
    """Scenario 20: Conflicting sources are retained, declared values kept, and discrepancies logged."""
    # Label declares sodium 400 mg, but database records 750 mg (>35% discrepancy)
    ocr_nutrients = {
        "sodium_mg": {"value": 400.0, "unit": "mg", "status": "declared", "confidence": 0.90},
        "protein_g": {"value": 10.0, "unit": "g", "status": "declared", "confidence": 0.90},
    }

    matched_product = {
        "status": "exact_barcode_match",
        "match_type": "exact_barcode",
        "product_name": "Salty Cracker",
        "source": "USDA Foundation Foods",
        "matched_data": {
            "nutrients": {
                "sodium_mg": 750.0,  # Conflict: 400 vs 750 (87.5% diff)
                "protein_g": 10.2,   # Normal small variation (2% diff, no conflict)
            }
        }
    }

    fused, missing, conflicts = NutrientFusion.fuse_nutrients(
        ocr_nutrients=ocr_nutrients,
        matched_product=matched_product,
    )

    # Declared value is preserved as authority
    assert fused["sodium_mg"]["value"] == 400.0
    assert fused["sodium_mg"]["status"] == "declared"

    # Discrepancy is recorded in conflict list
    assert len(conflicts) >= 1
    assert any("sodium_mg" in c and "declared on label=400.0 mg" in c and "750.0 mg" in c for c in conflicts)
    # Small variation is not flagged as a conflict
    assert not any("protein_g" in c for c in conflicts)


def test_scenario_21_incorrect_or_unrelated_matches_rejected():
    """Scenario 21: Incorrect, low-similarity, or unrelated product matches are rejected."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    matcher = ProductMatcher(repo_root=repo_root)

    # 1. Non-existent barcode returns unmatched / None
    res_barcode = matcher.match(barcode="9999999999994", allow_online=False)
    assert res_barcode["status"] == "unmatched"
    assert res_barcode["matched_data"] is None

    # 2. Completely unrelated/gibberish name without valid DB record
    res_name = matcher.match(product_name="XyZzzNonExistentSpaceFood990011")
    assert res_name["status"] == "unmatched" or res_name.get("confidence", 0) < 0.60
    assert res_name["matched_data"] is None

    # 3. Barcode with invalid checksum is rejected before matching
    res_invalid_bc = matcher.match(barcode="8901030000002")  # Invalid check digit
    assert res_invalid_bc["match_type"] == "invalid_barcode"
    assert res_invalid_bc["validation_error"] is not None
    assert res_invalid_bc["matched_data"] is None


def test_scenario_23_api_failures_timeouts_offline_mode_safe():
    """Scenario 23: API failures, timeouts, and offline mode are handled safely without crashing."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    matcher = ProductMatcher(repo_root=repo_root)

    # Mock urllib.request.urlopen to simulate network timeout
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection timed out")):
        res_timeout = matcher._lookup_barcode_online("3017620422003", timeout_sec=0.1)
        assert res_timeout is None  # Catches exception cleanly, returns None

    # Mock HTTP 500 server error
    with patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)):
        res_500 = matcher._lookup_barcode_online("3017620422003", timeout_sec=0.1)
        assert res_500 is None  # Catches exception cleanly, returns None

    # Full engine scan_barcode with allow_online=False (offline mode)
    engine = FoodIntelligenceEngine(repo_root=repo_root)
    # Valid barcode that is not in local SQLite DB
    res_offline = engine.scan_barcode("7622210449283", allow_online=False)
    assert res_offline["barcode_validation"]["is_valid"] is True
    # In offline mode, does not crash; falls back gracefully to scan_label_required
    assert res_offline["action_required"] == "scan_label_required"
    assert "back-of-package label" in res_offline["prompt_message"]


def test_scenario_24_cleanup_and_cli_entry_points():
    """Scenario 24: Imports, public APIs, and CLI entry points function reliably without breaking."""
    repo_root = Path(__file__).resolve().parent.parent.parent

    # 1. Clean imports of all core components
    from food_engine.engine import FoodIntelligenceEngine
    from food_engine.ocr.ocr_engine import OCREngine
    from food_engine.nutrition_extraction.extractor import NutritionExtractor
    from food_engine.nutrition_extraction.structured import extract_structured
    from food_engine.ingredient_parser.parser import IngredientParser
    from food_engine.product_matching.matcher import ProductMatcher
    from food_engine.product_matching.nutrient_fusion import NutrientFusion
    from food_engine.reporting.output_builder import OutputBuilder, format_text_report
    from food_engine.validation.barcode_validator import BarcodeValidator
    from food_engine.validation.completeness import CompletenessPolicy

    # Verify instantiation
    engine = FoodIntelligenceEngine(repo_root=repo_root)
    assert engine is not None

    # 2. CLI entry point: run_image_inference.py --help
    res_cli = subprocess.run(
        [sys.executable, str(repo_root / "scripts" / "run_image_inference.py"), "--help"],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert res_cli.returncode == 0
    assert "--barcode" in res_cli.stdout or "-b" in res_cli.stdout
    assert "--nutrition-image" in res_cli.stdout
    assert "--ingredients-image" in res_cli.stdout

    # 3. Formatted text report generation works with visual provenance badges
    sample_payload = {
        "product_identity": {"product_name": "Whole Wheat Biscuit", "brand": "SampleBrand", "barcode": "8901030000003"},
        "nutrition": {
            "basis": "per_100_g",
            "serving_size_g": 30.0,
            "nutrients": {
                "energy_kcal": {"value": 460.0, "unit": "kcal", "status": "declared", "source": "printed_package_label"},
                "protein_g": {"value": 7.5, "unit": "g", "status": "declared", "source": "printed_package_label"},
                "carbohydrates_g": {"value": 68.0, "unit": "g", "status": "reference_derived", "source": "Open Food Facts"},
                "sodium_mg": {"value": 380.0, "unit": "mg", "status": "calculated", "source": "calculated_stoichiometry"},
                "dietary_fibre_g": {"value": None, "unit": "g", "status": "missing"},
            }
        },
        "ingredients": {
            "parsed_ingredients": ["Wheat Flour", "Sugar", "Palm Oil"],
            "declared_allergens": ["Wheat"],
            "potential_traces": ["Milk / Dairy"],
        },
        "evidence_based_alerts": [
            {"title": "High Sugar Content", "severity": "warning", "explanation": "Contains >20g sugar per 100g."}
        ]
    }
    report_text = format_text_report(sample_payload)
    assert "[DECLARED]" in report_text
    assert "[EXACT_DB]" in report_text or "[REFERENCE_DB]" in report_text
    assert "[CALCULATED]" in report_text
    assert "[MISSING]" in report_text
    assert "High Sugar Content" in report_text
