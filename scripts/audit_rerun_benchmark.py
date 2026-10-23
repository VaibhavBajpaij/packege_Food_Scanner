"""One-pass audit rerun of the real-photo OCR benchmark.

Collects, for each sample: the COMPLETE raw OCR output (lines, confidences,
bounding boxes), engine identity, latencies and process memory, plus per-image
SHA-256. Results are stored raw so any metric (old or new protocol) can be
recomputed later without re-running inference.

Usage:
    python scripts/audit_rerun_benchmark.py --gt tests/fixtures/real_photos/ground_truth.json \
        --out reports/evaluation/audit_rerun_v1.json
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gt", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ids", nargs="*", help="Restrict to these sample_ids")
    args = parser.parse_args()

    gt_path = Path(args.gt)
    dataset = json.loads(gt_path.read_text(encoding="utf-8"))
    if args.ids:
        dataset = [d for d in dataset if d["sample_id"] in args.ids]
    print(f"{len(dataset)} samples from {gt_path}")

    try:
        import psutil
        proc = psutil.Process()
        rss0 = round(proc.memory_info().rss / 1024 / 1024, 2)
    except Exception:
        proc = None
        rss0 = None

    from food_engine.ocr.ocr_engine import OCREngine

    t0 = time.time()
    ocr = OCREngine(repo_root=REPO_ROOT, require_real_ocr=True)
    init_sec = round(time.time() - t0, 4)
    rss_post_init = round(proc.memory_info().rss / 1024 / 1024, 2) if proc else None

    import hashlib

    out: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "gt_file": str(gt_path),
        "engine": {
            "type": ocr._engine_type,
            "init_sec": init_sec,
            "confidence_threshold": ocr.confidence_threshold,
        },
        "memory_mb": {"rss_start": rss0, "rss_post_init": rss_post_init},
        "samples": {},
    }

    for i, item in enumerate(dataset, 1):
        sid = item["sample_id"]
        path = REPO_ROOT / "tests" / "fixtures" / "real_photos" / item["file_name"]
        if not path.exists():
            out["samples"][sid] = {"file": item["file_name"], "status": "missing_file"}
            continue

        t = time.time()
        res = ocr.run_ocr(str(path))
        dt = time.time() - t

        lines = res.get("lines", [])
        out["samples"][sid] = {
            "file": item["file_name"],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "status": res.get("status"),
            "error": res.get("error"),
            "elapsed_sec": round(dt, 4),
            "line_count": len(lines),
            "lines": [
                {
                    "text": l["text"],
                    "confidence": l["confidence"],
                    "box": l.get("bounding_box", []),
                }
                for l in lines
            ],
            "image_metadata": res.get("image_metadata", {}),
        }
        rss_now = round(proc.memory_info().rss / 1024 / 1024, 2) if proc else None
        out["memory_mb"][f"rss_after_{sid}"] = rss_now
        print(
            f"[{i:02d}/{len(dataset)}] {sid} status={res.get('status')} "
            f"lines={len(lines)} time={dt:.2f}s rss={rss_now}MB"
        )

    rss_end = round(proc.memory_info().rss / 1024 / 1024, 2) if proc else None
    peaks = [v["elapsed_sec"] for v in out["samples"].values() if "elapsed_sec" in v]
    peaks.sort()
    if peaks:
        half = (len(peaks) - 1) // 2
        median = peaks[half] if len(peaks) % 2 else (peaks[half] + peaks[half + 1]) / 2
        out["summary"] = {
            "per_image_median_sec": round(median, 4),
            "per_image_p95_sec": round(peaks[int(0.95 * (len(peaks) - 1))], 4),
            "per_image_max_sec": round(max(peaks), 4),
        }
    out["memory_mb"]["rss_end"] = rss_end

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved raw rerun results to {out_path}")
    print(json.dumps(out.get("summary", {}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
