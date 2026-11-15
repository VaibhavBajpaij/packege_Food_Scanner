"""Unit tests for the Streamlit Testing UI (app.py).

Verifies:
- Presets configuration and file path validity.
- Barcode image decoding helper with OpenCV.
- Ground truth loader and accuracy evaluation logic.
- Engine instantiation and clean execution.
"""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pytest

from app import (
    PRESETS,
    decode_barcode_from_image,
    load_ground_truth_samples,
)


def test_presets_configuration_validity():
    """Verifies that all defined presets have existing fixture files when paths are specified."""
    assert len(PRESETS) >= 6
    for name, config in PRESETS.items():
        if config["nutrition_img"]:
            assert Path(config["nutrition_img"]).exists(), f"Image path for {name} does not exist: {config['nutrition_img']}"
        if config["ingredients_img"]:
            assert Path(config["ingredients_img"]).exists(), f"Ingredients path for {name} does not exist: {config['ingredients_img']}"


def test_decode_barcode_from_image_handles_invalid():
    """Verifies that barcode decoding gracefully handles invalid inputs without crashing."""
    # Blank array
    blank_arr = np.zeros((100, 100, 3), dtype=np.uint8)
    code, err = decode_barcode_from_image(blank_arr)
    assert code is None

    # Invalid object
    code_inv, err_inv = decode_barcode_from_image(None)
    assert code_inv is None


def test_ground_truth_samples_loader():
    """Verifies that ground_truth_v4 samples are loaded."""
    samples = load_ground_truth_samples()
    assert isinstance(samples, dict)
    assert len(samples) >= 20
    assert "real_photo_01" in samples
    assert "real_photo_02" in samples


def test_accuracy_comparison_logic():
    """Verifies the accuracy comparison logic (TP, FP, FN calculation with tolerance)."""
    expected = {
        "energy_kcal": 460.0,
        "protein_g": 7.5,
        "carbohydrates_g": 68.0,
        "sugars_g": 24.5,
        "total_fat_g": 18.0,
    }

    extracted = {
        "energy_kcal": {"value": 460.0, "status": "declared"},  # Exact match -> TP
        "protein_g": {"value": 7.4, "status": "declared"},       # Within 5% -> TP
        "carbohydrates_g": {"value": 75.0, "status": "declared"},# Deviates (>5%) -> FP
        "sugars_g": {"value": None, "status": "missing"},        # Missed -> FN
        "total_fat_g": {"value": 18.0, "status": "declared"},   # Exact match -> TP
        "salt_g": {"value": 0.95, "status": "declared"},         # Extra / unverified -> FP
    }

    tp, fp, fn = 0, 0, 0
    tol_ratio = 0.05

    for field, exp_val in expected.items():
        ext_obj = extracted.get(field, {})
        ext_val = ext_obj.get("value")

        if exp_val is not None and ext_val is not None:
            abs_diff = abs(ext_val - exp_val)
            allowed_tol = max(exp_val * tol_ratio, 0.5)
            if abs_diff <= allowed_tol:
                tp += 1
            else:
                fp += 1
        elif exp_val is not None and ext_val is None:
            fn += 1

    # Check unverified / extra fields
    for field, ext_obj in extracted.items():
        if field not in expected and ext_obj.get("value") is not None:
            fp += 1

    assert tp == 3  # energy_kcal, protein_g, total_fat_g
    assert fp == 2  # carbohydrates_g (deviation), salt_g (extra)
    assert fn == 1  # sugars_g (missed)

    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    assert round(precision, 2) == 0.60
    assert round(recall, 2) == 0.75


def test_webrtc_constraints_and_processor():
    """Verifies that BarcodeProcessor initializes properly and MEDIA_STREAM_CONSTRAINTS are well-formed."""
    from app import BarcodeProcessor, MEDIA_STREAM_CONSTRAINTS
    import av

    # Check media constraints
    assert "video" in MEDIA_STREAM_CONSTRAINTS
    v = MEDIA_STREAM_CONSTRAINTS["video"]
    assert v.get("facingMode") == {"ideal": "environment"}
    assert v.get("width") == {"ideal": 1920}
    assert v.get("height") == {"ideal": 1080}
    assert v.get("advanced") == [{"focusMode": "continuous"}]

    # Test BarcodeProcessor
    proc = BarcodeProcessor()
    assert not proc.barcode_detected
    assert proc.barcode_queue.empty()

    # Feed dummy frame
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = av.VideoFrame.from_ndarray(blank, format="bgr24")
    out_frame = proc.recv(frame)
    assert out_frame is not None
    assert proc.barcode_queue.empty()

