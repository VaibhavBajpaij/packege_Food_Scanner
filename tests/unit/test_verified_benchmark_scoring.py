"""Regression tests for production benchmark scoring, provenance isolation, and reconciliation.

Tests the importable benchmark scorer (food_engine.evaluate.benchmark_scorer):
- Per-sample scoring (TP, FP, FN, core metrics, inequalities, serving basis)
- Strict mathematical reconciliation: per-sample sum == per-nutrient sum == overall
- Provenance tier isolation (label_declared vs calculated vs reference_derived)
- Unresolved / unreadable panel handling without false negative penalties
- Explicit dataset split reporting and validation
- Reconciled real_photo_14 physical label verification
"""

import json
from pathlib import Path
import pytest

from food_engine.evaluate.benchmark_scorer import (
    CANONICAL_NUTRIENT_MAP,
    CORE_NUTRIENTS,
    aggregate_benchmark,
    check_value_match,
    normalize_basis,
    partition_predicted_nutrients,
    score_sample,
)
from food_engine.nutrition_extraction.structured import extract_structured
from food_engine.product_matching.nutrient_fusion import NutrientFusion


def line(text, xmin, ymin, xmax, ymax, confidence=0.95):
    box = [[xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax]]
    return {"text": text, "confidence": confidence, "bounding_box": box}


class TestBenchmarkScorerUnit:
    def test_score_sample_perfect_match(self):
        sample_gt = {
            "sample_id": "test_01",
            "split": "dev",
            "serving_basis": "per_100g",
            "declared_nutrients_on_label": {
                "energy_kcal": 250.0,
                "fat_g": 10.0,
                "protein_g": 5.0,
            },
            "core_nutrients_on_label": {
                "energy_kcal": 250.0,
                "fat_g": 10.0,
                "protein_g": 5.0,
            },
            "chemically_calculated_from_label": {},
            "inequalities": {},
            "verification_status": "panel_verified_exact",
        }
        engine_out = {
            "nutrition": {
                "basis": "per_100g",
                "nutrients": {
                    "energy_kcal": {"value": 250.0, "status": "declared"},
                    "fat_g": {"value": 10.0, "status": "declared"},
                    "protein_g": {"value": 5.0, "status": "declared"},
                },
            }
        }
        res = score_sample(sample_gt, engine_out)
        m = res["metrics"]
        assert m["tp"] == 3
        assert m["fp"] == 0
        assert m["fn"] == 0
        assert m["precision"] == 1.0
        assert m["recall"] == 1.0
        assert m["f1"] == 1.0
        assert m["is_perfect"] is True
        assert res["serving_basis"]["match"] is True

    def test_wrong_value_counts_as_both_fp_and_fn(self):
        sample_gt = {
            "sample_id": "test_mismatch",
            "split": "dev",
            "serving_basis": "per_100g",
            "declared_nutrients_on_label": {"fat_g": 5.3},
            "core_nutrients_on_label": {"fat_g": 5.3},
        }
        engine_out = {
            "nutrition": {
                "basis": "per_100g",
                "nutrients": {"fat_g": {"value": 53.0, "status": "declared"}},
            }
        }
        res = score_sample(sample_gt, engine_out)
        m = res["metrics"]
        assert m["tp"] == 0
        assert m["fp"] == 1
        assert m["fn"] == 1
        assert m["precision"] == 0.0
        assert m["recall"] == 0.0
        assert m["is_perfect"] is False
        assert res["details"]["fields"]["fat_g"]["status"] == "FP_FN_MISMATCH"

    def test_spurious_prediction_counts_as_fp(self):
        sample_gt = {
            "sample_id": "test_spurious",
            "split": "dev",
            "serving_basis": "per_100g",
            "declared_nutrients_on_label": {"energy_kcal": 100.0},
        }
        engine_out = {
            "nutrition": {
                "basis": "per_100g",
                "nutrients": {
                    "energy_kcal": {"value": 100.0, "status": "declared"},
                    "saturated_fat_g": {"value": 2.0, "status": "declared"},
                },
            }
        }
        res = score_sample(sample_gt, engine_out)
        m = res["metrics"]
        assert m["tp"] == 1
        assert m["fp"] == 1
        assert m["fn"] == 0
        assert m["precision"] == 0.5
        assert m["recall"] == 1.0
        assert res["details"]["fields"]["saturated_fat_g"]["status"] == "FP_SPURIOUS"

    def test_comparator_inequality_semantics(self):
        sample_gt = {
            "sample_id": "test_ineq",
            "split": "dev",
            "serving_basis": "per_100g",
            "declared_nutrients_on_label": {"sugars_g": 1.0},
            "inequalities": {"sugars_g": "<1"},
        }
        # Value 0.5 is <= 1.0 -> TP
        res_ok = score_sample(sample_gt, {"nutrition": {"nutrients": {"sugars_g": {"value": 0.5, "status": "declared"}}}})
        assert res_ok["metrics"]["tp"] == 1
        assert res_ok["metrics"]["fp"] == 0

        # Value 2.5 exceeds upper bound -> FP and FN
        res_bad = score_sample(sample_gt, {"nutrition": {"nutrients": {"sugars_g": {"value": 2.5, "status": "declared"}}}})
        assert res_bad["metrics"]["tp"] == 0
        assert res_bad["metrics"]["fp"] == 1
        assert res_bad["metrics"]["fn"] == 1

    def test_unresolved_illegible_panel_handling(self):
        sample_gt = {
            "sample_id": "test_unreadable",
            "split": "dev",
            "verification_status": "panel_not_legible",
            "panel_not_legible": True,
            "declared_nutrients_on_label": {},
        }
        engine_out = {
            "nutrition": {
                "basis": "per_100g",
                "nutrients": {},
            }
        }
        res = score_sample(sample_gt, engine_out)
        assert res["is_legible"] is False
        assert res["metrics"]["fn"] == 0
        assert res["metrics"]["fp"] == 0
        assert res["metrics"]["tp"] == 0


class TestProvenanceIsolation:
    def test_provenance_isolation_declared_vs_calculated_vs_reference(self):
        sample_gt = {
            "sample_id": "test_prov",
            "split": "dev",
            "serving_basis": "per_100g",
            "declared_nutrients_on_label": {
                "sodium_mg": 400.0,
            },
            "chemically_calculated_from_label": {
                "salt_g": 1.0,
            },
        }
        engine_out = {
            "nutrition": {
                "basis": "per_100g",
                "nutrients": {
                    "sodium_mg": {"value": 400.0, "status": "declared"},
                    "salt_g": {"value": 1.0, "status": "calculated"},
                    "fibre_g": {"value": 3.0, "status": "reference_derived"},
                },
            }
        }
        res = score_sample(sample_gt, engine_out)
        # Declared evaluation must ONLY check sodium_mg
        assert res["metrics"]["tp"] == 1
        assert res["metrics"]["fp"] == 0
        assert res["metrics"]["fn"] == 0
        # salt_g must be captured in calculated tier
        assert res["calculated_metrics"]["tp"] == 1
        # fibre_g must be isolated in reference tier
        assert "fibre_g" in res["reference_details"]
        assert res["provenance_counts"]["declared_extracted"] == 1
        assert res["provenance_counts"]["chemically_calculated"] == 1
        assert res["provenance_counts"]["reference_derived"] == 1


class TestBenchmarkAggregationAndReconciliation:
    def test_aggregate_reconciliation_mathematical_identity(self):
        samples_gt = [
            {
                "sample_id": "s1",
                "split": "dev",
                "serving_basis": "per_100g",
                "declared_nutrients_on_label": {"fat_g": 10.0, "protein_g": 5.0},
                "core_nutrients_on_label": {"fat_g": 10.0, "protein_g": 5.0},
                "verification_status": "panel_verified_exact",
            },
            {
                "sample_id": "s2",
                "split": "dev",
                "serving_basis": "per_100g",
                "declared_nutrients_on_label": {"fat_g": 2.0, "sugars_g": 15.0},
                "core_nutrients_on_label": {"fat_g": 2.0, "sugars_g": 15.0},
                "verification_status": "panel_verified_exact",
            },
            {
                "sample_id": "s3",
                "split": "dev",
                "serving_basis": "per_100g",
                "declared_nutrients_on_label": {"protein_g": 8.0},
                "core_nutrients_on_label": {"protein_g": 8.0},
                "verification_status": "panel_verified_exact",
            },
        ]
        outputs = [
            {"nutrition": {"basis": "per_100g", "nutrients": {"fat_g": {"value": 10.0, "status": "declared"}, "protein_g": {"value": 5.0, "status": "declared"}}}},
            {"nutrition": {"basis": "per_100g", "nutrients": {"fat_g": {"value": 20.0, "status": "declared"}}}},  # fat mismatch (1 FP, 1 FN), sugars missing (1 FN)
            {"nutrition": {"basis": "per_100g", "nutrients": {"protein_g": {"value": 8.0, "status": "declared"}, "iron_mg": {"value": 1.0, "status": "declared"}}}},  # 1 TP, 1 spurious FP
        ]

        sample_results = [score_sample(gt, out) for gt, out in zip(samples_gt, outputs)]
        agg = aggregate_benchmark(sample_results)

        # 1. Sum of per-sample totals equals overall totals
        sum_sample_tp = sum(s["metrics"]["tp"] for s in sample_results)
        sum_sample_fp = sum(s["metrics"]["fp"] for s in sample_results)
        sum_sample_fn = sum(s["metrics"]["fn"] for s in sample_results)
        assert sum_sample_tp == agg["overall_declared"]["tp"]
        assert sum_sample_fp == agg["overall_declared"]["fp"]
        assert sum_sample_fn == agg["overall_declared"]["fn"]

        # 2. Sum of per-nutrient totals equals overall totals
        sum_nut_tp = sum(st["tp"] for st in agg["per_nutrient"].values())
        sum_nut_fp = sum(st["fp"] for st in agg["per_nutrient"].values())
        sum_nut_fn = sum(st["fn"] for st in agg["per_nutrient"].values())
        assert sum_nut_tp == agg["overall_declared"]["tp"]
        assert sum_nut_fp == agg["overall_declared"]["fp"]
        assert sum_nut_fn == agg["overall_declared"]["fn"]

        # 3. Overall reconciliation flag is verified True
        assert agg["reconciliation"]["is_reconciled"] is True

    def test_dataset_split_reporting_and_validation(self):
        samples_gt = [
            {"sample_id": "s1", "split": "dev", "serving_basis": "per_100g", "declared_nutrients_on_label": {"fat_g": 1.0}},
            {"sample_id": "s2", "split": "dev", "serving_basis": "per_100g", "declared_nutrients_on_label": {"fat_g": 2.0}},
        ]
        outputs = [
            {"nutrition": {"basis": "per_100g", "nutrients": {"fat_g": {"value": 1.0, "status": "declared"}}}},
            {"nutrition": {"basis": "per_100g", "nutrients": {"fat_g": {"value": 2.0, "status": "declared"}}}},
        ]
        sample_results = [score_sample(gt, out) for gt, out in zip(samples_gt, outputs)]
        agg = aggregate_benchmark(sample_results)

        assert "dev" in agg["splits"]
        assert agg["splits"]["dev"]["sample_count"] == 2
        assert "held_out" not in agg["splits"]


class TestRealPhoto14Reconciliation:
    def test_real_photo_14_with_gt_v4_scores_saturated_fat_as_tp(self):
        gt_v4 = json.load(open("tests/fixtures/real_photos/ground_truth_v4.json"))
        rp14_gt = [s for s in gt_v4["samples"] if s["sample_id"] == "real_photo_14"][0]

        # Engine output on rp14
        engine_output = {
            "nutrition": {
                "basis": "per_100_ml",
                "nutrients": {
                    "energy_kcal": {"value": 42.0, "status": "declared"},
                    "energy_kj": {"value": 180.0, "status": "declared"},
                    "protein_g": {"value": 0.0, "status": "declared"},
                    "carbohydrates_g": {"value": 10.6, "status": "declared"},
                    "sugars_g": {"value": 10.6, "status": "declared"},
                    "total_fat_g": {"value": 0.0, "status": "declared"},
                    "saturated_fat_g": {"value": 0.0, "status": "declared"},
                    "salt_g": {"value": None, "status": "missing"},
                },
            }
        }
        res = score_sample(rp14_gt, engine_output)
        # Saturated fat is now a verified statutory field in GT v4
        assert res["details"]["fields"]["saturated_fat_g"]["status"] == "TP"
        assert res["details"]["fields"]["saturated_fat_g"]["pred"] == 0.0
        assert res["details"]["fields"]["saturated_fat_g"]["gt"] == 0.0
        # No spurious false positives
        assert res["metrics"]["fp"] == 0
        assert res["metrics"]["tp"] == 7
        assert res["metrics"]["fn"] == 1  # salt_g missing


class TestPipelineExtractionIntegrity:
    def test_daily_value_percentage_cannot_substitute_for_nutrient_amount(self):
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
        assert prot["value"] != 14.0
        assert prot["value"] == 4.7

    def test_adjacent_nutrient_rows_do_not_bleed(self):
        res = extract_structured([
            line("Total Fat 7g", 0, 0, 150, 20),
            line("Saturated Fat 2g", 0, 25, 180, 45),
            line("Trans Fat 0g", 0, 50, 150, 70),
        ])
        nuts = res["nutrients"]
        assert nuts["total_fat_g"]["value"] == 7.0
        assert nuts["saturated_fat_g"]["value"] == 2.0
        assert nuts["trans_fat_g"]["value"] == 0.0

    def test_dropped_decimal_comma_yields_error(self):
        gt_val = 5.3
        pred_val = 53.0
        is_match, reason = check_value_match(gt_val, pred_val, tol=0.05)
        assert is_match is False
        assert "rel_err" in reason
