#!/usr/bin/env python3
"""Reproducible Full-Pipeline Benchmark for Food Intelligence Engine (Phase 4).

Evaluates the genuine end-to-end food intelligence engine (FoodIntelligenceEngine)
across real packaging photographs against ground_truth_v2.json.

Key audit criteria enforced:
- True TP, FP, and FN accounting (penalizes spurious/hallucinated nutrient predictions).
- Normalizes nutrient names, units, and serving bases before comparison.
- Excludes genuinely unknown/unreadable ground-truth values from the denominator.
- Proper perfect-sample accounting (all declared fields correct, zero false positives, basis match).
- Measures per-image latency and peak working set memory.
- Captures environment and Git commit / dirty state.
- Clearly labels output as a DEVELOPMENT benchmark.

Outputs:
- reports/evaluation/full_pipeline_benchmark_v3.json
- reports/evaluation/full_pipeline_benchmark_v3.md
"""

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.engine import FoodIntelligenceEngine

# Canonical nutrient names and alias mapping
CANONICAL_NUTRIENT_MAP = {
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
}

CORE_NUTRIENTS = {
    "energy_kcal",
    "fat_g",
    "carbohydrates_g",
    "sugars_g",
    "protein_g",
    "sodium_mg",
    "salt_g",
}

DEFAULT_TOLERANCE = 0.05


def normalize_basis(basis: Optional[str]) -> str:
    """Standardizes serving basis strings across ground truth and engine output."""
    if not basis:
        return "unknown"
    b = str(basis).lower().strip().replace(" ", "_")
    if b in ("per_100g", "per_100_g", "100g", "/100g"):
        return "per_100g"
    if b in ("per_100ml", "per_100_ml", "100ml", "/100ml"):
        return "per_100ml"
    if b in ("per_serving", "serving", "per_portion", "portion"):
        return "per_serving"
    if b in ("per_piece", "per_biscuit", "per_bar"):
        return "per_piece"
    if b in ("front_only", "no_panel"):
        return "front_only"
    return b


def check_value_match(gt_val: Any, pred_val: Any, tol: float = DEFAULT_TOLERANCE) -> Tuple[bool, Optional[str]]:
    """Checks whether predicted nutrient value matches ground truth within tolerance."""
    if pred_val is None:
        return False, "missing"
    try:
        gv = float(gt_val)
        pv = float(pred_val)
    except (TypeError, ValueError):
        eq = str(gt_val).strip().lower() == str(pred_val).strip().lower()
        return eq, (None if eq else "type_or_string_mismatch")

    if abs(gv) <= 1e-6 and abs(pv) <= 1e-6:
        return True, None
    if abs(gv) <= 1e-6 and abs(pv) > 1e-6:
        return False, f"expected_zero_got_{pv}"
    if abs(gv) > 1e-6 and abs(pv) <= 1e-6:
        return False, "predicted_zero"

    # Unit slip check (e.g., mg vs g conversion slip by x1000)
    if gv > 0 and pv > 0 and max(gv / pv, pv / gv) >= 900:
        return False, f"unit_slip_x1000 (gt={gv}, pred={pv})"

    rel_err = abs(pv - gv) / abs(gv)
    if rel_err <= tol:
        return True, None
    return False, f"rel_err_{rel_err:.2%}_(gt={gv}, pred={pv})"


def get_git_info() -> Dict[str, Any]:
    """Retrieves current Git commit hash and dirty status."""
    git_info: Dict[str, Any] = {
        "commit_hash": "unknown",
        "commit_short": "unknown",
        "branch": "unknown",
        "is_dirty": True,
        "dirty_files": [],
    }
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        git_info["commit_hash"] = commit
        git_info["commit_short"] = commit[:7]
    except Exception:
        pass
    try:
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT, text=True).strip()
        git_info["branch"] = branch
    except Exception:
        pass
    try:
        status = subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True).strip()
        lines = [l for l in status.splitlines() if l.strip()]
        git_info["is_dirty"] = len(lines) > 0
        git_info["dirty_files"] = lines
    except Exception:
        pass
    return git_info


def get_environment_info() -> Dict[str, Any]:
    """Collects system, hardware, and package environment details."""
    proc = psutil.Process()
    ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
    packages = {}
    for pkg in ("paddlepaddle", "paddleocr", "paddlex", "opencv-python", "pillow", "numpy", "pytest", "jsonschema"):
        try:
            import importlib.metadata
            packages[pkg] = importlib.metadata.version(pkg)
        except Exception:
            packages[pkg] = "not_installed"

    return {
        "os": platform.platform(),
        "python_version": sys.version.split()[0],
        "processor": platform.processor(),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "total_ram_gb": ram_gb,
        "packages": packages,
        "initial_rss_mb": round(proc.memory_info().rss / (1024 * 1024), 2),
    }


def evaluate_benchmark(
    sample_ids: Optional[List[str]] = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Dict[str, Any]:
    """Executes the full pipeline benchmark on packaging photographs."""
    gt_path = REPO_ROOT / "tests" / "fixtures" / "real_photos" / "ground_truth_v2.json"
    photos_dir = REPO_ROOT / "tests" / "fixtures" / "real_photos"

    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file not found: {gt_path}")

    gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
    samples = gt_data.get("samples", [])
    if sample_ids:
        samples = [s for s in samples if s["sample_id"] in sample_ids]

    proc = psutil.Process()
    env_info = get_environment_info()
    git_info = get_git_info()

    # Initialize complete FoodIntelligenceEngine
    t_init_start = time.perf_counter()
    engine = FoodIntelligenceEngine(repo_root=REPO_ROOT, use_gpu=False)
    engine_init_sec = round(time.perf_counter() - t_init_start, 4)
    rss_post_init = round(proc.memory_info().rss / (1024 * 1024), 2)

    # Aggregators
    per_nutrient_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "tn": 0})
    per_sample_results: List[Dict[str, Any]] = []

    overall_tp = 0
    overall_fp = 0
    overall_fn = 0

    core_tp = 0
    core_fp = 0
    core_fn = 0

    perfect_samples = 0
    basis_correct_count = 0
    basis_total_count = 0
    empty_prediction_count = 0

    split_stats: Dict[str, Dict[str, int]] = {
        "dev": {"tp": 0, "fp": 0, "fn": 0, "total_gt": 0, "perfect": 0, "basis_ok": 0, "count": 0},
        "held_out": {"tp": 0, "fp": 0, "fn": 0, "total_gt": 0, "perfect": 0, "basis_ok": 0, "count": 0},
    }

    latencies: List[float] = []
    peak_rss_mb = rss_post_init

    print(f"\n[BENCHMARK] Starting evaluation across {len(samples)} real food packaging photographs...")
    print(f"[BENCHMARK] Git Commit: {git_info['commit_short']} (Dirty: {git_info['is_dirty']})")
    print(f"[BENCHMARK] Engine Init: {engine_init_sec:.2f}s | Post-Init RSS: {rss_post_init:.1f} MB\n")

    for idx, sample in enumerate(samples, 1):
        sid = sample["sample_id"]
        filename = sample["file_name"]
        split = sample.get("split", "dev")
        image_path = photos_dir / filename

        if not image_path.exists():
            print(f"[{idx:02d}/{len(samples)}] {sid}: Missing image file {filename}")
            continue

        gt_declared = sample.get("declared_nutrients_on_label", {})
        gt_basis = normalize_basis(sample.get("serving_basis"))
        verification_status = sample.get("verification_status", "panel_verified_exact")

        t0 = time.perf_counter()
        out = engine.process_image(image_path)
        elapsed_sec = round(time.perf_counter() - t0, 4)
        latencies.append(elapsed_sec)

        current_rss = round(proc.memory_info().rss / (1024 * 1024), 2)
        if current_rss > peak_rss_mb:
            peak_rss_mb = current_rss

        pred_nutrition = out.get("nutrition", {})
        pred_basis = normalize_basis(pred_nutrition.get("basis"))
        pred_nutrients_raw = pred_nutrition.get("nutrients", {})

        # Standardize predicted nutrients
        pred_canonical: Dict[str, Any] = {}
        for raw_k, item in pred_nutrients_raw.items():
            canon_k = CANONICAL_NUTRIENT_MAP.get(raw_k, raw_k)
            # Only consider values with declared status or non-null value from label
            if isinstance(item, dict) and item.get("value") is not None:
                # Retain the value (prefer declared label source over fallback if collision)
                if canon_k not in pred_canonical or item.get("status") == "declared":
                    pred_canonical[canon_k] = item.get("value")

        # Check empty prediction
        if not pred_canonical:
            empty_prediction_count += 1

        sample_tp = 0
        sample_fp = 0
        sample_fn = 0
        sample_details: Dict[str, Any] = {"fields": {}, "errors": []}

        # 1. Evaluate Ground Truth Declared Fields
        for gt_field, gt_val in gt_declared.items():
            canon_field = CANONICAL_NUTRIENT_MAP.get(gt_field, gt_field)
            if gt_val is None:
                # Genuinely unreadable / unknown in ground truth -> exclude from denominator
                continue

            pred_val = pred_canonical.get(canon_field)
            is_match, err_reason = check_value_match(gt_val, pred_val, tol=tolerance)

            is_core = canon_field in CORE_NUTRIENTS

            if is_match:
                sample_tp += 1
                overall_tp += 1
                per_nutrient_stats[canon_field]["tp"] += 1
                if is_core:
                    core_tp += 1
                sample_details["fields"][canon_field] = {
                    "status": "TP",
                    "gt": gt_val,
                    "pred": pred_val,
                }
            else:
                sample_fn += 1
                overall_fn += 1
                per_nutrient_stats[canon_field]["fn"] += 1
                if is_core:
                    core_fn += 1

                # If a wrong value was predicted, it also counts as an FP (incorrect prediction)
                if pred_val is not None:
                    sample_fp += 1
                    overall_fp += 1
                    per_nutrient_stats[canon_field]["fp"] += 1
                    if is_core:
                        core_fp += 1
                    sample_details["errors"].append({
                        "field": canon_field,
                        "type": "wrong_value",
                        "gt": gt_val,
                        "pred": pred_val,
                        "reason": err_reason,
                    })
                    sample_details["fields"][canon_field] = {
                        "status": "FN_WRONG",
                        "gt": gt_val,
                        "pred": pred_val,
                        "reason": err_reason,
                    }
                else:
                    sample_details["errors"].append({
                        "field": canon_field,
                        "type": "missing",
                        "gt": gt_val,
                        "pred": None,
                    })
                    sample_details["fields"][canon_field] = {
                        "status": "FN_MISSING",
                        "gt": gt_val,
                        "pred": None,
                    }

        # 2. Check for Spurious / Hallucinated Predicted Fields (not declared in GT)
        for pred_field, pred_val in pred_canonical.items():
            if pred_val is None:
                continue
            # Look up in gt_declared under any alias
            found_in_gt = any(
                CANONICAL_NUTRIENT_MAP.get(k, k) == pred_field and v is not None
                for k, v in gt_declared.items()
            )
            if not found_in_gt:
                # If panel was not legible / front only, or nutrient simply not declared
                sample_fp += 1
                overall_fp += 1
                per_nutrient_stats[pred_field]["fp"] += 1
                if pred_field in CORE_NUTRIENTS:
                    core_fp += 1
                sample_details["errors"].append({
                    "field": pred_field,
                    "type": "spurious_extra",
                    "gt": None,
                    "pred": pred_val,
                })
                sample_details["fields"][pred_field] = {
                    "status": "FP_SPURIOUS",
                    "gt": None,
                    "pred": pred_val,
                }

        # Basis match evaluation
        basis_match = False
        if gt_basis != "front_only" and gt_basis != "unknown":
            basis_total_count += 1
            if pred_basis == gt_basis:
                basis_correct_count += 1
                basis_match = True
            else:
                sample_details["errors"].append({
                    "field": "__serving_basis__",
                    "type": "basis_mismatch",
                    "gt": gt_basis,
                    "pred": pred_basis,
                })
        else:
            # front_only photos have no basis
            basis_match = (pred_basis in ("front_only", "unknown", None))

        # Perfect sample criteria: all declared matched (0 FN), no spurious (0 FP), and basis matches
        declared_count = sum(1 for v in gt_declared.values() if v is not None)
        is_perfect = (sample_fn == 0 and sample_fp == 0 and basis_match and declared_count > 0)
        if is_perfect:
            perfect_samples += 1

        # Split tracking
        if split in split_stats:
            split_stats[split]["count"] += 1
            split_stats[split]["tp"] += sample_tp
            split_stats[split]["fp"] += sample_fp
            split_stats[split]["fn"] += sample_fn
            split_stats[split]["total_gt"] += declared_count
            if is_perfect:
                split_stats[split]["perfect"] += 1
            if basis_match and gt_basis not in ("front_only", "unknown"):
                split_stats[split]["basis_ok"] += 1

        sample_record = {
            "sample_id": sid,
            "filename": filename,
            "split": split,
            "product_name": sample.get("product_name"),
            "verification_status": verification_status,
            "elapsed_sec": elapsed_sec,
            "rss_mb": current_rss,
            "serving_basis": {"gt": gt_basis, "pred": pred_basis, "match": basis_match},
            "metrics": {
                "tp": sample_tp,
                "fp": sample_fp,
                "fn": sample_fn,
                "declared_gt_fields": declared_count,
                "precision": round(sample_tp / (sample_tp + sample_fp), 4) if (sample_tp + sample_fp) else 0.0,
                "recall": round(sample_tp / (sample_tp + sample_fn), 4) if (sample_tp + sample_fn) else 0.0,
                "is_perfect": is_perfect,
            },
            "details": sample_details,
        }
        per_sample_results.append(sample_record)

        print(
            f"[{idx:02d}/{len(samples)}] {sid} ({split:8s}): "
            f"TP={sample_tp:2d} FP={sample_fp:2d} FN={sample_fn:2d} "
            f"({sample_record['metrics']['recall']*100:5.1f}% recall) "
            f"Basis={'OK' if basis_match else 'ERR'} in {elapsed_sec:5.1f}s (RSS: {current_rss:6.1f}MB)"
        )

    # Aggregate metric calculations
    total_gt_declared = overall_tp + overall_fn
    overall_prec = round(overall_tp / (overall_tp + overall_fp), 4) if (overall_tp + overall_fp) else 0.0
    overall_rec = round(overall_tp / (overall_tp + overall_fn), 4) if (overall_tp + overall_fn) else 0.0
    overall_f1 = round(2 * overall_prec * overall_rec / (overall_prec + overall_rec), 4) if (overall_prec + overall_rec) else 0.0

    core_gt_total = core_tp + core_fn
    core_prec = round(core_tp / (core_tp + core_fp), 4) if (core_tp + core_fp) else 0.0
    core_rec = round(core_tp / (core_tp + core_fn), 4) if (core_tp + core_fn) else 0.0
    core_f1 = round(2 * core_prec * core_rec / (core_prec + core_rec), 4) if (core_prec + core_rec) else 0.0

    basis_acc = round(basis_correct_count / basis_total_count, 4) if basis_total_count else 0.0
    packet_acc = round(perfect_samples / len(samples), 4) if samples else 0.0

    # Per-nutrient precision / recall
    nutrient_table = {}
    for nut, s in sorted(per_nutrient_stats.items()):
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        p = round(tp / (tp + fp), 4) if (tp + fp) else 0.0
        r = round(tp / (tp + fn), 4) if (tp + fn) else 0.0
        f = round(2 * p * r / (p + r), 4) if (p + r) else 0.0
        nutrient_table[nut] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": p,
            "recall": r,
            "f1": f,
            "is_core": nut in CORE_NUTRIENTS,
        }

    # Macro metrics across nutrients with GT declarations
    active_nuts = [v for v in nutrient_table.values() if (v["tp"] + v["fn"]) > 0]
    macro_p = round(sum(v["precision"] for v in active_nuts) / len(active_nuts), 4) if active_nuts else 0.0
    macro_r = round(sum(v["recall"] for v in active_nuts) / len(active_nuts), 4) if active_nuts else 0.0
    macro_f1 = round(sum(v["f1"] for v in active_nuts) / len(active_nuts), 4) if active_nuts else 0.0

    # Latency statistics
    lat_sorted = sorted(latencies)
    median_lat = round(lat_sorted[len(lat_sorted) // 2], 4) if lat_sorted else 0.0
    mean_lat = round(sum(lat_sorted) / len(lat_sorted), 4) if lat_sorted else 0.0
    p95_lat = round(lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))], 4) if lat_sorted else 0.0

    benchmark_summary = {
        "benchmark_name": "Food Intelligence Engine - Phase 4 Reproducible Benchmark",
        "benchmark_type": "development_benchmark",
        "audit_note": "This is a DEVELOPMENT benchmark on existing samples, NOT an independent holdout result.",
        "timestamp": datetime.now().isoformat(),
        "git": git_info,
        "environment": env_info,
        "parameters": {
            "relative_numeric_tolerance": tolerance,
            "ground_truth_file": str(gt_path.relative_to(REPO_ROOT)),
            "engine_init_sec": engine_init_sec,
        },
        "sample_counts": {
            "total_evaluated_samples": len(samples),
            "perfect_samples_100_percent_correct": perfect_samples,
            "sample_level_accuracy": packet_acc,
            "empty_prediction_count": empty_prediction_count,
        },
        "overall_field_metrics": {
            "total_ground_truth_declared_fields": total_gt_declared,
            "true_positives": overall_tp,
            "false_positives": overall_fp,
            "false_negatives": overall_fn,
            "field_precision": overall_prec,
            "field_recall": overall_rec,
            "field_f1": overall_f1,
            "macro_precision": macro_p,
            "macro_recall": macro_r,
            "macro_f1": macro_f1,
        },
        "core_nutrient_subset_metrics": {
            "core_nutrients_defined": sorted(list(CORE_NUTRIENTS)),
            "total_core_ground_truth_fields": core_gt_total,
            "true_positives": core_tp,
            "false_positives": core_fp,
            "false_negatives": core_fn,
            "core_field_precision": core_prec,
            "core_field_recall": core_rec,
            "core_field_f1": core_f1,
        },
        "serving_basis_metrics": {
            "evaluated_basis_samples": basis_total_count,
            "correct_basis_count": basis_correct_count,
            "basis_accuracy": basis_acc,
        },
        "latency_sec": {
            "mean": mean_lat,
            "median": median_lat,
            "p95": p95_lat,
            "min": round(lat_sorted[0], 4) if lat_sorted else 0.0,
            "max": round(lat_sorted[-1], 4) if lat_sorted else 0.0,
            "total_elapsed_all_images": round(sum(lat_sorted), 2),
        },
        "memory_mb": {
            "initial_rss": env_info["initial_rss_mb"],
            "post_engine_init_rss": rss_post_init,
            "peak_rss_during_benchmark": peak_rss_mb,
        },
        "splits_breakdown": {
            "dev": {
                "sample_count": split_stats["dev"]["count"],
                "total_gt_fields": split_stats["dev"]["total_gt"],
                "tp": split_stats["dev"]["tp"],
                "fp": split_stats["dev"]["fp"],
                "fn": split_stats["dev"]["fn"],
                "recall": round(split_stats["dev"]["tp"] / split_stats["dev"]["total_gt"], 4) if split_stats["dev"]["total_gt"] else 0.0,
                "precision": round(split_stats["dev"]["tp"] / (split_stats["dev"]["tp"] + split_stats["dev"]["fp"]), 4) if (split_stats["dev"]["tp"] + split_stats["dev"]["fp"]) else 0.0,
                "perfect_packets": split_stats["dev"]["perfect"],
                "basis_accuracy": round(split_stats["dev"]["basis_ok"] / split_stats["dev"]["count"], 4) if split_stats["dev"]["count"] else 0.0,
            },
            "held_out_inspected": {
                "note": "Previously inspected during development; reported for historical tracking.",
                "sample_count": split_stats["held_out"]["count"],
                "total_gt_fields": split_stats["held_out"]["total_gt"],
                "tp": split_stats["held_out"]["tp"],
                "fp": split_stats["held_out"]["fp"],
                "fn": split_stats["held_out"]["fn"],
                "recall": round(split_stats["held_out"]["tp"] / split_stats["held_out"]["total_gt"], 4) if split_stats["held_out"]["total_gt"] else 0.0,
                "precision": round(split_stats["held_out"]["tp"] / (split_stats["held_out"]["tp"] + split_stats["held_out"]["fp"]), 4) if (split_stats["held_out"]["tp"] + split_stats["held_out"]["fp"]) else 0.0,
                "perfect_packets": split_stats["held_out"]["perfect"],
                "basis_accuracy": round(split_stats["held_out"]["basis_ok"] / split_stats["held_out"]["count"], 4) if split_stats["held_out"]["count"] else 0.0,
            },
        },
        "per_nutrient_metrics": nutrient_table,
        "per_sample_results": per_sample_results,
    }

    return benchmark_summary


def generate_markdown_report(data: Dict[str, Any], output_path: Path) -> str:
    """Generates an executive Markdown report from the benchmark data."""
    git = data["git"]
    env = data["environment"]
    ov = data["overall_field_metrics"]
    co = data["core_nutrient_subset_metrics"]
    lat = data["latency_sec"]
    mem = data["memory_mb"]
    basis = data["serving_basis_metrics"]
    cnt = data["sample_counts"]
    splits = data["splits_breakdown"]

    lines = [
        "# Food Intelligence Engine — Phase 4 Reproducible Benchmark Report",
        "",
        f"- **Evaluation Date**: `{data['timestamp']}`",
        f"- **Benchmark Type**: `{data['benchmark_type']}` ({data['audit_note']})",
        f"- **Git Commit**: `{git['commit_short']}` (Branch: `{git['branch']}` | Dirty: `{git['is_dirty']}`)",
        f"- **Environment**: Python `{env['python_version']}` on `{env['os']}` | RAM: `{env['total_ram_gb']} GB`",
        f"- **Engine Mode**: Full-pipeline `FoodIntelligenceEngine.process_image` (Deskew + 1.5x Upscale Rescue + Structured)",
        "",
        "---",
        "",
        "## 1. Executive Summary & Headline Metrics",
        "",
        "| Metric Name | Value | Evaluation Details & Mathematical Definition |",
        "|---|---|---|",
        f"| **Overall Field Recall** | **{ov['field_recall']*100:.1f}%** | ${ov['true_positives']} / {ov['total_ground_truth_declared_fields']}$ declared fields correctly matched within 5% tolerance |",
        f"| **Overall Field Precision** | **{ov['field_precision']*100:.1f}%** | ${ov['true_positives']} / ({ov['true_positives']} + {ov['false_positives']})$ extracted values that were correct |",
        f"| **Overall Field F1 Score** | **{ov['field_f1']:.4f}** | Harmonic mean of field precision and field recall |",
        f"| **Core Nutrient Recall** | **{co['core_field_recall']*100:.1f}%** | ${co['true_positives']} / {co['total_core_ground_truth_fields']}$ core nutrients (Energy, Fat, Carbs, Sugars, Protein, Sodium, Salt) |",
        f"| **Core Nutrient Precision** | **{co['core_field_precision']*100:.1f}%** | ${co['true_positives']} / ({co['true_positives']} + {co['false_positives']})$ core extractions that were correct |",
        f"| **Serving Basis Accuracy** | **{basis['basis_accuracy']*100:.1f}%** | ${basis['correct_basis_count']} / {basis['evaluated_basis_samples']}$ packages where detected basis matched ground truth |",
        f"| **Packet-Level Perfect Accuracy** | **{cnt['sample_level_accuracy']*100:.1f}%** | **{cnt['perfect_samples_100_percent_correct']} / {cnt['total_evaluated_samples']}** packets with 100% fields correct, zero false positives, and basis match |",
        f"| **Mean Latency per Image** | **{lat['mean']:.2f} s** | CPU execution (Median: {lat['median']:.2f}s, Min: {lat['min']:.2f}s, Max: {lat['max']:.2f}s) |",
        f"| **Peak Working Set Memory** | **{mem['peak_rss_during_benchmark']:.1f} MB** | Peak process memory observed during high-resolution multi-scale OCR |",
        "",
        "---",
        "",
        "## 2. Dev vs. Historical 'Held-Out' Split Comparison",
        "",
        "> [!IMPORTANT]",
        "> **Provenance Warning**: As established in the independent audit, the 'held-out' split of 7 images was previously inspected during exploratory debugging. It is reported below strictly for historical continuity and must **not** be presented as an independent validation set.",
        "",
        "| Split Group | Sample Count | Total Declared Fields | TP | FP | FN | Field Recall | Field Precision | Perfect Packets | Basis Accuracy |",
        "|---|---|---|---|---|---|---|---|---|---|",
        f"| **Dev Split** | {splits['dev']['sample_count']} | {splits['dev']['total_gt_fields']} | {splits['dev']['tp']} | {splits['dev']['fp']} | {splits['dev']['fn']} | **{splits['dev']['recall']*100:.1f}%** | {splits['dev']['precision']*100:.1f}% | {splits['dev']['perfect_packets']} / {splits['dev']['sample_count']} | {splits['dev']['basis_accuracy']*100:.1f}% |",
        f"| **Inspected 'Held-Out' Split** | {splits['held_out_inspected']['sample_count']} | {splits['held_out_inspected']['total_gt_fields']} | {splits['held_out_inspected']['tp']} | {splits['held_out_inspected']['fp']} | {splits['held_out_inspected']['fn']} | **{splits['held_out_inspected']['recall']*100:.1f}%** | {splits['held_out_inspected']['precision']*100:.1f}% | {splits['held_out_inspected']['perfect_packets']} / {splits['held_out_inspected']['sample_count']} | {splits['held_out_inspected']['basis_accuracy']*100:.1f}% |",
        "",
        "---",
        "",
        "## 3. Per-Nutrient Precision & Recall Breakdown",
        "",
        "| Nutrient Field | Core? | GT Declared | TP | FP | FN | Precision | Recall | F1 Score |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for nut, s in sorted(data["per_nutrient_metrics"].items()):
        gt_count = s["tp"] + s["fn"]
        core_mark = "Yes" if s["is_core"] else "No"
        lines.append(
            f"| `{nut}` | {core_mark} | {gt_count} | {s['tp']} | {s['fp']} | {s['fn']} | "
            f"{s['precision']*100:.1f}% | {s['recall']*100:.1f}% | {s['f1']:.4f} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 4. Case-by-Case Sample Results",
        "",
        "| ID | Split | Product Name | Time (s) | Memory (MB) | Basis (Pred / GT) | Declared | TP | FP | FN | Recall | Perfect? |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ])

    for r in data["per_sample_results"]:
        m = r["metrics"]
        b = r["serving_basis"]
        perf = "Yes" if m["is_perfect"] else "No"
        pname = r["product_name"][:25] if r["product_name"] else "Unknown"
        lines.append(
            f"| `{r['sample_id']}` | {r['split']} | {pname} | {r['elapsed_sec']:.1f} | {r['rss_mb']:.0f} | "
            f"`{b['pred']}` / `{b['gt']}` | {m['declared_gt_fields']} | {m['tp']} | {m['fp']} | {m['fn']} | "
            f"{m['recall']*100:.1f}% | {perf} |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 5. Metric Definitions & Formulas",
        "",
        r"1. **True Positive ($TP$)**: Predicted value $\hat{v}$ matches ground-truth declared value $v$ within relative tolerance: $|\hat{v} - v| / |v| \le 0.05$ (or absolute difference $\le 10^{-6}$ when $v=0$).",
        "2. **False Negative ($FN$)**: Ground truth declares value $v$, but the engine either produced $None$ (missing) or a value outside the 5% tolerance.",
        "3. **False Positive ($FP$)**: Engine produced a numeric prediction that was either incorrect for a declared field ($|\\hat{v} - v| / |v| > 0.05$) or predicted a nutrient not declared on the physical packaging.",
        "4. **Field Recall**: $\\frac{TP}{TP + FN}$ across all declared non-null ground-truth fields.",
        "5. **Field Precision**: $\\frac{TP}{TP + FP}$ across all extracted candidate values.",
        "6. **Perfect Packet Accuracy**: Percentage of food packages where all declared nutrients are correctly extracted with zero false negatives, zero false positives, and an exact serving basis match.",
        "",
    ])

    content = "\n".join(lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reproducible full-pipeline benchmark.")
    parser.add_argument("--ids", nargs="*", help="Optional sample IDs to evaluate.")
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE, help="Relative error tolerance.")
    parser.add_argument("--out-json", default="reports/evaluation/full_pipeline_benchmark_v3.json", help="Path to output JSON.")
    parser.add_argument("--out-md", default="reports/evaluation/full_pipeline_benchmark_v3.md", help="Path to output Markdown.")
    args = parser.parse_args()

    out_json_path = REPO_ROOT / args.out_json
    out_md_path = REPO_ROOT / args.out_md

    results = evaluate_benchmark(sample_ids=args.ids, tolerance=args.tolerance)

    out_json_path.parent.mkdir(parents=True, exist_ok=True)
    out_json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[BENCHMARK] Wrote JSON report to: {out_json_path}")

    generate_markdown_report(results, out_md_path)
    print(f"[BENCHMARK] Wrote Markdown report to: {out_md_path}")

    print("\n" + "=" * 80)
    print("                    BENCHMARK EXECUTION COMPLETE")
    print("=" * 80)
    print(f"  Total Evaluated Samples:       {results['sample_counts']['total_evaluated_samples']}")
    print(f"  Field Recall:                  {results['overall_field_metrics']['field_recall']*100:.1f}% ({results['overall_field_metrics']['true_positives']}/{results['overall_field_metrics']['total_ground_truth_declared_fields']})")
    print(f"  Field Precision:               {results['overall_field_metrics']['field_precision']*100:.1f}% ({results['overall_field_metrics']['true_positives']}/{results['overall_field_metrics']['true_positives'] + results['overall_field_metrics']['false_positives']})")
    print(f"  Core Nutrient Recall:          {results['core_nutrient_subset_metrics']['core_field_recall']*100:.1f}% ({results['core_nutrient_subset_metrics']['true_positives']}/{results['core_nutrient_subset_metrics']['total_core_ground_truth_fields']})")
    print(f"  Serving Basis Accuracy:        {results['serving_basis_metrics']['basis_accuracy']*100:.1f}% ({results['serving_basis_metrics']['correct_basis_count']}/{results['serving_basis_metrics']['evaluated_basis_samples']})")
    print(f"  Sample-Level Perfect Accuracy: {results['sample_counts']['sample_level_accuracy']*100:.1f}% ({results['sample_counts']['perfect_samples_100_percent_correct']}/{results['sample_counts']['total_evaluated_samples']})")
    print(f"  Mean Latency:                  {results['latency_sec']['mean']:.2f} s/image (Median: {results['latency_sec']['median']:.2f} s)")
    print(f"  Peak Working Set Memory:       {results['memory_mb']['peak_rss_during_benchmark']:.1f} MB")
    print("=" * 80 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
