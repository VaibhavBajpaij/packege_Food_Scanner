"""Benchmark v2 metrics: OCR text quality and nutrition-field extraction.

Uses ONLY:
- Full-line OCR output captured in the Phase 3 audit rerun (fresh inference,
  no thresholds or GT leveraging).
- ground_truth_v2.json (independent manual transcription).
- text_metrics (unit-tested independent CER/WER; not the historical rules).

Input : reports/evaluation/audit_rerun_v1.json
Output: reports/evaluation/real_photos_benchmark_v2.json
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.evaluate.text_metrics import (  # noqa: E402
    cer,
    coverage_cer,
    coverage_wer,
    normalise_for_cer,
    wer,
)
from food_engine.ocr.layout_assembly import row_group_lines  # noqa: E402
from food_engine.nutrition_extraction.extractor import NutritionExtractor  # noqa: E402

RERUN = REPO_ROOT / "reports/evaluation/audit_rerun_v1.json"
GT = REPO_ROOT / "tests/fixtures/real_photos/ground_truth_v2.json"
OUT = REPO_ROOT / "reports/evaluation/real_photos_benchmark_v2.json"

TOL = 0.05  # relative tolerance for numeric field match

# Map GT field name -> accepted extractor output keys (value or derived equal)
FIELD_ALIASES = {
    "energy_kcal": ["energy_kcal"],
    "energy_kj": ["energy_kj"],
    "protein_g": ["protein_g"],
    "carbohydrates_g": ["carbohydrates_g"],
    "sugars_g": ["sugars_g"],
    "fat_g": ["total_fat_g", "fat_g"],
    "saturated_fat_g": ["saturated_fat_g"],
    "fibre_g": ["fibre_g", "fiber_g"],
    "sodium_mg": ["sodium_mg"],
    "salt_g": ["salt_g"],
}


def value_matches(gt_v, pred_v):
    if pred_v is None:
        return False, "missing"
    try:
        pv = float(pred_v)
        gv = float(gt_v)
    except (TypeError, ValueError):
        return str(pred_v).strip().lower() == str(gt_v).strip().lower(), None
    if abs(pv) <= 1e-9 and abs(gv) <= 1e-9:
        return True, None
    # unit-error guard: an off-by-x1000 mg->g slip is much worse than tolerance
    if gv > 0 and pv > 0:
        if max(pv / gv, gv / pv) >= 900 and abs(pv - gv) > TOL * max(abs(pv), abs(gv)):
            return False, "unit_slip"
    rel = abs(pv - gv) / max(abs(gv), 1e-9)
    return rel <= TOL, None


def evaluate_split(rerun_samples, gt_by_id, sample_ids):
    cer_pairs, wer_pairs, cov_cer, cov_wer = [], [], [], []
    empty_gt = 0
    tp = {f: 0 for f in FIELD_ALIASES}
    fp = {f: 0 for f in FIELD_ALIASES}
    fn = {f: 0 for f in FIELD_ALIASES}
    basis_correct = 0
    basis_total = 0
    per_sample_field_errors = {}
    latencies = []
    for sid in sorted(sample_ids):
        gt = gt_by_id.get(sid)
        s = rerun_samples.get(sid)
        if gt is None or s is None:
            continue
        latencies.append(s.get("elapsed_sec", 0))
        gt_lines = gt.get("visible_label_lines") or []
        pred = " ".join(s.get("lines", []))
        ref = " ".join(gt_lines)
        if not ref.strip():
            empty_gt += 1
        else:
            if pred.strip():
                cer_pairs.append((cer(ref, pred), len(normalise_for_cer(ref))))
                wer_pairs.append((wer(ref, pred), max(1, len(normalise_for_cer(ref).split()))))
                cov_cer.append((coverage_cer(ref, pred), len(normalise_for_cer(ref))))
                cov_wer.append((coverage_wer(ref, pred), max(1, len(normalise_for_cer(ref).split()))))
            # CER with an empty prediction still counts (full miss)
            elif not pred.strip():
                cer_pairs.append((None, len(normalise_for_cer(ref))))
                wer_pairs.append((None, max(1, len(normalise_for_cer(ref).split()))))
                cov_cer.append((None, len(normalise_for_cer(ref))))
                cov_wer.append((None, max(1, len(normalise_for_cer(ref).split()))))
        # Field extraction: assembled rows -> extractor
        boxes = s.get("lines_with_boxes") or []
        if boxes:
            rows = [r["text"] for r in row_group_lines(boxes)]
        else:
            rows = list(s.get("lines", []))
        ex = NutritionExtractor.extract(rows)
        nuts = ex["nutrients"]
        errors = {}
        gt_nuts = gt.get("declared_nutrients_on_label") or {}
        for field, key_candidates in FIELD_ALIASES.items():
            if field not in gt_nuts:
                continue  # not declared on the label -> extractor should not report
            got = None
            for k in key_candidates:
                entry = nuts.get(k)
                if entry and entry.get("value") is not None:
                    got = (k, entry["value"])
                    break
            ok, err_kind = value_matches(gt_nuts[field], got[1] if got else None)
            if ok:
                tp[field] += 1
            else:
                fp[field] += 1
                fn[field] += 1
                errors[field] = {
                    "expected": gt_nuts[field],
                    "got": got[1] if got else None,
                    "via": got[0] if got else None,
                    "kind": err_kind or ("wrong_value" if got else "missing"),
                }
        if gt.get("serving_basis"):
            basis_total += 1
            if ex.get("basis") == gt["serving_basis"]:
                basis_correct += 1
                errors.pop("__basis__", None)
            else:
                errors["__basis__"] = {"expected": gt["serving_basis"], "got": ex.get("basis")}
        if errors:
            per_sample_field_errors[sid] = errors

    def agg_weighted(pairs):
        good = [(c, w) for c, w in pairs if c is not None]
        missing = len(pairs) - len(good)
        if not pairs:
            return None
        if not good:  # only empty predictions
            return None
        return {
            "weighted": sum(c * w for c, w in good) / sum(w for _, w in good) if sum(w for _, w in good) else None,
            "macro": sum(c for c, _ in good) / len(good),
            "empty_prediction_excluded": missing,
        }

    prec = {}
    rec = {}
    f1 = {}
    for f in FIELD_ALIASES:
        p = tp[f] / (tp[f] + fp[f]) if (tp[f] + fp[f]) else None
        r = tp[f] / (tp[f] + fn[f]) if (tp[f] + fn[f]) else None
        prec[f] = p
        rec[f] = r
        f1[f] = 2 * p * r / (p + r) if p and r else None

    macro_f1 = sum(f for f in f1.values() if f is not None) / sum(1 for f in f1.values() if f is not None)
    macro_recall = sum(r for r in rec.values() if r is not None) / sum(1 for r in rec.values() if r is not None)
    macro_prec = sum(p for p in prec.values() if p is not None) / sum(1 for p in prec.values() if p is not None)

    exact_all = sum(
        1 for sid in per_sample_field_errors if not any(k != "__basis__" for k in per_sample_field_errors[sid])
    )

    lat = sorted(latencies)
    def pct(arr, q):
        return arr[min(len(arr) - 1, int(q * len(arr)))] if arr else None

    return {
        "n_samples": len([sid for sid in sample_ids if sid in rerun_samples and sid in gt_by_id]),
        "cer": agg_weighted(cer_pairs),
        "wer": agg_weighted(wer_pairs),
        "coverage_cer": agg_weighted(cov_cer),
        "coverage_wer": agg_weighted(cov_wer),
        "empty_prediction_count": empty_gt,
        "per_field_precision": prec,
        "per_field_recall": rec,
        "per_field_f1": f1,
        "macro_precision": macro_prec,
        "macro_recall": macro_recall,
        "macro_f1": macro_f1,
        "samples_with_all_declared_fields_correct": exact_all,
        "basis_accuracy": basis_correct / basis_total if basis_total else None,
        "latency_sec": {"median": pct(lat, 0.5), "p95": pct(lat, 0.95)},
        "per_sample_field_errors": per_sample_field_errors,
    }


def main():
    rerun = json.loads(RERUN.read_text(encoding="utf-8"))
    gt = json.loads(GT.read_text(encoding="utf-8"))
    gt_by_id = {s["sample_id"]: s for s in gt["samples"]}

    samples = {}
    for sid, s in rerun["samples"].items():
        lines = s.get("recognized_lines") or s.get("lines") or []
        samples[sid] = {
            "elapsed_sec": s.get("elapsed_sec"),
            "lines": [l["text"] if isinstance(l, dict) else str(l) for l in lines],
            "lines_with_boxes": [l for l in lines if isinstance(l, dict) and l.get("bounding_box")],
        }

    dev_ids = [sid for sid, s in gt_by_id.items() if s.get("split") == "dev"]
    hold_ids = [sid for sid, s in gt_by_id.items() if s.get("split") == "held_out"]

    result = {
        "generated_by": "scripts/run_benchmark_v2_metrics.py",
        "inference_source": "reports/evaluation/audit_rerun_v1.json (single fresh inference pass, no thresholds)",
        "metrics_module": "src/food_engine/evaluate/text_metrics.py (independent, unit-tested)",
        "tolerance": TOL,
        "dev": evaluate_split(samples, gt_by_id, dev_ids),
        "held_out": evaluate_split(samples, gt_by_id, hold_ids),
    }
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
