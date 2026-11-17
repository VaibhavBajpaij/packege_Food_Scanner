"""Unit tests for Stage 8: Evidence-Based Health Rules."""

from food_engine.reporting.health_rules import EvidenceBasedHealthRules


def test_high_sugar_and_sodium_alerts():
    nutrients = {
        "sugars_g": {"value": 25.0, "unit": "g", "status": "declared"},
        "sodium_mg": {"value": 750.0, "unit": "mg", "status": "declared"},
        "saturated_fat_g": {"value": 6.5, "unit": "g", "status": "declared"},
        "trans_fat_g": {"value": 0.4, "unit": "g", "status": "declared"},
    }
    declared_allergens = ["Peanuts", "Milk / Dairy"]
    traces = ["Soybeans / Soy"]

    alerts = EvidenceBasedHealthRules.evaluate(
        nutrients=nutrients,
        declared_allergens=declared_allergens,
        potential_traces=traces,
        basis="per_100_g"
    )

    alert_titles = [a["title"] for a in alerts]
    assert "High Sugar Content" in alert_titles
    assert "High Sodium Content" in alert_titles
    assert "High Saturated Fat Content" in alert_titles
    assert "Declared Trans Fatty Acids" in alert_titles
    assert "Declared Allergen: Peanuts" in alert_titles
    assert "Declared Allergen: Milk / Dairy" in alert_titles
    assert "Potential Allergen Trace: Soybeans / Soy" in alert_titles

    # Verify every alert has an authoritative source and no disease claim
    for a in alerts:
        assert len(a["authority_source"]) > 5
        assert len(a["reason"]) > 10
        assert "cure" not in a["reason"].lower()
        assert "diagnos" not in a["reason"].lower()


def test_zero_ocr_lines_yields_inconclusive_compliance():
    """Verify that 0 detected OCR lines returns INCONCLUSIVE and never false-positive COMPLIANT."""
    res = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients={},
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
        ocr_lines_detected=0,
    )
    assert res["status"] == "INCONCLUSIVE"
    assert res["is_sufficient"] is False
    assert "Inconclusive / Insufficient Data" in res["diagnosis_message"]
    assert any(a.get("title") == "Inconclusive / Insufficient Data" for a in res["alerts"])


def test_missing_core_nutrients_yields_inconclusive():
    """Verify missing core macronutrients return INCONCLUSIVE compliance."""
    # Only protein and carbs declared; energy, sugars, fat, and sodium missing
    partial_nuts = {
        "protein_g": {"value": 5.0, "unit": "g", "status": "declared"},
        "carbohydrates_g": {"value": 20.0, "unit": "g", "status": "declared"},
    }
    res = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients=partial_nuts,
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
        ocr_lines_detected=5,
    )
    assert res["status"] == "INCONCLUSIVE"
    assert res["is_sufficient"] is False
    assert "Inconclusive / Insufficient Data" in res["diagnosis_message"]


def test_complete_core_nutrients_low_values_yields_compliant():
    """Verify complete core nutrients within thresholds yield COMPLIANT."""
    healthy_nuts = {
        "energy_kcal": {"value": 85.0, "unit": "kcal", "status": "declared"},
        "sugars_g": {"value": 2.0, "unit": "g", "status": "declared"},
        "saturated_fat_g": {"value": 0.5, "unit": "g", "status": "declared"},
        "sodium_mg": {"value": 120.0, "unit": "mg", "status": "declared"},
    }
    res = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients=healthy_nuts,
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
        ocr_lines_detected=10,
    )
    assert res["status"] == "COMPLIANT"
    assert res["is_sufficient"] is True
    assert "FSSAI & WHO Dietary Compliant" in res["diagnosis_message"]


def test_insufficient_data_guard_contract():
    """Verify exact contract for insufficient nutrients guard (<2 core nutrients present)."""
    # 1. Empty nutrients
    res_empty = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients={},
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
    )
    assert res_empty["status"] == "INCONCLUSIVE"
    assert res_empty["badge"] == "AMBER"
    assert "Insufficient Nutritional Data" in res_empty["title"]
    assert "Key macronutrients" in res_empty["message"]
    assert res_empty["flags"] == []

    # 2. Only 1 core nutrient present (less than 2)
    single_nut = {
        "sugars": {"value": 5.0, "status": "declared"}
    }
    res_single = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients=single_nut,
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
    )
    assert res_single["status"] == "INCONCLUSIVE"
    assert res_single["badge"] == "AMBER"
    assert res_single["flags"] == []

    # 3. Nutrients with MISSING status
    missing_nuts = {
        "sugars": {"value": None, "status": "MISSING"},
        "saturated_fat": {"value": None, "status": "MISSING"},
        "sodium": {"value": None, "status": "MISSING"},
        "energy": {"value": None, "status": "MISSING"},
    }
    res_missing = EvidenceBasedHealthRules.evaluate_compliance(
        nutrients=missing_nuts,
        declared_allergens=[],
        potential_traces=[],
        basis="per_100_g",
    )
    assert res_missing["status"] == "INCONCLUSIVE"
    assert res_missing["badge"] == "AMBER"
    assert res_missing["flags"] == []


