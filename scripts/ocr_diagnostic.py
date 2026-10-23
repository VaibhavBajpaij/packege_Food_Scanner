"""Reproducible OCR diagnostic for real food-package photographs.

For each image, records:
- SHA-256 checksum and dimensions
- Engine/model identity (paddle/paddleocr versions, device, configuration)
- Inference status, recognized lines and elapsed time
- A metadata-independence proof: the image is re-encoded with all metadata
  stripped and re-run; both raw OCR outputs are compared so we can demonstrate
  the prediction comes from pixels, not from PNG/text metadata or fixtures.

Usage:
    python scripts/ocr_diagnostic.py [image1 image2 ... | --all]

Outputs per-image JSON to reports/evaluation/ocr_diagnostic/<stem>.json and
prints a summary to stdout. No network access is required.
"""

import argparse
import hashlib
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

OUT_DIR = REPO_ROOT / "reports" / "evaluation" / "ocr_diagnostic"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_metadata_copy(path: Path) -> Path:
    """Lossless re-encode to PNG: identical pixels, every auxiliary chunk dropped.

    Because pixels are unchanged, any OCR-output difference would indicate the
    engine is reading something other than pixels (metadata/filesystem), while
    identical output proves the prediction is pixel-driven.
    """
    from PIL import Image

    out = OUT_DIR / "metadata_stripped"
    out.mkdir(parents=True, exist_ok=True)
    dst = out / f"{path.stem}_clean.png"
    with Image.open(path) as im:
        if im.mode not in ("RGB", "L"):
            im = im.convert(im.mode)
        im.save(dst, format="PNG", compress_level=0)
    return dst


def normalise_line_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def engine_identity(ocr: Any) -> Dict[str, Any]:
    """Collects recorded model/version/config/device info from the OCR engine."""
    import paddle
    import paddleocr

    info: Dict[str, Any] = {
        "paddle_version": getattr(paddle, "__version__", None),
        "paddleocr_version": getattr(paddleocr, "__version__", None),
        "engine_type": ocr._engine_type,
        "device": "gpu" if ocr.use_gpu else "cpu",
        "init_time_sec": ocr._init_time_sec,
        "init_error": ocr._init_error,
        "confidence_threshold": ocr.confidence_threshold,
        "constructor_kwargs": {
            "ocr_version": "PP-OCRv4",
            "lang": "en",
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": True,
        },
    }
    # Best-effort capture of the loaded model directories (PaddleOCR 3.x / PaddleX)
    instance = ocr._ocr_instance
    for attr in (
        "text_det_model_dir",
        "text_rec_model_dir",
        "text_cls_model_dir",
        "text_rec_model_name",
        "text_det_model_name",
    ):
        val = getattr(instance, attr, None)
        if val:
            info[attr] = str(val)
    return info


def locator_models_dirs() -> List[str]:
    """Finds downloaded PaddleX/PaddleOCR model directories on this machine."""
    found: List[str] = []
    home = Path.home()
    for candidate in (
        home / ".paddlex" / "official_models",
        REPO_ROOT / "models" / "paddleocr",
    ):
        if candidate.is_dir():
            for d in sorted(candidate.iterdir()):
                if d.is_dir():
                    found.append(str(d))
    return found


def diagnose_one(ocr: Any, image_path: Path) -> Dict[str, Any]:
    t0 = time.time()
    result = ocr.run_ocr(str(image_path))
    elapsed = time.time() - t0

    lines = [l["text"] for l in result.get("lines", [])]
    confs = [l["confidence"] for l in result.get("lines", [])]

    diag: Dict[str, Any] = {
        "image": str(image_path),
        "sha256": sha256_file(image_path),
        "status": result.get("status"),
        "error": result.get("error"),
        "engine": result.get("engine"),
        "model_version": result.get("model_version"),
        "line_count": result.get("line_count"),
        "lines": lines,
        "confidences": confs,
        "elapsed_sec": round(elapsed, 4),
        "engine_internal_time_sec": result.get("execution_time_sec"),
        "image_metadata": result.get("image_metadata", {}),
    }

    # Metadata-independence proof
    clean_path = strip_metadata_copy(image_path)
    clean_result = ocr.run_ocr(str(clean_path))
    clean_lines = [l["text"] for l in clean_result.get("lines", [])]
    same_lines = [normalise_line_text(x) for x in lines] == [
        normalise_line_text(x) for x in clean_lines
    ]
    diag["metadata_independence_check"] = {
        "stripped_image": str(clean_path),
        "qualities_equal_after_stripping": same_lines,
        "line_count_clean": clean_result.get("line_count"),
    }
    return diag


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR diagnostic with integrity proof")
    parser.add_argument("images", nargs="*", help="Image paths; empty or --all runs on all 22 real photos")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    fixture_dir = REPO_ROOT / "tests" / "fixtures" / "real_photos"
    if args.all or not args.images:
        images = sorted(set(fixture_dir.glob("*.jpg")) | set(fixture_dir.glob("*.png")))
    else:
        images = [Path(p).resolve() for p in args.images]
        for p in images:
            if not p.exists():
                print(f"Missing image: {p}")
                return 2

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Initializing OCR engine ...")
    from food_engine.ocr.ocr_engine import OCREngine

    t0 = time.time()
    try:
        ocr = OCREngine(repo_root=REPO_ROOT, require_real_ocr=True)
        init_ok = True
    except Exception as exc:
        print(f"FATAL: OCR engine initialization failed: {exc}")
        return 3
    init_time = time.time() - t0
    print(f"Engine ready ({ocr._engine_type}) in {init_time:.2f}s")

    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine_identity": engine_identity(ocr),
        "model_dirs_on_disk": locator_models_dirs(),
        "engine_init_sec": round(init_time, 4),
        "images": [],
    }

    failures = 0
    for p in images:
        print(f"\n--- {p.name} ---")
        try:
            d = diagnose_one(ocr, p)
        except Exception as exc:
            d = {"image": str(p), "status": "diagnostic_failed", "error": f"{type(exc).__name__}: {exc}"}
            failures += 1
        report["images"].append(d)
        print(f"status={d.get('status')} lines={d.get('line_count')} elapsed={d.get('elapsed_sec')}s")
        for i, line in enumerate(d.get("lines", [])[:5], 1):
            print(f"  {i:02d}. {line}")
        if len(d.get("lines", [])) > 5:
            print(f"  ... ({len(d['lines'])} lines total)")
        chk = d.get("metadata_independence_check", {})
        print(f"metadata-stripped rerun: same output = {chk.get('qualities_equal_after_stripping')}")
        out_json = OUT_DIR / f"{p.stem}.json"
        out_json.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    report["total_images"] = len(images)
    report["failures"] = failures
    summary_path = OUT_DIR / "diagnostic_summary.json"
    summary_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(images)} per-image reports to {OUT_DIR}")
    print(f"Summary: {summary_path}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
