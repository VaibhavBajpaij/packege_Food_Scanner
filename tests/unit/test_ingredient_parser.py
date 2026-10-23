"""Unit tests for Stage 4: Ingredient and Declared Allergen Extraction."""

from food_engine.ingredient_parser.parser import IngredientParser


def test_ingredient_splitting_nested_parentheses():
    text = (
        "INGREDIENTS: Whole Wheat Flour (62%), Vegetable Oil (Palm Oil, Antioxidant (E319)), "
        "Sugar, Milk Solids, Salt."
    )
    res = IngredientParser.parse_from_text(text)
    items = res["parsed_ingredients"]
    assert len(items) == 5
    assert "Whole Wheat Flour (62%)" in items
    assert "Vegetable Oil (Palm Oil, Antioxidant (E319))" in items
    assert "Sugar" in items
    assert "Milk Solids" in items


def test_declared_allergens_extraction():
    text = (
        "INGREDIENTS: Wheat Flour, Sugar, Butter, Soy Lecithin.\n"
        "ALLERGEN INFORMATION: CONTAINS WHEAT (GLUTEN), MILK, AND SOY.\n"
        "MAY CONTAIN TRACES OF PEANUTS."
    )
    res = IngredientParser.parse_from_text(text)
    declared = res["declared_allergens"]
    traces = res["potential_traces"]

    assert "Wheat" in declared
    assert "Milk / Dairy" in declared
    assert "Soybeans / Soy" in declared
    assert "Peanuts" in traces
    assert res["review_required"] is True


def test_no_declared_allergens_never_assumed_allergen_free():
    text = "INGREDIENTS: Oats, Honey, Dried Berries."
    res = IngredientParser.parse_from_text(text)
    assert len(res["declared_allergens"]) == 0
    # Rule check: review_required must stay True to prevent false assumptions of allergen safety
    assert res["review_required"] is True
