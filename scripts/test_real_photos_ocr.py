"""Real Food-Label OCR Benchmark on Genuine Package Photographs.

Evaluates PaddleOCR PP-OCRv4 against 22 real packaging photographs with ground truth.
Computes:
- Character Error Rate (CER)
- Word Error Rate (WER)
- Nutrition field extraction accuracy
- Latency (initialization vs per-image inference)
- Whole-process memory working set (initial, post-init, peak)
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
import psutil

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.ocr.ocr_engine import OCREngine
from food_engine.nutrition_extraction.extractor import NutritionExtractor


def levenshtein_chars(s1: str, s2: str) -> int:
    """Computes Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_chars(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (c1 != c2)
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


def levenshtein_tokens(r_tokens: List[str], h_tokens: List[str]) -> int:
    """Computes Levenshtein edit distance over sequences of words."""
    if len(r_tokens) < len(h_tokens):
        return levenshtein_tokens(h_tokens, r_tokens)
    if len(h_tokens) == 0:
        return len(r_tokens)
    prev = list(range(len(h_tokens) + 1))
    for i, t1 in enumerate(r_tokens):
        curr = [i + 1]
        for j, t2 in enumerate(h_tokens):
            ins = prev[j + 1] + 1
            dels = curr[j] + 1
            subs = prev[j] + (t1.lower() != t2.lower())
            curr.append(min(ins, dels, subs))
        prev = curr
    return prev[-1]


def run_benchmark():
    proc = psutil.Process(os.getpid())
    init_mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)

    gt_path = REPO_ROOT / "tests" / "fixtures" / "real_photos" / "ground_truth.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth file missing at {gt_path}")

    dataset = json.loads(gt_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(dataset)} real food photo test cases.")

    print("\n[Step 1/3] Initializing Genuine OCR Engine...")
    t_init_start = time.time()
    ocr = OCREngine(repo_root=REPO_ROOT, require_real_ocr=True)
    init_time_sec = round(time.time() - t_init_start, 4)
    post_init_mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    print(f"OCR Engine: {ocr._engine_type} initialized in {init_time_sec:.3f} s.")
    print(f"Memory: Initial {init_mem_mb} MB -> Post-Init {post_init_mem_mb} MB (+{post_init_mem_mb - init_mem_mb:.1f} MB)")

    results: List[Dict[str, Any]] = []
    latencies: List[float] = []

    field_tp = 0
    field_fp = 0
    field_fn = 0
    total_expected_fields = 0

    print("\n[Step 2/3] Processing Real Food Packaging Photographs...")
    print("-" * 90)

    for idx, item in enumerate(dataset, 1):
        filename = item["file_name"]
        filepath = REPO_ROOT / "tests" / "fixtures" / "real_photos" / filename
        name = item["product_name"]
        pkg = item["package_type"]

        if not filepath.exists():
            print(f"[{idx:02d}] Missing file: {filename}")
            continue

        t0 = time.time()
        ocr_out = ocr.run_ocr(filepath)
        infer_time = time.time() - t0
        latencies.append(infer_time)

        lines = [l["text"] for l in ocr_out.get("lines", [])]
        joined_ocr = " ".join(lines).strip()
        ocr_words = [w for w in joined_ocr.split() if w]

        # Extract nutrition table from OCR lines using our production extractor
        extracted = NutritionExtractor.extract(lines)
        ext_nutrients = extracted.get("nutrients", {})

        # Compare with ground truth
        gt = item.get("ground_truth", {})
        gt_nutrients = gt.get("declared_nutrients_on_label") or gt.get("nutrients_per_100g", {})
        gt_visible_text = gt.get("visible_label_text") or gt.get("ingredients_text", "")

        # Compute CER and WER against reference visible text if present
        cer = None
        wer = None
        if gt_visible_text and len(gt_visible_text) > 10:
            clean_gt_text = " ".join(gt_visible_text.split()).strip()
            gt_words = [w for w in clean_gt_text.split() if w]
            # Character error rate
            char_dist = levenshtein_chars(clean_gt_text, joined_ocr)
            cer = round(char_dist / max(1, len(clean_gt_text)), 4)
            # Word error rate
            word_dist = levenshtein_tokens(gt_words, ocr_words)
            wer = round(word_dist / max(1, len(gt_words)), 4)

        # Evaluate nutrition field matches
        matched_fields = {}
        for field, gt_val in gt_nutrients.items():
            if gt_val is not None:
                total_expected_fields += 1
                rec_entry = ext_nutrients.get(field)
                if rec_entry is None or (isinstance(rec_entry, dict) and rec_entry.get("value") is None):
                    # Check common field aliases
                    if field in ("fat_g", "total_fat_g"):
                        rec_entry = ext_nutrients.get("total_fat_g") or ext_nutrients.get("fat_g")
                    elif field in ("fiber_g", "dietary_fibre_g"):
                        rec_entry = ext_nutrients.get("dietary_fibre_g") or ext_nutrients.get("fiber_g")

                rec_val = rec_entry.get("value") if isinstance(rec_entry, dict) else rec_entry
                if rec_val is not None:
                    # Allow 20% relative difference or absolute tolerance for small values
                    is_match = False
                    try:
                        rec_float = float(rec_val)
                        gt_float = float(gt_val)
                        if gt_float == 0.0:
                            is_match = abs(rec_float - gt_float) < 0.5
                        elif gt_float < 5.0:
                            is_match = abs(rec_float - gt_float) <= 1.0
                        else:
                            rel_diff = abs(rec_float - gt_float) / gt_float
                            is_match = rel_diff <= 0.20
                    except Exception:
                        is_match = False

                    if is_match:
                        field_tp += 1
                        matched_fields[field] = {"status": "match", "gt": gt_val, "ocr": rec_val}
                    else:
                        field_fp += 1
                        matched_fields[field] = {"status": "mismatch", "gt": gt_val, "ocr": rec_val}
                else:
                    field_fn += 1
                    matched_fields[field] = {"status": "missing_in_ocr", "gt": gt_val, "ocr": None}

        case_summary = {
            "sample_id": item["sample_id"],
            "filename": filename,
            "product_name": name,
            "package_type": pkg,
            "visual_conditions": item.get("visual_conditions", ""),
            "dimensions": item.get("image_dimensions", {}),
            "line_count": len(lines),
            "inference_time_sec": round(infer_time, 4),
            "mean_confidence": round(float(sum(l["confidence"] for l in ocr_out.get("lines", [])) / max(1, len(lines))), 4) if lines else 0.0,
            "cer": cer,
            "wer": wer,
            "matched_nutrient_fields": matched_fields,
            "first_3_lines": lines[:3],
        }
        results.append(case_summary)

        print(f"[{idx:02d}/22] {name[:30]:<30} | {pkg:<16} | lines: {len(lines):<3} | time: {infer_time:.2f}s | CER: {str(cer):<6} | WER: {str(wer):<6}")

    post_infer_mem_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    peak_mem_mb = round(proc.memory_info().peak_wset / (1024 * 1024), 2) if hasattr(proc.memory_info(), "peak_wset") else post_infer_mem_mb

    # Summary metrics
    valid_cers = [r["cer"] for r in results if r["cer"] is not None]
    valid_wers = [r["wer"] for r in results if r["wer"] is not None]
    mean_cer = round(sum(valid_cers) / len(valid_cers), 4) if valid_cers else None
    mean_wer = round(sum(valid_wers) / len(valid_wers), 4) if valid_wers else None

    import numpy as np
    median_cer = round(float(np.median(valid_cers)), 4) if valid_cers else None
    median_wer = round(float(np.median(valid_wers)), 4) if valid_wers else None

    field_precision = round(field_tp / max(1, field_tp + field_fp), 4)
    field_recall = round(field_tp / max(1, field_tp + field_fn), 4)
    field_accuracy = round(field_tp / max(1, total_expected_fields), 4)

    summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine_type": ocr._engine_type,
        "model_version": "PP-OCRv4-mobile",
        "device": "cpu",
        "sample_count": len(results),
        "performance": {
            "model_init_time_sec": init_time_sec,
            "per_image_latency_sec": {
                "mean": round(float(np.mean(latencies)), 4),
                "median": round(float(np.median(latencies)), 4),
                "min": round(float(np.min(latencies)), 4),
                "max": round(float(np.max(latencies)), 4),
                "std": round(float(np.std(latencies)), 4),
            },
            "memory_usage_mb": {
                "initial_working_set": init_mem_mb,
                "post_init_working_set": post_init_mem_mb,
                "post_inference_working_set": post_infer_mem_mb,
                "peak_working_set": peak_mem_mb,
            }
        },
        "accuracy_metrics": {
            "evaluated_samples_with_text": len(valid_cers),
            "character_error_rate": {
                "mean": mean_cer,
                "median": median_cer,
            },
            "word_error_rate": {
                "mean": mean_wer,
                "median": median_wer,
            },
            "nutrition_field_extraction": {
                "total_ground_truth_fields": total_expected_fields,
                "true_positives": field_tp,
                "false_positives": field_fp,
                "false_negatives": field_fn,
                "precision": field_precision,
                "recall": field_recall,
                "field_accuracy": field_accuracy,
            }
        },
        "detailed_results": results,
    }

    out_file = REPO_ROOT / "reports" / "evaluation" / "real_photos_ocr_benchmark.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 90)
    print("BENCHMARK SUMMARY RESULTS:")
    print(f"Total Photographs Evaluated: {len(results)}")
    print(f"Model Init Time:             {init_time_sec:.3f} s")
    print(f"Mean Per-Image Latency:      {summary['performance']['per_image_latency_sec']['mean']:.3f} s")
    print(f"Median Per-Image Latency:    {summary['performance']['per_image_latency_sec']['median']:.3f} s")
    print(f"Process Peak Working Set:    {peak_mem_mb} MB")
    print(f"Mean Character Error Rate:   {mean_cer}")
    print(f"Median Character Error Rate: {median_cer}")
    print(f"Mean Word Error Rate:        {mean_wer}")
    print(f"Median Word Error Rate:      {median_wer}")
    print(f"Nutrition Field Recall:      {field_recall * 100:.1f}% ({field_tp}/{total_expected_fields})")
    print(f"Nutrition Field Precision:   {field_precision * 100:.1f}%")
    print(f"Results saved to:            {out_file}")
    print("=" * 90)

    return summary


if __name__ == "__main__":
    run_benchmark()
