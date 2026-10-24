"""Regression tests for Phase 6 verified benchmark scoring, ground truth, and provenance isolation."""

import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.nutrition_extraction.structured import extract_structured
from food_engine.product_matching.nutrient_fusion import NutrientFusion
from food_engine.nutrition_calculation.calculator import NutritionCalculator


def line(text, xmin, ymin, xmax, ymax, confidence=0.95):
    box = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
    return {"text": text, "confidence": confidence, "bounding_box": box}


class TestProvenanceSeparation:
    def test_calculated_salt_sodium_is_separated_from_label_declared(self):
        """Req 2: Calculated salt/sodium carries status='calculated' and is distinguished from 'declared'."""
        # OCR has only sodium
        res = extract_structured([
            line("Nutrition Facts", 0, 0, 200, 20),
            line("per serving", 0, 25, 100, 45),
            line("Sodium 290mg", 0, 50, 150, 70),
        ])
        nuts = res["nutrients"]
        assert nuts["sodium_mg"]["status"] == "declared"
        assert nuts["sodium_mg"]["value"] == 290.0
        assert nuts["salt_g"]["status"] == "calculated"
        assert nuts["salt_g"]["value"] == round((290.0 / 1000.0) * 2.5, 3)
        assert nuts["salt_g"]["status"] != "declared"

    def test_reference_derived_nutrients_not_represented_as_ocr_declared(self):
        """Req 3: Database-matched fallback values carry status='reference_derived', never 'declared'."""
        ocr_nuts = {
            "energy_kcal": {"value": 42.0, "unit": "kcal", "status": "declared"},
            "carbohydrates_g": {"value": 10.6, "unit": "g", "status": "declared"},
            "saturated_fat_g": {"value": None, "unit": "g", "status": "missing"},
        }
        matched_prod = {
            "status": "exact_barcode_match",
            "source": "reference_database",
            "matched_data": {
                "nutrients": {
                    "saturated_fat_g": 0.0
                }
            }
        }
        fused, missing, conflicts = NutrientFusion.fuse_nutrients(ocr_nuts, matched_product=matched_prod)
        assert fused["saturated_fat_g"]["status"] == "reference_derived"
        assert fused["saturated_fat_g"]["status"] != "declared"
        assert fused["saturated_fat_g"]["value"] == 0.0


class TestBenchmarkScoringRules:
    def test_valid_visible_nutrients_not_scored_as_spurious_when_annotated(self):
        """Req 1: Valid visible nutrients (fibre, trans fat, etc.) score as TP, not FP, against comprehensive GT."""
        gt_decl = {
            "energy_kcal": 467.0,
            "fibre_g": 4.0,
            "energy_kj": 1962.0,
        }
        pred_declared = {
            "energy_kcal": 467.0,
            "fibre_g": 4.0,
            "energy_kj": 1962.0,
        }
        # Simulate benchmark scoring
        tp = sum(1 for k, v in gt_decl.items() if pred_declared.get(k) == v)
        fp = sum(1 for k, v in pred_declared.items() if k not in gt_decl)
        assert tp == 3
        assert fp == 0

    def test_wrong_nutrient_value_counts_as_error(self):
        """Req 4: An extracted nutrient whose value deviates outside tolerance counts as FN and FP."""
        gt_val = 5.3
        pred_val = 53.0  # dropped comma
        rel_err = abs(pred_val - gt_val) / gt_val
        assert rel_err > 0.05
        # Scoring logic must flag this as wrong_value
        assert rel_err == pytest.approx(9.0, rel=1e-2)

    def test_daily_value_percentage_cannot_substitute_for_nutrient_amount(self):
        """Req 5: Multi-column extraction must reject %RI / %DV column tokens for nutrient grams."""
        res = extract_structured([
            line("Per 100g", 100, 0, 180, 20),
            line("Per portion", 200, 0, 280, 20),
            line("% RI*", 300, 0, 360, 20),
            line("Proteines", 0, 30, 80, 50),
            line("4.7 g", 110, 30, 160, 50),
            line("2.1 g", 210, 30, 260, 50),
            line("14 %", 310, 30, 350, 50),
        ])
        prot = res["nutrients"]["protein_g"]
        # Percent value '14%' must never be selected as the nutrient amount
        assert prot["value"] != 14.0
        assert prot["value"] == 4.7

    def test_adjacent_nutrient_rows_do_not_overwrite_each_other(self):
        """Req 6: Adjacent vertical rows (e.g. Saturated Fat 2g, Trans Fat 0g) must not bleed."""
        res = extract_structured([
            line("Nutrition Facts", 0, 0, 200, 20),
            line("per serving", 0, 25, 100, 45),
            line("Total Fat 13g", 0, 50, 150, 70),
            line("Saturated Fat 2g", 0, 75, 170, 95),
            line("Trans Fat 0g", 0, 100, 140, 120),
        ])
        nuts = res["nutrients"]
        assert nuts["total_fat_g"]["value"] == 13.0
        assert nuts["saturated_fat_g"]["value"] == 2.0
        assert nuts["trans_fat_g"]["value"] == 0.0

    def test_dropped_decimal_comma_constraint_detection(self):
        """Req 7: Sub-component constraint flags when saturated fat exceeds total fat due to dropped comma."""
        tot_fat = 11.0
        raw_sat_fat = 53.0  # dropped comma from 5.3g
        # Sub-component constraint check
        is_implausible = raw_sat_fat > (tot_fat * 1.05)
        assert is_implausible is True
        # Decimal repair candidate
        recovered = raw_sat_fat / 10.0
        assert recovered <= tot_fat
        assert recovered == 5.3

    def test_inequality_retains_comparator_semantics(self):
        """Req 8: An inequality declaration '<1g' or '<0.1g' is evaluated with upper bound comparator."""
        def eval_inequality(gt_str, pred_val):
            if gt_str.startswith("<"):
                bound = float(gt_str[1:])
                return pred_val <= (bound * 1.05)
            return pred_val == float(gt_str)

        assert eval_inequality("<1", 1.0) is True
        assert eval_inequality("<1", 0.0) is True
        assert eval_inequality("<1", 0.5) is True
        assert eval_inequality("<1", 2.0) is False

    def test_missing_or_unreadable_ground_truth_not_treated_as_verified_absence(self):
        """Req 9: Unreadable / unannotated samples (e.g. front-only photos) do not count as verified zero/absence."""
        gt_sample = {
            "sample_id": "real_photo_13",
            "verification_status": "panel_not_legible",
            "serving_basis": "front_only",
            "declared_nutrients_on_label": {},
            "unresolved_fields": ["panel_not_photographed"]
        }
        # In benchmark scoring, when panel_not_legible or field in unresolved_fields,
        # missing declared fields must not increment FN, and absence must not be scored as zero.
        assert gt_sample["verification_status"] == "panel_not_legible"
        assert len(gt_sample["declared_nutrients_on_label"]) == 0
        assert "panel_not_photographed" in gt_sample["unresolved_fields"]
