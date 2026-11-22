import pytest
from food_engine.deception_detector import DeceptiveLabelBuster


@pytest.fixture
def buster():
    return DeceptiveLabelBuster()


def test_bournvita_sugar_aliases_and_disguise(buster):
    """Bournvita scandal test: Contains sugar, maltodextrin, liquid glucose, and invert sugar."""
    ingredients = "Malt extract (44%), Sugar, Cocoa solids, Milk solids, Liquid glucose, Maltodextrin, Invert sugar syrup, Emulsifiers (INS 322, INS 471), Minerals, Vitamins."
    nutrients = {
        "energy_kcal": 380.0,
        "sugars_100g": 32.2,
        "saturated_fat_100g": 1.8,
        "sodium_mg": 180.0,
        "protein_g": 7.0,
        "fiber_g": 3.0,
    }
    res = buster.analyze_label(
        product_name="Cadbury Bournvita",
        ingredients_text=ingredients,
        nutrients=nutrients,
        serving_size_g=20.0,
        pack_weight_g=500.0,
        brand="Cadbury",
        category="Health Drink Powder",
    )

    sugar_analysis = res["sugar_analysis"]
    assert sugar_analysis["is_disguised"] is True
    # Should detect at least: sugar, maltodextrin, liquid glucose, invert sugar syrup, malt extract
    aliases = [a["alias"].lower() for a in sugar_analysis["aliases"]]
    assert any("maltodextrin" in a for a in aliases)
    assert any("liquid glucose" in a for a in aliases)
    assert any("malt extract" in a for a in aliases)
    assert res["deception_score"] >= 40
    assert res["nova_classification"]["nova_group"] == 4


def test_parle_g_palm_oil_buster(buster):
    """Parle-G biscuit test: Uses Edible Vegetable Oil (Palmolein) and Invert Sugar Syrup."""
    ingredients = "Wheat Flour (65%), Sugar, Edible Vegetable Oil (Palmolein), Invert Sugar Syrup, Leavening Agents (INS 503ii, INS 500ii), Salt, Milk Solids, Emulsifier (INS 322)."
    nutrients = {
        "energy_kcal": 454.0,
        "sugars_100g": 26.5,
        "saturated_fat_100g": 6.5,
        "sodium_mg": 280.0,
        "protein_g": 6.5,
    }
    res = buster.analyze_label(
        product_name="Parle-G Gluco Biscuits",
        ingredients_text=ingredients,
        nutrients=nutrients,
        serving_size_g=25.0,
        pack_weight_g=100.0,
        brand="Parle",
        category="Biscuits",
    )

    palm_oil = res["palm_oil_analysis"]
    assert palm_oil["contains_palm_oil"] is True
    assert palm_oil["is_disguised_under_vegetable_oil"] is True
    assert "DECEPTIVE LABEL DETECTED" in palm_oil["warning"]
    assert res["fssai_inr"]["stars"] <= 3.0


def test_clean_food_unprocessed(buster):
    """Pure cow milk or raw whole wheat: Should be NOVA 1, 0 deception, 5.0 stars."""
    ingredients = "Pasteurised standardized cow milk."
    nutrients = {
        "energy_kcal": 62.0,
        "sugars_100g": 4.7,  # natural lactose
        "saturated_fat_100g": 2.2,
        "sodium_mg": 45.0,
        "protein_g": 3.2,
    }
    res = buster.analyze_label(
        product_name="Amul Pure Cow Milk",
        ingredients_text=ingredients,
        nutrients=nutrients,
        serving_size_g=200.0,
        pack_weight_g=200.0,
        brand="Amul",
        category="Dairy",
    )

    assert res["deception_score"] == 0
    assert res["palm_oil_analysis"]["contains_palm_oil"] is False
    assert res["nova_classification"]["nova_group"] == 1
    assert res["fssai_inr"]["stars"] >= 4.5


def test_serving_size_deception_calculation(buster):
    """Test manufacturer serving trick: 15g serving on a 150g pack of chips."""
    nutrients = {
        "sugars_100g": 20.0,
        "saturated_fat_100g": 10.0,
        "energy_kcal": 500.0,
    }
    reality = buster._calculate_serving_deception(
        nutrients=nutrients,
        serving_size_g=15.0,
        pack_weight_g=150.0,
    )
    assert reality["servings_per_pack"] == 10.0
    assert reality["per_serving_sugar_g"] == 3.0
    assert reality["full_pack_sugar_g"] == 30.0
    assert reality["is_serving_size_deceptive"] is True
    assert reality["who_daily_sugar_pct"] == 120.0  # 30g / 25g = 120%
