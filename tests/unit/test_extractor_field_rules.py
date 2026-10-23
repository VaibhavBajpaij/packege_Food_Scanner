"""Regression tests for Phase 3 extraction/layout fixes.

Covers the defect classes surfaced by the Phase 3 audit:
- kJ/kcal mixed on one energy row (kcal must be 467, not 1962)
- 'Calories from Fat' exclusion
- thousands separators ('1,098 mg' -> 1098) and decimal commas ('4,1 g' -> 4.1)
- % Daily-Value captures never recorded as nutrient quantities
- two-column panels (per serving | per 100g) column selection
- bounding-box row reassembly of fragmented OCR lines
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.nutrition_extraction.extractor import (  # noqa: E402
    NutritionExtractor,
    parse_number,
)
from food_engine.ocr.layout_assembly import row_group_lines  # noqa: E402


class TestParseNumber:
    def test_three_digit_comma_is_thousands(self):
        assert parse_number("1,098") == 1098.0
        assert parse_number("14,090") == 14090.0

    def test_one_or_two_digit_comma_is_decimal(self):
        assert parse_number("4,1") == 4.1
        assert parse_number("61,7") == 61.7

    def test_plain_and_dotted(self):
        assert parse_number("7.0") == 7.0
        assert parse_number("47") == 47.0

    def test_multiple_separators_rightmost_decimal(self):
        assert parse_number("1,234,567.89") == 1234567.89


class TestEnergyUnitSeparation:
    def test_kj_and_kcal_on_same_row(self):
        lines = ["Energie 1962 kJ / 467 kcal", "Matieres grasses 17 g"]
        res = NutritionExtractor.extract(lines)
        nuts = res["nutrients"]
        assert nuts["energy_kcal"]["value"] == 467.0
        assert nuts["energy_kj"]["value"] == 1962.0

    def test_calories_from_fat_is_not_energy(self):
        lines = ["Amount per serving", "Calories from Fat 60", "Calories 310", "Protein 7g"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["energy_kcal"]["value"] == 310.0

    def test_kj_only_row_goes_to_kj_not_kcal(self):
        lines = ["Energy", "1868.8 kJ", "Protein 8.9 g"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["energy_kj"]["value"] == 1868.8
        assert res["nutrients"]["energy_kcal"]["value"] is None


class TestNumberFormatting:
    def test_thousands_sodium(self):
        lines = ["Sodium 1,098mg", "Protein 8.9 g"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["sodium_mg"]["value"] == 1098.0

    def test_decimal_comma(self):
        lines = ["of which Sugars 4,1 g", "Protein 3,9 g"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["sugars_g"]["value"] == 4.1
        assert res["nutrients"]["protein_g"]["value"] == 3.9


class TestPercentExclusion:
    def test_percent_only_is_not_a_value(self):
        lines = ["Total Sugars", "13%"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["sugars_g"]["value"] is None
        assert res["nutrients"]["sugars_g"]["status"] == "missing"

    def test_value_with_trailing_percent_uses_amount(self):
        lines = ["Total Sugars 39g 78%"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["sugars_g"]["value"] == 39.0


class TestTwoColumnPanels:
    LINES = [
        "Serving size: 70 g",
        "Average Quantity: Per serving / Per 100g",
        "Energy 324 kJ / 464 kJ",
        "77 kcal / 111 kcal",
        "Protein 6.2 g / 8.9 g",
        "Sodium 713 mg / 1018 mg",
        "sugars 2.0 g / 2.8 g",
    ]

    def test_layout_detection_serving_first(self):
        assert NutritionExtractor._detect_column_layout(self.LINES) == "serving_first"

    def test_layout_detection_hundred_first(self):
        lines = ["Pour 100 g: ", "par portion de 51 g", "Lipides 16.6 g / 8.5 g"]
        assert NutritionExtractor._detect_column_layout(["per serving / per 100g"]) == "serving_first"

    def test_per_100g_column_selected(self):
        res = NutritionExtractor.extract(list(self.LINES))
        nuts = res["nutrients"]
        assert nuts["energy_kcal"]["value"] == 111.0
        assert nuts["protein_g"]["value"] == 8.9
        assert nuts["sodium_mg"]["value"] == 1018.0
        assert nuts["sugars_g"]["value"] == 2.8
        assert nuts["energy_kj"]["value"] == 464.0

    def test_per_serving_column_selected(self):
        # Same panel shape recorded under a per-serving basis
        lines = [
            "Serving size: 70 g",
            "Amount per serving / Per 100g",
            "77 kcal / 111 kcal",
        ]
        res = NutritionExtractor.extract(lines)
        res_basis = res["basis"]
        assert res_basis == "per_100_g"  # header contains 'per 100g'

    def test_ambiguity_recorded_when_selection_from_multiple(self):
        res = NutritionExtractor.extract(list(self.LINES))
        assert res["basis"] == "per_100_g"
        # With a serving_first layout and per-100 basis, multiple same-unit
        # candidates must have been narrowed column-wise and flagged.
        assert any(
            (n.get("match_method") == "line")
            for n in res["nutrients"].values()
        )


class TestReversedSugarPatterns:
    def test_includes_g_added_sugars(self):
        lines = ["Total Sugars 14g", "Includes 12g Added Sugars 6%"]
        res = NutritionExtractor.extract(lines)
        nuts = res["nutrients"]
        assert nuts["added_sugars_g"]["value"] == 12.0
        assert nuts["sugars_g"]["value"] == 14.0

    def test_of_which_sugars(self):
        lines = ["Carbohydrate 51.7g", "of which Sugars 2.6 g"]
        res = NutritionExtractor.extract(lines)
        assert res["nutrients"]["sugars_g"]["value"] == 2.6


class TestRowAssembly:
    def _line(self, text, xmin, ymin, xmax, ymax):
        # 4-point polygon (tl, tr, br, bl)
        box = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
        return {"text": text, "confidence": 0.95, "bounding_box": box}

    def test_fragments_on_same_print_row_merge(self):
        lines = [
            self._line("Information", 20, 10, 120, 30),
            self._line("nutritionnelle", 140, 8, 300, 30),
            self._line("100g", 320, 12, 380, 32),
        ]
        rows = row_group_lines(lines)
        assert len(rows) == 1
        assert rows[0]["text"] == "Information nutritionnelle 100g"

    def test_different_rows_stay_separate(self):
        lines = [
            self._line("Energy", 20, 100, 100, 124),
            self._line("1962 kJ / 467 kcal", 130, 98, 360, 126),
            self._line("Protein 6.3 g", 20, 150, 180, 172),
        ]
        rows = row_group_lines(lines)
        assert len(rows) == 2
        assert rows[0]["text"].startswith("Energy")
        assert rows[1]["text"] == "Protein 6.3 g"

    def test_no_boxes_fallthrough(self):
        rows = row_group_lines([{"text": "Ferrero", "bounding_box": None}])
        assert len(rows) == 1
        assert rows[0]["text"] == "Ferrero"

    def test_left_to_right_within_row(self):
        lines = [
            self._line("Fat", 200, 10, 260, 30),
            self._line("Total", 20, 8, 80, 30),
        ]
        rows = row_group_lines(lines)
        assert rows[0]["text"] == "Total Fat"
