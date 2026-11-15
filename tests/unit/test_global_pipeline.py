"""Unit tests for Global Pipeline, Triage Logger, and Benchmark Validation."""

import json
import sys
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

from food_engine.validation.triage_logger import (
    calculate_blur_score,
    check_image_quality,
    log_triage_case,
    get_triage_summary
)
from scripts.run_global_pipeline_benchmark import is_match, verify_physical_sanity


def test_blur_score_sharp_vs_blurred():
    """Verify that sharp images pass quality gate while blurred images trigger Bucket A."""
    # Create sharp high-contrast black-white checkerboard
    sharp_arr = np.zeros((200, 200), dtype=np.uint8)
    sharp_arr[::10, :] = 255
    sharp_arr[:, ::10] = 255
    sharp_img = Image.fromarray(sharp_arr)

    score_sharp = calculate_blur_score(sharp_img)
    assert score_sharp > 100.0, f"Expected high score for checkerboard, got {score_sharp}"
    passed, _, _ = check_image_quality(sharp_img, threshold=80.0)
    assert passed is True

    # Create uniform / blurred image
    blurry_arr = np.ones((200, 200), dtype=np.uint8) * 128
    blurry_img = Image.fromarray(blurry_arr)
    score_blurry = calculate_blur_score(blurry_img)
    assert score_blurry < 10.0, f"Expected low score for uniform image, got {score_blurry}"
    passed_blurry, _, msg = check_image_quality(blurry_img, threshold=80.0)
    assert passed_blurry is False
    assert "blurry" in msg.lower()


def test_triage_logger_bucket_separation(tmp_path):
    """Verify that triage logger correctly routes to Bucket A vs Bucket B."""
    test_img = Image.new("RGB", (100, 100), color=(128, 128, 128))

    # Log blurry case -> Bucket A
    case_a = log_triage_case(
        test_img,
        failure_reason="IMAGE_TOO_BLURRY",
        details={"raw_ocr_lines": 0},
        sample_id="test_case_a"
    )
    assert case_a["suspected_bucket"] == "BUCKET_A_IMAGE_QUALITY"
    assert case_a["is_blurry"] is True

    # Log engine parser bug on sharp image -> Bucket B
    sharp_arr = np.zeros((200, 200, 3), dtype=np.uint8)
    sharp_arr[::5, :, :] = 255
    sharp_img = Image.fromarray(sharp_arr)
    case_b = log_triage_case(
        sharp_img,
        failure_reason="NO_NUTRITION_TABLE_FOUND",
        details={"raw_tokens": ["Ingredients:", "Sugar", "Flour"]},
        sample_id="test_case_b"
    )
    assert case_b["suspected_bucket"] == "BUCKET_B_ENGINE_PARSER_BUG"
    assert case_b["is_blurry"] is False


def test_physical_sanity_checks():
    """Verify Atwater formula, mass conservation, and parent-child nutrient rules."""
    # Physically impossible: Macronutrient sum = 50 + 40 + 30 = 120g per 100g!
    bad_macros = {
        "energy_kcal": 600.0,
        "protein_g": 50.0,
        "carbohydrates_g": 40.0,
        "fat_g": 30.0
    }
    passed, warnings = verify_physical_sanity(bad_macros)
    assert passed is False
    assert any("exceeds 100g" in w for w in warnings)

    # Physically impossible: Sugars > Total Carbohydrates
    bad_sugars = {
        "energy_kcal": 400.0,
        "protein_g": 10.0,
        "carbohydrates_g": 20.0,
        "sugars_g": 35.0,
        "fat_g": 10.0
    }
    passed_s, warnings_s = verify_physical_sanity(bad_sugars)
    assert passed_s is False
    assert any("Sugars" in w and "exceeds" in w for w in warnings_s)

    # Valid profile: 7g protein, 68g carbs, 18g fat -> kcal = 4*7 + 4*68 + 9*18 = 28 + 272 + 162 = 462 kcal
    good_nutrients = {
        "energy_kcal": 460.0,
        "protein_g": 7.0,
        "carbohydrates_g": 68.0,
        "sugars_g": 24.0,
        "fat_g": 18.0,
        "saturated_fat_g": 8.0
    }
    passed_g, warnings_g = verify_physical_sanity(good_nutrients)
    assert passed_g is True
    assert len(warnings_g) == 0


def test_is_match_tolerance():
    """Verify standard AOAC/regulatory tolerance evaluation."""
    # Absolute tolerance: 0.4g diff is <= 0.5g
    assert is_match(5.4, 5.0) is True
    # Percentage tolerance: within 5%
    assert is_match(465.0, 460.0) is True
    # Mismatch: 500 kcal vs 400 kcal
    assert is_match(500.0, 400.0) is False
    # None handling
    assert is_match(None, 10.0) is False
    assert is_match(10.0, None) is False


def test_global_dataset_manifest_integrity():
    """Verify that global dataset manifest exists and has valid multi-country entries."""
    manifest_path = REPO_ROOT / "datasets" / "evaluation" / "global_packaged_food" / "global_ground_truth.json"
    assert manifest_path.exists(), "Global dataset manifest must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["total_samples"] >= 15, "Expected at least 15 global products"
    assert len(data["countries_covered"]) >= 5, "Expected coverage of at least 5 countries"
    assert "North America" in data["regions_covered"]
    assert "Europe" in data["regions_covered"]
    assert "Asia-Pacific" in data["regions_covered"]

    # Verify each sample has required fields and existing image file
    for s in data["samples"]:
        assert s["barcode"], f"Sample {s['sample_id']} missing barcode"
        assert s["product_name"], f"Sample {s['sample_id']} missing product_name"
        assert s["country"], f"Sample {s['sample_id']} missing country"
        assert "ground_truth_nutrients_100g" in s
        img_p = REPO_ROOT / s["local_image_path"]
        assert img_p.exists(), f"Image file {img_p} must exist on disk"
