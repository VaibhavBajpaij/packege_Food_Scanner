"""Unit tests for Stage 3: Product Matching and Database Lookups."""

from pathlib import Path
from food_engine.product_matching.matcher import ProductMatcher


def test_product_matcher_initialization():
    matcher = ProductMatcher()
    assert matcher.products_db_path.exists()
    assert matcher.reference_db_path.exists()


def test_exact_barcode_lookup():
    matcher = ProductMatcher()
    # Test looking up known Open Food Facts item
    res = matcher.match(barcode="0000101209159")
    assert res["status"] == "exact_barcode_match"
    assert res["barcode"] == "0000101209159"
    assert "Open Food Facts" in res["source"]


def test_reference_food_lookup_indian_staple():
    matcher = ProductMatcher()
    res = matcher.match(product_name="Rice, Raw, Milled")
    assert res["status"] == "fuzzy_name_match"
    assert "Indian Food Composition" in res["source"]
    assert res["matched_data"]["id"] == "A001"
    assert res["matched_data"]["nutrients"]["energy_kcal"] == 356.0


def test_reference_food_lookup_usda():
    matcher = ProductMatcher()
    res = matcher._lookup_reference_foods("Hummus")
    assert res is not None
    assert "USDA" in res["source"]
    assert "HUMMUS" in res["name"].upper()


def test_unmatched_ocr_fallback():
    matcher = ProductMatcher()
    res = matcher.match(ocr_lines=["Random Nonexistent Brand X99", "Net Wt: 50g"])
    assert res["status"] == "ocr_inferred"
    assert res["product_name"] == "Random Nonexistent Brand X99"


def test_preset_6_exact_barcode_match():
    matcher = ProductMatcher()
    res = matcher.match(barcode="8901030000003")
    assert res["status"] == "exact_barcode_match"
    assert res["barcode"] == "8901030000003"
    assert "Premium Whole Wheat Crunch Biscuits" in res["product_name"]


def test_online_lookup_user_agent_and_timeout():
    import urllib.request
    matcher = ProductMatcher()

    captured_headers = {}
    def mock_urlopen(req, timeout=None):
        nonlocal captured_headers
        captured_headers = req.headers
        raise TimeoutError("Simulated socket timeout")

    orig_urlopen = urllib.request.urlopen
    urllib.request.urlopen = mock_urlopen
    try:
        data, err = matcher._lookup_barcode_online("9999999999994", timeout_sec=5.0)
        assert data is None
        assert err == "API_UNAVAILABLE"
        ua = captured_headers.get("User-agent") or captured_headers.get("User-Agent")
        assert "PackagedFoodScanner" in ua
        assert "engineering@example.com" in ua
    finally:
        urllib.request.urlopen = orig_urlopen

