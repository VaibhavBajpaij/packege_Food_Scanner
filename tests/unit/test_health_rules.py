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
