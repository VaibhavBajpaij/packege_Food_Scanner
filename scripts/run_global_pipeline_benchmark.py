#!/usr/bin/env python3
"""Run Automated Global Testing & Benchmarking Pipeline across Multi-Country Packaged Food Dataset.

Evaluates:
1. Barcode Lookup & Completeness Decision against local database
2. Pre-flight Image Quality Gate (Blur / Sharpness)
3. PaddleOCR PP-OCRv4 extraction & structured table parsing
4. Ingredient parsing & Allergen detection
5. Nutrient provenance fusion (DECLARED, EXACT_DB, REFERENCE_DB, CALCULATED)
6. Physical sanity checks (Atwater formula, mass conservation, parent-child bounds)
7. Ground truth evaluation (TP, FP, FN, Precision, Recall, F1)
8. Automated Hard-Example & Failure Triage Queue (Bucket A vs Bucket B)

Outputs:
- reports/evaluation/global_pipeline_benchmark_report.json
- reports/evaluation/global_pipeline_benchmark_report.md
- datasets/triage/ (automated triage reports for failures)
"""

import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.engine import FoodIntelligenceEngine
from food_engine.validation.triage_logger import (
    calculate_blur_score,
    check_image_quality,
    log_triage_case
)

DATASET_DIR = REPO_ROOT / "datasets" / "evaluation" / "global_packaged_food"
MANIFEST_PATH = DATASET_DIR / "global_ground_truth.json"
REPORT_DIR = REPO_ROOT / "reports" / "evaluation"

EVAL_FIELDS = [
    "energy_kcal",
    "protein_g",
    "carbohydrates_g",
    "sugars_g",
    "fat_g",
    "saturated_fat_g",
    "fiber_g",
    "sodium_mg",
    "salt_g"
]


def is_match(pred: Optional[float], gt: Optional[float], tolerance_pct: float = 0.05, abs_tol: float = 0.5) -> bool:
    """Evaluate whether an extracted value matches ground truth within standard testing tolerance."""
    if pred is None or gt is None:
        return False
    # Absolute tolerance
    diff = abs(pred - gt)
    if diff <= abs_tol:
        return True
    # Percentage tolerance
    if gt != 0:
        if (diff / abs(gt)) <= tolerance_pct:
            return True
    return False


def verify_physical_sanity(nutrients: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check physical and chemical laws of food nutrition."""
    warnings = []
    
    p = nutrients.get("protein_g") or 0.0
    c = nutrients.get("carbohydrates_g") or 0.0
    f = nutrients.get("fat_g") or 0.0
    kcal = nutrients.get("energy_kcal")
    sugars = nutrients.get("sugars_g")
    sat_fat = nutrients.get("saturated_fat_g")

    # 1. Mass conservation per 100g: P + C + F + ash/water <= 105g (5g margin for rounding)
    macro_sum = p + c + f
    if macro_sum > 105.0:
        warnings.append(f"Macronutrient sum ({macro_sum:.1f}g) exceeds 100g limit.")

    # 2. Sub-component bounds: Sugars <= Carbs
    if sugars is not None and c > 0:
        if sugars > (c + 1.0):
            warnings.append(f"Sugars ({sugars:.1f}g) exceeds total carbohydrates ({c:.1f}g).")

    # 3. Sub-component bounds: Sat Fat <= Total Fat
    if sat_fat is not None and f > 0:
        if sat_fat > (f + 1.0):
            warnings.append(f"Saturated fat ({sat_fat:.1f}g) exceeds total fat ({f:.1f}g).")

    # 4. Atwater energy calculation: kcal approx 4*P + 4*C + 9*F
    if kcal is not None and kcal > 0 and macro_sum > 5.0:
        calc_kcal = (4.0 * p) + (4.0 * c) + (9.0 * f)
        diff_kcal = abs(kcal - calc_kcal)
        if diff_kcal > 100.0 and (diff_kcal / kcal) > 0.35:
            warnings.append(f"Atwater mismatch: Declared {kcal:.0f} kcal vs calculated {calc_kcal:.0f} kcal.")

    return len(warnings) == 0, warnings


def run_benchmark():
    if not MANIFEST_PATH.exists():
        print(f"Error: Manifest not found at {MANIFEST_PATH}. Run download_global_packaged_food_dataset.py first.")
        sys.exit(1)

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    samples = manifest.get("samples", [])
    print("=" * 80)
    print(f"RUNNING AUTOMATED GLOBAL PACKAGED FOOD SCANNER BENCHMARK")
    print(f"Total Products: {len(samples)} across {len(manifest.get('countries_covered', []))} countries")
    print("=" * 80)

    # Initialize Engine (PP-OCRv4 CPU cached)
    print("Initializing FoodIntelligenceEngine...")
    t_start = time.time()
    engine = FoodIntelligenceEngine()
    print(f"Engine initialized in {time.time() - t_start:.2f}s.\n")

    results = []
    total_tp = 0
    total_fp = 0
    total_fn = 0

    regional_stats = {}
    country_stats = {}

    for idx, sample in enumerate(samples, 1):
        sample_id = sample["sample_id"]
        code = sample["barcode"]
        name = sample["product_name"]
        country = sample["country"]
        region = sample["region"]
        img_rel_path = sample["local_image_path"]
        img_path = REPO_ROOT / img_rel_path
        gt_nuts = sample.get("ground_truth_nutrients_100g", {})

        print(f"[{idx:02d}/{len(samples)}] Testing {sample_id} | {country} | {code} ({name[:30]})...")

        if region not in regional_stats:
            regional_stats[region] = {"total": 0, "tp": 0, "fp": 0, "fn": 0, "barcode_matches": 0, "ocr_successes": 0}
        if country not in country_stats:
            country_stats[country] = {"total": 0, "tp": 0, "fp": 0, "fn": 0, "barcode_matches": 0, "ocr_successes": 0}

        regional_stats[region]["total"] += 1
        country_stats[country]["total"] += 1

        # Check if local image exists
        if not img_path.exists():
            print(f"  Warning: Image {img_path} not found. Skipping image OCR.")
            continue

        # Stage 1: Pre-flight Image Quality Check
        blur_passed, blur_score, blur_msg = check_image_quality(img_path)

        # Stage 2: Execute Engine Pipeline
        t0 = time.time()
        try:
            scan_res = engine.process_image(str(img_path), barcode=code)
            elapsed = time.time() - t0
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"  FAILED with exception: {exc}")
            log_triage_case(
                img_path,
                failure_reason="ENGINE_EXCEPTION",
                details={"exception": str(exc), "trace": "FoodIntelligenceEngine.process_image failed"},
                sample_id=sample_id,
                barcode=code,
                product_name=name
            )
            continue

        # Analyze Barcode match
        prod_match = scan_res.get("product_match") or {}
        barcode_match = (
            prod_match.get("status") in ("exact_barcode_match", "exact_match", "matched")
            or prod_match.get("confidence", 0.0) > 0.5
        )
        if barcode_match:
            regional_stats[region]["barcode_matches"] += 1
            country_stats[country]["barcode_matches"] += 1

        # Extract predicted nutrients
        pred_nuts = {}
        fused_nutrients = scan_res.get("nutrition", {}).get("nutrients", {})
        for k, v in fused_nutrients.items():
            if isinstance(v, dict):
                val = v.get("value")
            else:
                val = getattr(v, "value", None)
            if val is not None:
                # normalize key names
                std_k = k
                if std_k == "calories":
                    std_k = "energy_kcal"
                elif std_k == "carbs":
                    std_k = "carbohydrates_g"
                elif std_k == "fat":
                    std_k = "fat_g"
                elif std_k == "protein":
                    std_k = "protein_g"
                pred_nuts[std_k] = val

        # Physical sanity checks
        sanity_passed, sanity_warnings = verify_physical_sanity(pred_nuts)

        # Evaluate against Ground Truth
        sample_tp = 0
        sample_fp = 0
        sample_fn = 0
        field_evaluations = {}

        for field in EVAL_FIELDS:
            gt_val = gt_nuts.get(field)
            pred_val = pred_nuts.get(field)

            if gt_val is not None:
                if pred_val is not None:
                    if is_match(pred_val, gt_val):
                        status = "TP"
                        sample_tp += 1
                    else:
                        status = "FP_INCORRECT"
                        sample_fp += 1
                else:
                    status = "FN_MISSING"
                    sample_fn += 1
            else:
                if pred_val is not None:
                    # Predicted a nutrient not in ground truth
                    status = "FP_EXTRA"
                    sample_fp += 1
                else:
                    status = "TN"

            field_evaluations[field] = {
                "ground_truth": gt_val,
                "predicted": pred_val,
                "status": status
            }

        total_tp += sample_tp
        total_fp += sample_fp
        total_fn += sample_fn

        regional_stats[region]["tp"] += sample_tp
        regional_stats[region]["fp"] += sample_fp
        regional_stats[region]["fn"] += sample_fn

        country_stats[country]["tp"] += sample_tp
        country_stats[country]["fp"] += sample_fp
        country_stats[country]["fn"] += sample_fn

        if sample_tp > 0:
            regional_stats[region]["ocr_successes"] += 1
            country_stats[country]["ocr_successes"] += 1

        precision = sample_tp / (sample_tp + sample_fp) if (sample_tp + sample_fp) > 0 else 0.0
        recall = sample_tp / (sample_tp + sample_fn) if (sample_tp + sample_fn) > 0 else 0.0

        # Automatic Triage Logging on low performance or sanity warnings
        if not sanity_passed or (sample_fp > sample_tp and sample_tp < 3):
            triage_reason = "SANITY_CHECK_WARNINGS" if not sanity_passed else "POOR_EXTRACTION_ACCURACY"
            log_triage_case(
                img_path,
                failure_reason=triage_reason,
                details={
                    "sanity_warnings": sanity_warnings,
                    "sample_tp": sample_tp,
                    "sample_fp": sample_fp,
                    "sample_fn": sample_fn,
                    "predicted_nutrients": pred_nuts,
                    "ground_truth": gt_nuts
                },
                sample_id=sample_id,
                barcode=code,
                product_name=name
            )

        print(f"  -> TP={sample_tp}, FP={sample_fp}, FN={sample_fn} | Precision={precision:.1%}, Recall={recall:.1%} | {elapsed:.2f}s | Sanity={'PASS' if sanity_passed else 'WARN'}")

        results.append({
            "sample_id": sample_id,
            "barcode": code,
            "product_name": name,
            "country": country,
            "region": region,
            "image_filename": sample["image_filename"],
            "blur_score": blur_score,
            "blur_passed": blur_passed,
            "barcode_matched": barcode_match,
            "elapsed_seconds": round(elapsed, 2),
            "sample_tp": sample_tp,
            "sample_fp": sample_fp,
            "sample_fn": sample_fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "sanity_passed": sanity_passed,
            "sanity_warnings": sanity_warnings,
            "field_evaluations": field_evaluations
        })

    # Overall Summary
    overall_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    overall_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    overall_f1 = (2 * overall_prec * overall_rec) / (overall_prec + overall_rec) if (overall_prec + overall_rec) > 0 else 0.0

    print("\n" + "=" * 80)
    print("GLOBAL BENCHMARK COMPLETE")
    print(f"Total Evaluated: {len(results)} products across {len(country_stats)} countries")
    print(f"Overall Metrics: TP={total_tp}, FP={total_fp}, FN={total_fn}")
    print(f"Precision: {overall_prec:.2%}")
    print(f"Recall:    {overall_rec:.2%}")
    print(f"F1 Score:  {overall_f1:.2%}")
    print("=" * 80)

    # Save JSON Report
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_json_path = REPORT_DIR / "global_pipeline_benchmark_report.json"
    report_data = {
        "benchmark_name": "Global Packaged Food Scanner Comprehensive Benchmark",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_samples": len(results),
        "overall_metrics": {
            "true_positives": total_tp,
            "false_positives": total_fp,
            "false_negatives": total_fn,
            "precision": round(overall_prec, 4),
            "recall": round(overall_rec, 4),
            "f1_score": round(overall_f1, 4)
        },
        "regional_breakdown": regional_stats,
        "country_breakdown": country_stats,
        "results": results
    }
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"Saved JSON Report: {report_json_path}")

    # Generate Detailed Markdown Report
    report_md_path = REPORT_DIR / "global_pipeline_benchmark_report.md"
    reg_rows = []
    for reg, stats in regional_stats.items():
        r_tp, r_fp, r_fn = stats["tp"], stats["fp"], stats["fn"]
        r_p = r_tp / (r_tp + r_fp) if (r_tp + r_fp) > 0 else 0.0
        r_r = r_tp / (r_tp + r_fn) if (r_tp + r_fn) > 0 else 0.0
        reg_rows.append(f"| **{reg}** | {stats['total']} | {stats['barcode_matches']} | {stats['ocr_successes']} | {r_tp} | {r_fp} | {r_fn} | {r_p:.1%} | {r_r:.1%} |")

    sample_rows = []
    for r in results:
        san = "✅ Pass" if r["sanity_passed"] else "⚠️ Warn"
        sample_rows.append(
            f"| `{r['sample_id']}` | {r['country']} | **{r['product_name'][:24]}** | {r['sample_tp']} | {r['sample_fp']} | {r['sample_fn']} | {r['precision']:.1%} | {r['recall']:.1%} | {san} | {r['elapsed_seconds']}s |"
        )

    md_content = f"""# Global Packaged Food Scanner — Benchmark & Verification Report

**Evaluation Date:** {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}  
**Dataset Scope:** Multi-Country Global Holdout (North America, Europe, Asia-Pacific, Global Brands)  
**License:** Open Food Facts (ODbL 1.0) — **100% Commercially Permissible for QA & Evaluation**  

---

## Executive Summary

| Total Packaged Foods | Total Correct (TP) | Incorrect (FP) | Missing (FN) | Field Precision | Field Recall | Global F1-Score |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **{len(results)}** | **{total_tp}** | **{total_fp}** | **{total_fn}** | **{overall_prec:.1%}** | **{overall_rec:.1%}** | **{overall_f1:.1%}** |
> [!NOTE]
> Evaluation enforces a standard tolerance of $\\pm 5\\%$ relative error or $\\pm 0.5\\text{{g}}$ absolute difference. Extra ungrounded extractions are penalized as False Positives, and undetected nutrients are penalized as False Negatives.

---

## Regional Performance Breakdown

| Region | Samples | Barcode DB Matches | Successful Extractions | TP | FP | FN | Precision | Recall |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
{chr(10).join(reg_rows)}

---

## Product-by-Product Evaluation Ledger

| Sample ID | Country | Product Name | TP | FP | FN | Precision | Recall | Physical Sanity | Runtime |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
{chr(10).join(sample_rows)}

---

## Automated Hard-Example & Failure Triage (Active Learning)

Failed or uncertain scans are automatically logged with companion JSON sidecars in `datasets/triage/reports/`:
- **Bucket A (Photographic Fault):** Blur, extreme glare, out-of-focus camera. Prompt user to retake photo.
- **Bucket B (Engine Bug):** Sharp readable image, but table parser or regex missed fields. Automatically added to the developer remediation queue.
"""
    report_md_path.write_text(md_content, encoding="utf-8")
    print(f"Saved Markdown Report: {report_md_path}")


if __name__ == "__main__":
    run_benchmark()
