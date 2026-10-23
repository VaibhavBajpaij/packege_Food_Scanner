"""Unit tests for Stage 7: Deterministic Nutrition Calculations."""

from food_engine.nutrition_calculation.calculator import NutritionCalculator


def test_package_totals_scaling():
    nutrients_per_100 = {
        "energy_kcal": {"value": 400.0, "unit": "kcal", "status": "declared"},
        "protein_g": {"value": 10.0, "unit": "g", "status": "declared"},
        "sugars_g": {"value": 20.0, "unit": "g", "status": "declared"},
        "vitamin_c_mg": {"value": None, "unit": "mg", "status": "missing"},
    }

    # Net weight: 150g (factor 1.5)
    res = NutritionCalculator.calculate_package_totals(
        nutrients_per_100=nutrients_per_100,
        package_weight_g=150.0,
        basis="per_100_g"
    )

    scaled = res["calculated_nutrients"]
    assert scaled["energy_kcal"]["value"] == 600.0
    assert scaled["protein_g"]["value"] == 15.0
    assert scaled["sugars_g"]["value"] == 30.0
    assert scaled["vitamin_c_mg"]["status"] == "missing"
    assert "weight_scaling" in res["calculation_method"]


def test_liquid_density_volume_scaling():
    nutrients_per_100 = {
        "energy_kcal": {"value": 50.0, "unit": "kcal", "status": "declared"},
    }
    # 200g of liquid with density 1.05 g/ml -> volume = 200 / 1.05 = 190.48 ml -> factor = 1.905
    res = NutritionCalculator.calculate_package_totals(
        nutrients_per_100=nutrients_per_100,
        package_weight_g=200.0,
        liquid_density_g_per_ml=1.05,
        basis="per_100_ml"
    )
    scaled = res["calculated_nutrients"]
    expected = round(50.0 * (200.0 / 1.05) / 100.0, 2)
    assert scaled["energy_kcal"]["value"] == expected


def test_sodium_and_salt_conversions():
    # 800 mg sodium -> 2.0 g salt
    sod, salt = NutritionCalculator.convert_sodium_and_salt(sodium_mg=800.0)
    assert sod == 800.0
    assert salt == 2.0

    # 1.5 g salt -> 600 mg sodium
    sod, salt = NutritionCalculator.convert_sodium_and_salt(salt_g=1.5)
    assert sod == 600.0
    assert salt == 1.5


def test_energy_conversions():
    # 100 kcal -> 418.4 kJ
    kcal, kj = NutritionCalculator.convert_energy(kcal=100.0)
    assert kcal == 100.0
    assert kj == 418.4
