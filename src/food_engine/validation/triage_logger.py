"""Failure Triage & Hard Example Logger for Packaged Food Scanner.

Categorizes pipeline failures into:
- BUCKET_A_IMAGE_QUALITY: Camera/user fault (blurry, out of focus, glare, underexposed).
- BUCKET_B_ENGINE_PARSER_BUG: System bug (image is sharp and readable, but parser/regex/fusion failed).

Automatically creates:
- Image file: datasets/triage/images/{triage_id}.jpg
- JSON sidecar: datasets/triage/reports/{triage_id}.json
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import cv2
import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
TRIAGE_DIR = REPO_ROOT / "datasets" / "triage"
TRIAGE_IMAGES_DIR = TRIAGE_DIR / "images"
TRIAGE_REPORTS_DIR = TRIAGE_DIR / "reports"

BLUR_THRESHOLD_DEFAULT = 80.0  # Laplacian variance threshold


def calculate_blur_score(image_input: Union[np.ndarray, Image.Image, Path, str]) -> float:
    """Calculate the Laplacian variance of an image to measure edge sharpness.

    Higher values indicate a sharper, clearer image.
    Values < 80 typically indicate motion blur or defocus.
    """
    try:
        if isinstance(image_input, (str, Path)):
            cv_img = cv2.imread(str(image_input))
            if cv_img is None:
                return 0.0
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
        elif isinstance(image_input, Image.Image):
            rgb = np.array(image_input.convert("RGB"))
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        elif isinstance(image_input, np.ndarray):
            if len(image_input.shape) == 3:
                gray = cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY)
            else:
                gray = image_input
        else:
            return 0.0

        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        return round(float(score), 2)
    except Exception:
        return 0.0


def check_image_quality(
    image_input: Union[np.ndarray, Image.Image, Path, str],
    threshold: float = BLUR_THRESHOLD_DEFAULT
) -> Tuple[bool, float, str]:
    """Pre-flight quality gate to verify if an image is sharp enough for reliable OCR.

    Returns:
        (is_passed, blur_score, message)
    """
    score = calculate_blur_score(image_input)
    if score < threshold:
        msg = (
            f"Image is too blurry (sharpness score {score:.1f} < required threshold {threshold:.1f}). "
            f"Please hold the camera steady in good lighting and scan again."
        )
        return False, score, msg
    else:
        msg = f"Image quality passed (sharpness score: {score:.1f} >= {threshold:.1f})."
        return True, score, msg


def log_triage_case(
    image_input: Union[np.ndarray, Image.Image, Path, str],
    failure_reason: str,
    details: Optional[Dict[str, Any]] = None,
    sample_id: Optional[str] = None,
    barcode: Optional[str] = None,
    product_name: Optional[str] = None
) -> Dict[str, Any]:
    """Capture a failed or uncertain scan into the Triage Queue with image and JSON sidecar.

    Args:
        image_input: The image that failed
        failure_reason: e.g. 'IMAGE_TOO_BLURRY', 'NO_NUTRITION_TABLE', 'SANITY_CHECK_FAILED', 'PARSER_ERROR'
        details: Diagnostic dictionary (OCR tokens, error traceback, parsed values)
        sample_id: Optional unique identifier
        barcode: Optional barcode if available
        product_name: Optional detected name
    """
    TRIAGE_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    TRIAGE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    triage_id = sample_id or f"triage_{timestamp_str}_{int(time.time()*1000)%1000:03d}"

    # Calculate blur score
    score = calculate_blur_score(image_input)

    # Classify into Bucket A vs Bucket B
    if score < BLUR_THRESHOLD_DEFAULT or "BLUR" in failure_reason.upper():
        suspected_bucket = "BUCKET_A_IMAGE_QUALITY"
        category_desc = "Camera / Photographic fault (blurry, out-of-focus, or motion artifact)."
        recommended_action = "Prompt user to retake photo; do not alter engine extraction rules."
    else:
        suspected_bucket = "BUCKET_B_ENGINE_PARSER_BUG"
        category_desc = "Engine / Parser bug (image is sharp, but extraction/normalization/fusion failed)."
        recommended_action = "Inspect raw OCR tokens and improve dictionary, regex, or table parser."

    # Save image
    img_filename = f"{triage_id}.jpg"
    img_save_path = TRIAGE_IMAGES_DIR / img_filename

    try:
        if isinstance(image_input, (str, Path)):
            cv_img = cv2.imread(str(image_input))
            if cv_img is not None:
                cv2.imwrite(str(img_save_path), cv_img)
        elif isinstance(image_input, Image.Image):
            image_input.convert("RGB").save(str(img_save_path), format="JPEG", quality=90)
        elif isinstance(image_input, np.ndarray):
            if len(image_input.shape) == 3 and image_input.shape[2] == 3:
                cv2.imwrite(str(img_save_path), image_input)
            else:
                Image.fromarray(image_input).save(str(img_save_path))
    except Exception as e:
        img_filename = f"save_failed: {e}"

    # Prepare JSON Sidecar
    payload = {
        "triage_id": triage_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "barcode": barcode,
        "product_name": product_name,
        "failure_reason": failure_reason,
        "suspected_bucket": suspected_bucket,
        "category_description": category_desc,
        "recommended_action": recommended_action,
        "sharpness_score": score,
        "blur_threshold": BLUR_THRESHOLD_DEFAULT,
        "is_blurry": score < BLUR_THRESHOLD_DEFAULT,
        "image_file": img_filename,
        "diagnostics": details or {}
    }

    report_path = TRIAGE_REPORTS_DIR / f"{triage_id}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    return payload


def get_triage_summary() -> Dict[str, Any]:
    """Read and aggregate all pending triage reports."""
    if not TRIAGE_REPORTS_DIR.exists():
        return {
            "total_cases": 0,
            "bucket_a_image_quality": 0,
            "bucket_b_engine_bug": 0,
            "cases": []
        }

    cases = []
    bucket_a_count = 0
    bucket_b_count = 0

    for p in sorted(TRIAGE_REPORTS_DIR.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                cases.append(data)
                if data.get("suspected_bucket") == "BUCKET_A_IMAGE_QUALITY":
                    bucket_a_count += 1
                else:
                    bucket_b_count += 1
        except Exception:
            continue

    return {
        "total_cases": len(cases),
        "bucket_a_image_quality": bucket_a_count,
        "bucket_b_engine_bug": bucket_b_count,
        "cases": cases
    }
