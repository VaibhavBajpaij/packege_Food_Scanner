"""Regression tests for the bbox-aware structured nutrition extractor."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.nutrition_extraction.structured import extract_structured  # noqa: E402


def line(text, xmin, ymin, xmax, ymax, confidence=0.95):
    box = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
    return {"text": text, "confidence": confidence, "bounding_box": box}


class TestProseExclusion:
    def test_ingredient_words_do_not_steal_nutrient_rows(self):
        res = extract_structured([
            line("premium biscuits", 0, 0, 400, 20),
            line("ingredients: sugar, salt (ins 500)", 0, 30, 400, 50),
            line("nutrition facts", 0, 80, 200, 100),
            line("values per 100g", 0, 110, 140, 130),
            line("total sugars 24.5 g", 0, 140, 300, 160),
            line("salt 0.95 g", 0, 180, 300, 200),
        ])
        nuts = res["nutrients"]
        assert nuts["sugars_g"]["value"] == 24.5
        assert nuts["salt_g"]["value"] == 0.95


class TestSideBySideColumns:
    def test_values_in_both_nutrient_columns_are_matched(self):
        res = extract_structured([
            line("per serving", 150, 0, 240, 20),
            line("per serving", 450, 0, 543, 20),
            line("total fat 16g", 85, 30, 204, 55),
            line("total carb. 8g", 379, 32, 532, 57),
            line("total sugars 3g", 393, 60, 537, 85),
            line("protein 7g", 385, 90, 500, 115),
        ])
        nuts = res["nutrients"]
        assert nuts["total_fat_g"]["value"] == 16.0
        assert nuts["carbohydrates_g"]["value"] == 8.0
        assert nuts["sugars_g"]["value"] == 3.0
        assert nuts["protein_g"]["value"] == 7.0


class TestSidebarExclusion:
    def test_right_hand_marketing_claim_is_not_a_table_value(self):
        res = extract_structured([
            line("per serving", 284, 0, 535, 20),
            line("total fat 2g", 289, 30, 374, 55),
            line("sodium 130mg", 300, 60, 403, 85),
            line("total carbohydrate 14g", 302, 90, 462, 115),
            line("*silk vanilla: 470mg calcium per cup", 571, 88, 828, 113),
        ])
        nuts = res["nutrients"]
        assert nuts["sodium_mg"]["value"] == 130.0
        assert nuts["carbohydrates_g"]["value"] == 14.0
        assert nuts["calcium_mg"]["value"] is None


class TestEnergyWithoutLabel:
    def test_unit_bearing_kcal_in_declared_column_is_energy(self):
        res = extract_structured([
            line("per 100g", 500, 0, 600, 20),
            line("449kcal", 510, 30, 590, 55),
            line("fat 16.6g", 40, 30, 300, 55),
        ])
        nuts = res["nutrients"]
        assert nuts["energy_kcal"]["value"] == 449.0
        assert nuts["total_fat_g"]["value"] == 16.6
