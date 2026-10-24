"""Benchmark scoring and aggregation module for Food Intelligence Engine.

Provides importable, mathematically verified evaluation functions:
- Provenance separation (label_declared vs calculated vs reference_derived)
- Exact value and comparator (<) inequality matching
- Per-sample and aggregate TP/FP/FN metrics
- Strict reconciliation: per-nutrient sum == per-sample sum == overall total
- Explicit dataset split tracking and validation
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

CANONICAL_NUTRIENT_MAP: Dict[str, str] = {
    "energy_kcal": "energy_kcal",
    "energy_kj": "energy_kj",
    "protein_g": "protein_g",
    "carbohydrates_g": "carbohydrates_g",
    "sugars_g": "sugars_g",
    "added_sugars_g": "added_sugars_g",
    "fat_g": "fat_g",
    "total_fat_g": "fat_g",
    "saturated_fat_g": "saturated_fat_g",
    "trans_fat_g": "trans_fat_g",
    "fibre_g": "fibre_g",
    "dietary_fibre_g": "fibre_g",
    "fiber_g": "fibre_g",
    "sodium_mg": "sodium_mg",
    "salt_g": "salt_g",
    "cholesterol_mg": "cholesterol_mg",
    "calcium_mg": "calcium_mg",
    "iron_mg": "iron_mg",
    "potassium_mg": "potassium_mg",
    "vitamin_d_mcg": "vitamin_d_mcg",
    "magnesium_mg": "magnesium_mg",
    "zinc_mg": "zinc_mg",
    "vitamin_c_mg": "vitamin_c_mg",
}

CORE_NUTRIENTS: Set[str] = {
    "energy_kcal",
    "protein_g",
    "carbohydrates_g",
    "sugars_g",
    "fat_g",
    "saturated_fat_g",
    "sodium_mg",
    "salt_g",
}

DEFAULT_TOLERANCE = 0.05


def normalize_basis(raw_basis: Optional[str]) -> str:
    """Normalise serving basis to standard canonical string."""
    if not raw_basis:
        return "per_100g"
    b = str(raw_basis).lower().strip().replace("-", "_").replace(" ", "_")
    if "serving" in b:
        return "per_serving"
    if "100ml" in b or "100_ml" in b:
        return "per_100ml"
    if "100g" in b or "100_g" in b:
        return "per_100g"
    if "front" in b:
        return "front_only"
    return "per_100g"


def check_value_match(
    gt_val: float,
    pred_val: Any,
    tol: float = DEFAULT_TOLERANCE,
    comparator: Optional[str] = None,
) -> Tuple[bool, str]:
    """Evaluates whether predicted numeric value matches ground truth within tolerance.

    Supports:
    - Relative tolerance for positive quantities (default 5%)
    - Strict zero matching (pred == 0 for gt == 0)
    - Comparator upper-bound matching for inequalities (e.g. '<1g' or '<0.1g')
    """
    if pred_val is None:
        return False, "missing_prediction"
    try:
        p = float(pred_val)
        g = float(gt_val)
    except (ValueError, TypeError):
        return False, f"unparseable_value_(gt={gt_val}, pred={pred_val})"

    if comparator == "<":
        # Upper-bound inequality (e.g. '<1g')
        if p <= g * (1.0 + tol) + 1e-6:
            return True, f"matched_inequality_upper_bound_(gt<{g}, pred={p})"
        return False, f"exceeds_upper_bound_(gt<{g}, pred={p})"

    if abs(g) < 1e-6:
        if abs(p) < 1e-6:
            return True, "matched_zero"
        return False, f"predicted_non_zero_for_zero_gt_(pred={p})"

    if abs(p) < 1e-6:
        return False, "predicted_zero_for_non_zero_gt"

    rel_err = abs(p - g) / abs(g)
    if rel_err <= tol:
        return True, f"matched_within_{tol*100:.1f}%_(rel_err={rel_err*100:.2f}%)"
    return False, f"rel_err_{rel_err*100:.2f}%_(gt={g}, pred={p})"


def partition_predicted_nutrients(
    pred_nutrients_raw: Dict[str, Any],
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    """Partitions raw engine predicted nutrients into declared, calculated, and reference tiers."""
    pred_declared: Dict[str, float] = {}
    pred_calculated: Dict[str, float] = {}
    pred_reference: Dict[str, float] = {}

    for raw_k, item in pred_nutrients_raw.items():
        canon_k = CANONICAL_NUTRIENT_MAP.get(raw_k, raw_k)
        if not isinstance(item, dict) or item.get("value") is None:
            continue

        status = item.get("status")
        try:
            val = float(item["value"])
        except (ValueError, TypeError):
            continue

        if status == "declared":
            pred_declared[canon_k] = val
        elif status == "calculated":
            pred_calculated[canon_k] = val
        elif status == "reference_derived":
            pred_reference[canon_k] = val
        else:
            # Default non-null fallback to declared if status is unspecified
            pred_declared[canon_k] = val

    return pred_declared, pred_calculated, pred_reference


def score_sample(
    sample_gt: Dict[str, Any],
    engine_output: Dict[str, Any],
    tolerance: float = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Evaluates a single food package output against ground truth.

    Distinguishes:
    - Visually declared label nutrients
    - Stoichiometrically calculated nutrients
    - Reference-database fallbacks
    - Unreadable / illegible panels
    """
    sid = sample_gt.get("sample_id", "unknown")
    filename = sample_gt.get("file_name", "")
    split = sample_gt.get("split", "dev")
    verification_status = sample_gt.get("verification_status", "panel_verified_exact")

    # Handle unreadable panels explicitly
    is_legible = verification_status != "panel_not_legible" and not sample_gt.get("panel_not_legible", False)

    gt_declared = sample_gt.get("declared_nutrients_on_label", {})
    gt_core = sample_gt.get("core_nutrients_on_label", {})
    gt_calc = sample_gt.get("chemically_calculated_from_label", {})
    inequalities = sample_gt.get("inequalities", {})
    gt_basis = normalize_basis(sample_gt.get("serving_basis"))

    pred_nutrition = engine_output.get("nutrition", {})
    pred_basis = normalize_basis(pred_nutrition.get("basis"))
    pred_nutrients_raw = pred_nutrition.get("nutrients", {})

    pred_declared, pred_calculated, pred_reference = partition_predicted_nutrients(pred_nutrients_raw)

    sample_tp = 0
    sample_fp = 0
    sample_fn = 0
    core_tp = 0
    core_fp = 0
    core_fn = 0
    declared_gt_count = 0
    core_gt_count = 0

    sample_details: Dict[str, Any] = {"fields": {}, "errors": []}

    if is_legible:
        # 1. Evaluate Declared Ground Truth Targets (Recall & TP)
        for gt_field, gt_val in gt_declared.items():
            canon_field = CANONICAL_NUTRIENT_MAP.get(gt_field, gt_field)
            if gt_val is None:
                continue

            declared_gt_count += 1
            is_core = canon_field in CORE_NUTRIENTS
            if is_core:
                core_gt_count += 1

            pred_val = pred_declared.get(canon_field)
            comp = "<" if canon_field in inequalities else None
            is_match, err_reason = check_value_match(gt_val, pred_val, tol=tolerance, comparator=comp)

            if is_match:
                sample_tp += 1
                if is_core:
                    core_tp += 1
                sample_details["fields"][canon_field] = {
                    "status": "TP",
                    "gt": gt_val,
                    "pred": pred_val,
                    "reason": err_reason,
                    "is_core": is_core,
                }
            else:
                sample_fn += 1
                if is_core:
                    core_fn += 1
                if pred_val is None:
                    sample_details["fields"][canon_field] = {
                        "status": "FN_MISSING",
                        "gt": gt_val,
                        "pred": None,
                        "is_core": is_core,
                    }
                    sample_details["errors"].append({
                        "field": canon_field,
                        "type": "missing",
                        "gt": gt_val,
                        "pred": None,
                        "is_core": is_core,
                    })
                else:
                    # Wrong value counts as both FP and FN
                    sample_fp += 1
                    if is_core:
                        core_fp += 1
                    sample_details["fields"][canon_field] = {
                        "status": "FP_FN_MISMATCH",
                        "gt": gt_val,
                        "pred": pred_val,
                        "reason": err_reason,
                        "is_core": is_core,
                    }
                    sample_details["errors"].append({
                        "field": canon_field,
                        "type": "value_mismatch",
                        "gt": gt_val,
                        "pred": pred_val,
                        "reason": err_reason,
                        "is_core": is_core,
                    })

        # 2. Evaluate Extra Declared Predictions Not in GT (Precision & FP)
        canon_gt_fields = {CANONICAL_NUTRIENT_MAP.get(k, k) for k in gt_declared.keys()}
        for pred_field, pred_val in pred_declared.items():
            if pred_field not in canon_gt_fields:
                is_core = pred_field in CORE_NUTRIENTS
                sample_fp += 1
                if is_core:
                    core_fp += 1
                sample_details["fields"][pred_field] = {
                    "status": "FP_SPURIOUS",
                    "gt": None,
                    "pred": pred_val,
                    "is_core": is_core,
                }
                sample_details["errors"].append({
                    "field": pred_field,
                    "type": "spurious",
                    "gt": None,
                    "pred": pred_val,
                    "is_core": is_core,
                })

    # Evaluate Chemically Calculated Nutrients
    calc_tp = 0
    calc_gt_count = 0
    calc_details: Dict[str, Any] = {}
    for c_field, c_val in gt_calc.items():
        canon_c = CANONICAL_NUTRIENT_MAP.get(c_field, c_field)
        calc_gt_count += 1
        pred_c = pred_calculated.get(canon_c)
        c_match, c_reason = check_value_match(c_val, pred_c, tol=0.15)
        if c_match:
            calc_tp += 1
            calc_details[canon_c] = {"status": "TP", "gt": c_val, "pred": pred_c, "reason": c_reason}
        else:
            calc_details[canon_c] = {"status": "MISMATCH", "gt": c_val, "pred": pred_c, "reason": c_reason}

    # Serving basis evaluation
    basis_match = (gt_basis == pred_basis) if is_legible else None

    # Sample-level precision and recall
    prec = round(sample_tp / (sample_tp + sample_fp), 4) if (sample_tp + sample_fp) > 0 else 0.0
    rec = round(sample_tp / declared_gt_count, 4) if declared_gt_count > 0 else (1.0 if not is_legible else 0.0)
    f1 = round(2 * prec * rec / (prec + rec), 4) if (prec + rec) > 0 else 0.0
    is_perfect = (sample_tp == declared_gt_count and sample_fp == 0) if is_legible else False

    return {
        "sample_id": sid,
        "filename": filename,
        "split": split,
        "is_legible": is_legible,
        "verification_status": verification_status,
        "serving_basis": {
            "gt": gt_basis,
            "pred": pred_basis,
            "match": basis_match,
        },
        "metrics": {
            "tp": sample_tp,
            "fp": sample_fp,
            "fn": sample_fn,
            "declared_gt_fields": declared_gt_count,
            "core_tp": core_tp,
            "core_fp": core_fp,
            "core_fn": core_fn,
            "core_gt_fields": core_gt_count,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "is_perfect": is_perfect,
        },
        "provenance_counts": {
            "declared_extracted": len(pred_declared),
            "chemically_calculated": len(pred_calculated),
            "reference_derived": len(pred_reference),
        },
        "calculated_metrics": {
            "tp": calc_tp,
            "total_gt": calc_gt_count,
            "details": calc_details,
        },
        "reference_details": {k: v for k, v in pred_reference.items()},
        "details": sample_details,
    }


def aggregate_benchmark(sample_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregates per-sample evaluation results into reconciled benchmark metrics.

    Guarantees strict reconciliation across:
    1. Overall sums (sum of sample TP/FP/FN == overall TP/FP/FN)
    2. Per-nutrient sums (sum of nutrient TP/FP/FN == overall TP/FP/FN)
    3. Dataset split tracking (dev vs test)
    """
    overall_tp = 0
    overall_fp = 0
    overall_fn = 0
    overall_gt = 0

    core_tp = 0
    core_fp = 0
    core_fn = 0
    core_gt = 0

    calc_tp = 0
    calc_gt = 0
    ref_derived_total = 0

    perfect_count = 0
    basis_matches = 0
    basis_total = 0

    per_nutrient_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "gt": 0})
    split_counts: Dict[str, int] = defaultdict(int)
    split_metrics: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "gt": 0})

    for s in sample_results:
        m = s["metrics"]
        split = s.get("split", "dev")
        split_counts[split] += 1

        overall_tp += m["tp"]
        overall_fp += m["fp"]
        overall_fn += m["fn"]
        overall_gt += m["declared_gt_fields"]

        core_tp += m["core_tp"]
        core_fp += m["core_fp"]
        core_fn += m["core_fn"]
        core_gt += m["core_gt_fields"]

        split_metrics[split]["tp"] += m["tp"]
        split_metrics[split]["fp"] += m["fp"]
        split_metrics[split]["fn"] += m["fn"]
        split_metrics[split]["gt"] += m["declared_gt_fields"]

        if m["is_perfect"]:
            perfect_count += 1

        sb = s.get("serving_basis", {})
        if sb.get("match") is not None:
            basis_total += 1
            if sb.get("match"):
                basis_matches += 1

        # Tally per-nutrient counts
        fields = s.get("details", {}).get("fields", {})
        for field_name, f_data in fields.items():
            status = f_data.get("status")
            if status == "TP":
                per_nutrient_stats[field_name]["tp"] += 1
                per_nutrient_stats[field_name]["gt"] += 1
            elif status == "FN_MISSING":
                per_nutrient_stats[field_name]["fn"] += 1
                per_nutrient_stats[field_name]["gt"] += 1
            elif status == "FP_SPURIOUS":
                per_nutrient_stats[field_name]["fp"] += 1
            elif status == "FP_FN_MISMATCH":
                per_nutrient_stats[field_name]["fp"] += 1
                per_nutrient_stats[field_name]["fn"] += 1
                per_nutrient_stats[field_name]["gt"] += 1

        # Tally calculated and reference tiers
        c_met = s.get("calculated_metrics", {})
        calc_tp += c_met.get("tp", 0)
        calc_gt += c_met.get("total_gt", 0)

        prov = s.get("provenance_counts", {})
        ref_derived_total += prov.get("reference_derived", 0)

    # Reconciliation check: sum of per-nutrient stats == overall
    nutrient_sum_tp = sum(st["tp"] for st in per_nutrient_stats.values())
    nutrient_sum_fp = sum(st["fp"] for st in per_nutrient_stats.values())
    nutrient_sum_fn = sum(st["fn"] for st in per_nutrient_stats.values())
    nutrient_sum_gt = sum(st["gt"] for st in per_nutrient_stats.values())

    is_reconciled = (
        nutrient_sum_tp == overall_tp
        and nutrient_sum_fp == overall_fp
        and nutrient_sum_fn == overall_fn
        and nutrient_sum_gt == overall_gt
    )

    # Calculate overall macro/micro rates
    def calc_p_r_f1(tp: int, fp: int, fn: int, gt: int) -> Dict[str, float]:
        p = round(tp / (tp + fp), 4) if (tp + fp) > 0 else 0.0
        r = round(tp / gt, 4) if gt > 0 else 0.0
        f = round(2 * p * r / (p + r), 4) if (p + r) > 0 else 0.0
        return {"precision": p, "recall": r, "f1": f}

    overall_prf = calc_p_r_f1(overall_tp, overall_fp, overall_fn, overall_gt)
    core_prf = calc_p_r_f1(core_tp, core_fp, core_fn, core_gt)

    per_nutrient_summary: Dict[str, Dict[str, Any]] = {}
    for nutrient, st in sorted(per_nutrient_stats.items()):
        prf = calc_p_r_f1(st["tp"], st["fp"], st["fn"], st["gt"])
        per_nutrient_summary[nutrient] = {
            "gt": st["gt"],
            "tp": st["tp"],
            "fp": st["fp"],
            "fn": st["fn"],
            "precision": prf["precision"],
            "recall": prf["recall"],
            "f1": prf["f1"],
            "is_core": nutrient in CORE_NUTRIENTS,
        }

    splits_summary: Dict[str, Any] = {}
    for sp, cnt in split_counts.items():
        sm = split_metrics[sp]
        prf = calc_p_r_f1(sm["tp"], sm["fp"], sm["fn"], sm["gt"])
        splits_summary[sp] = {
            "sample_count": cnt,
            "tp": sm["tp"],
            "fp": sm["fp"],
            "fn": sm["fn"],
            "gt": sm["gt"],
            "precision": prf["precision"],
            "recall": prf["recall"],
            "f1": prf["f1"],
        }

    total_samples = len(sample_results)
    perfect_rate = round(perfect_count / total_samples, 4) if total_samples > 0 else 0.0
    basis_rate = round(basis_matches / basis_total, 4) if basis_total > 0 else 0.0

    return {
        "total_samples": total_samples,
        "splits": splits_summary,
        "reconciliation": {
            "overall_tp": overall_tp,
            "nutrient_sum_tp": nutrient_sum_tp,
            "overall_fp": overall_fp,
            "nutrient_sum_fp": nutrient_sum_fp,
            "overall_fn": overall_fn,
            "nutrient_sum_fn": nutrient_sum_fn,
            "overall_gt": overall_gt,
            "nutrient_sum_gt": nutrient_sum_gt,
            "is_reconciled": is_reconciled,
        },
        "overall_declared": {
            "tp": overall_tp,
            "fp": overall_fp,
            "fn": overall_fn,
            "gt_total": overall_gt,
            "precision": overall_prf["precision"],
            "recall": overall_prf["recall"],
            "f1": overall_prf["f1"],
        },
        "core_declared": {
            "tp": core_tp,
            "fp": core_fp,
            "fn": core_fn,
            "gt_total": core_gt,
            "precision": core_prf["precision"],
            "recall": core_prf["recall"],
            "f1": core_prf["f1"],
        },
        "package_level": {
            "perfect_samples": perfect_count,
            "total_samples": total_samples,
            "accuracy": perfect_rate,
            "serving_basis_matches": basis_matches,
            "serving_basis_total": basis_total,
            "serving_basis_accuracy": basis_rate,
        },
        "calculated_nutrients": {
            "tp": calc_tp,
            "total_gt": calc_gt,
            "accuracy": round(calc_tp / calc_gt, 4) if calc_gt > 0 else 0.0,
        },
        "reference_derived": {
            "total_injected": ref_derived_total,
        },
        "per_nutrient": per_nutrient_summary,
    }
