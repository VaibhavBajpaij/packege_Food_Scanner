"""Tests for page-skew estimation used before OCR."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.ocr.ocr_engine import _estimate_text_skew  # noqa: E402


def line(text, p0, p1):
    return {"text": text, "bounding_box": [p0, p1, [p1[0], p1[1] + 20], [p0[0], p0[1] + 20]]}


def test_positive_skew_is_estimated():
    lines = [
        line("Nutrition Facts", (0, 0), (100, 27)),
        line("Total Fat 2g", (0, 40), (100, 67)),
    ]
    assert abs(_estimate_text_skew(lines) - 15.1) < 0.2


def test_negative_skew_is_estimated():
    lines = [
        line("Nutrition Facts", (100, 0), (0, 18)),
        line("Total Fat 2g", (100, 40), (0, 58)),
    ]
    assert abs(_estimate_text_skew(lines) + 10.2) < 0.2


def test_vertical_and_short_boxes_are_ignored():
    lines = [
        line("x", (0, 0), (100, 0)),
        line("sideways", (0, 0), (0, 100)),
    ]
    assert _estimate_text_skew(lines) == 0.0
