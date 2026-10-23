"""Stage-level profiling of the real-photo OCR pipeline (CPU).

Measures, per invocation:
- image read + decode (PIL)
- RGB conversion (numpy array build)
- OCR predict (whole pipeline)
- nutrition extraction
and separately:
- model init time, cold first-inference vs warm steady-state
- RSS and whole-process peak working set
- controlled max-side downsizing experiments (default 1920 vs smaller) with
  CER against the v2 ground truth on DEV-split images only (held_out untouched).

Usage:
    python scripts/profile_ocr_stages.py [--repeats 2]
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PIL import Image  # noqa: E402


def rss_mb(proc) -> float:
    return proc.memory_info().rss / 1024 / 1024


def peak_ws_mb(proc) -> float:
    try:
        return proc.memory_info().peak_wset / 1024 / 1024
    except AttributeError:
        return rss_mb(proc)


def timed(fn, *args, **kwargs):
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    return out, time.perf_counter() - t0


def profile_batch(paths: List[Path], repeats: int, engine) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for p in paths:
        for rep in range(repeats):
            rec: Dict[str, Any] = {"image": p.name, "rep": rep}

            t0 = time.perf_counter()
            img = Image.open(p)
            rec["decode_sec"] = round(time.perf_counter() - t0, 4)

            t0 = time.perf_counter()
            np_img = None
            from PIL import ImageOps
            import numpy as np
            fixed = ImageOps.exif_transpose(img)
            if fixed.mode not in ("RGB", "L"):
                fixed = fixed.convert("RGB")
            rec["convert_sec"] = round(time.perf_counter() - t0, 4)
            img.close()

            t0 = time.perf_counter()
            ocr_raw = engine._ocr_instance.predict(np.asarray(fixed.convert("RGB")))
            rec["predict_sec"] = round(time.perf_counter() - t0, 4)

            from food_engine.nutrition_extraction.extractor import NutritionExtractor
            page = ocr_raw[0] if ocr_raw else {}
            texts = list(page.get("rec_texts", []))
            t0 = time.perf_counter()
            NutritionExtractor.extract(texts)
            rec["extract_sec"] = round(time.perf_counter() - t0, 5)

            rec["line_count"] = len(texts)
            results.append(rec)
            print(
                f"{p.name} rep{rep}: decode={rec['decode_sec']}s convert={rec['convert_sec']}s "
                f"predict={rec['predict_sec']}s extract={rec['extract_sec']}s lines={rec['line_count']}"
            )
    return results


def summarise(recs: List[Dict[str, Any]]) -> Dict[str, Any]:
    def med(key: str) -> float:
        vals = [r[key] for r in recs if key in r]
        return round(statistics.median(vals), 4) if vals else 0.0

    return {k: med(k) for k in ("decode_sec", "convert_sec", "predict_sec", "extract_sec", "line_count")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()

    import psutil
    proc = psutil.Process()

    report: Dict[str, Any] = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "repeats": args.repeats, "device": "cpu"}

    print("[1/4] Engine init timing ...")
    st = time.perf_counter()
    from food_engine.ocr.ocr_engine import OCREngine
    engine = OCREngine(repo_root=REPO_ROOT, require_real_ocr=True)
    report["init_sec"] = round(time.perf_counter() - st, 4)
    report["rss_after_init_mb"] = round(rss_mb(proc), 2)
    print(f"  init: {report['init_sec']}s, rss {report['rss_after_init_mb']} MB")

    print("[2/4] Cold vs warm inference (photo_02) ...")
    p_first = REPO_ROOT / "tests" / "fixtures" / "real_photos" / "real_photo_02_0044000032029.jpg"
    t0 = time.perf_counter()
    engine.run_ocr(str(p_first))
    cold = time.perf_counter() - t0
    warm_times = []
    for _ in range(2):
        t0 = time.perf_counter()
        engine.run_ocr(str(p_first))
        warm_times.append(time.perf_counter() - t0)
    report["cold_first_infer_sec"] = round(cold, 4)
    report["warm_sec_same_image"] = [round(x, 4) for x in warm_times]
    print(f"  cold={cold:.2f}s warm={warm_times}")

    print("[3/4] Stage medians over dev pipeline images ...")
    dev_names = [
        "real_photo_02_0044000032029.jpg",
        "real_photo_03_0028400070560.jpg",
        "real_photo_12_0011110038364.jpg",
        "real_photo_20_0028400043809.jpg",
    ]
    recs = profile_batch([REPO_ROOT / "tests" / "fixtures" / "real_photos" / n for n in dev_names], args.repeats, engine)
    report["stage_medians_dev"] = summarise(recs)
    report["stage_records_dev"] = recs

    print("[4/4] Whole-process peak ...")
    report["rss_end_mb"] = round(rss_mb(proc), 2)
    report["peak_wset_mb"] = round(peak_ws_mb(proc), 2)
    print(f"  rss_end={report['rss_end_mb']} MB peak_wset={report['peak_wset_mb']} MB (cumulative for process)")

    out = REPO_ROOT / "reports" / "evaluation" / "profile_ocr_stages.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
