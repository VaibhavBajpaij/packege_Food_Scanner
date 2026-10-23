"""Unit tests for JSON schema validation and dataset/model manifests."""

import json
from pathlib import Path
import jsonschema
import yaml
from food_engine.reporting.output_builder import OutputBuilder


def test_schema_file_validity():
    repo_root = Path(__file__).resolve().parent.parent.parent
    schema_path = repo_root / "config" / "nutrient_schema.yaml"
    assert schema_path.exists()
    schema = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    assert schema["type"] == "object"
    assert "required" in schema


def test_output_builder_validation():
    ob = OutputBuilder()
    payload = ob.build_payload(
        input_image="test.jpg",
        image_metadata={"width": 400, "height": 300, "format": "JPEG"},
        ocr_result={"engine": "test", "model_version": "v1", "execution_time_sec": 0.01, "line_count": 0, "lines": []},
        product_match={"status": "unmatched", "match_type": "none", "product_name": None, "barcode": None, "brand": None, "source": "none"},
        ingredients={"original_text": None, "parsed_ingredients": [], "declared_allergens": [], "review_required": True},
        nutrition={"basis": "per_100_g", "nutrients": {}},
        calculated_package_totals={"package_weight_g": None, "calculated_nutrients": {}},
        evidence_based_alerts=[],
        missing_fields=[],
        conflicting_fields=[],
        source_verified=False
    )
    assert payload["engine_version"] == "0.1.0"


def test_manifest_files_exist_and_valid():
    repo_root = Path(__file__).resolve().parent.parent.parent
    model_manifest = repo_root / "models" / "model_manifest.json"
    download_manifest = repo_root / "datasets" / "manifests" / "download_manifest.json"

    assert model_manifest.exists()
    assert download_manifest.exists()

    mm = json.loads(model_manifest.read_text(encoding="utf-8"))
    assert "models" in mm
    assert "ppocr_v4_en_rec" in mm["models"]

    dm = json.loads(download_manifest.read_text(encoding="utf-8"))
    assert "downloads" in dm
    assert len(dm["downloads"]) >= 5
