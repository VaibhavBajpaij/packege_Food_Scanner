import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add repo root and api directory to path
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "api"))

from api.server import app

client = TestClient(app)


def test_api_health():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "UP"
    assert "NutriTruth" in data["service"]
    assert data["database"]["connected"] is True
    assert data["database"]["offline_products_count"] > 10000
    assert "Live Camera Barcode Scanner" in data["modules"][0]


def test_api_demo_bournvita():
    res = client.get("/api/v1/demo/bournvita")
    assert res.status_code == 200
    data = res.json()
    assert data["product_name"] == "Cadbury Bournvita"
    assert data["sugar_analysis"]["is_disguised"] is True
    assert data["deception_score"] >= 40
    assert data["nova_classification"]["nova_group"] == 4


def test_api_demo_parle_g():
    res = client.get("/api/v1/demo/parle-g")
    assert res.status_code == 200
    data = res.json()
    assert data["palm_oil_analysis"]["contains_palm_oil"] is True
    assert data["palm_oil_analysis"]["is_disguised_under_vegetable_oil"] is True


def test_api_custom_analyze():
    payload = {
        "product_name": "Test Instant Soup",
        "brand": "QuickSoup",
        "category": "Soup",
        "ingredients_text": "Maltodextrin, Salt, Edible Vegetable Fat (Palmolein), Monosodium Glutamate (INS 621), Caramel IV (INS 150d).",
        "nutrients": {
            "sugars_100g": 18.0,
            "saturated_fat_100g": 8.0,
            "sodium_mg": 1400.0,
        },
        "serving_size_g": 15.0,
        "pack_weight_g": 60.0,
    }
    res = client.post("/api/v1/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["deception_score"] >= 50
    assert data["sugar_analysis"]["is_disguised"] is True
    assert data["palm_oil_analysis"]["contains_palm_oil"] is True


def test_api_image_barcode_scan():
    """Tests the server-side image scanning on real sample image with barcode."""
    sample_img = repo_root / "datasets" / "triage" / "images" / "global_15.jpg"
    if sample_img.exists():
        with open(sample_img, "rb") as f:
            res = client.post("/api/v1/scan/image", files={"file": ("global_15.jpg", f, "image/jpeg")})
            assert res.status_code == 200
            data = res.json()
            assert "scan_result" in data
            assert data["scan_result"]["barcode"] == "8901058017687"
            assert "maggi" in data["product_name"].lower()


def test_api_index_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "NutriTruth" in res.text
    assert "html5-qrcode" in res.text
    assert "Camera Active" in res.text or "Live Camera Barcode Scanner" in res.text
