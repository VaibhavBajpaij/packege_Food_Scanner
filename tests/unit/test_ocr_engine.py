"""Unit tests for Stage 2: Genuine Pixel-Based OCR Engine.

Tests:
- Actual image-pixel OCR on drawn text
- Pixel sensitivity (different pixels produce different OCR results)
- Blank/empty images without text
- Corrupted and non-existent image files
- Confidence threshold filtering
- Explicit failure reporting when OCR is unavailable
- Zero tolerance for synthetic metadata fallbacks
"""

from pathlib import Path
from unittest.mock import patch
import pytest
from PIL import Image, ImageDraw, ImageFont

from food_engine.ocr.ocr_engine import OCREngine


@pytest.fixture(scope="module")
def ocr_engine():
    """Shared OCR engine fixture to avoid re-initializing models for each test."""
    return OCREngine(require_real_ocr=True)


def test_real_pixel_ocr_recognizes_drawn_text(tmp_path: Path, ocr_engine: OCREngine):
    """Verifies that genuine OCR recognizes text rendered into raw image pixels."""
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    # Draw clear uppercase text onto pixels
    draw.text((30, 40), "CALORIES 250", fill=(0, 0, 0), font=font)
    draw.text((30, 90), "TOTAL FAT 12g", fill=(0, 0, 0), font=font)
    draw.text((30, 140), "PROTEIN 8g", fill=(0, 0, 0), font=font)

    test_path = tmp_path / "drawn_nutrition.png"
    img.save(test_path)

    res = ocr_engine.run_ocr(test_path)

    assert res["status"] == "success"
    assert res["engine"].startswith("paddleocr_ppocrv4")
    assert res["line_count"] > 0
    assert len(res["lines"]) > 0

    joined = " ".join([l["text"].upper() for l in res["lines"]])
    assert "CALORIES" in joined or "250" in joined or "FAT" in joined or "PROTEIN" in joined

    for line in res["lines"]:
        assert "text" in line
        assert "confidence" in line
        assert 0.0 <= line["confidence"] <= 1.0
        assert "bounding_box" in line
        # PP-OCRv4 returns 4 polygon points: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        assert len(line["bounding_box"]) == 4


def test_pixel_sensitivity_different_pixels_different_text(tmp_path: Path, ocr_engine: OCREngine):
    """Verifies that OCR output is strictly driven by pixel content, not metadata or cache."""
    # Image A: SUGAR
    img_a = Image.new("RGB", (400, 100), color=(255, 255, 255))
    draw_a = ImageDraw.Draw(img_a)
    draw_a.text((30, 30), "ORGANIC SUGAR", fill=(0, 0, 0))
    path_a = tmp_path / "pixel_test_a.png"
    img_a.save(path_a)

    # Image B: SODIUM
    img_b = Image.new("RGB", (400, 100), color=(255, 255, 255))
    draw_b = ImageDraw.Draw(img_b)
    draw_b.text((30, 30), "SODIUM 500mg", fill=(0, 0, 0))
    path_b = tmp_path / "pixel_test_b.png"
    img_b.save(path_b)

    res_a = ocr_engine.run_ocr(path_a)
    res_b = ocr_engine.run_ocr(path_b)

    text_a = " ".join([l["text"].upper() for l in res_a["lines"]])
    text_b = " ".join([l["text"].upper() for l in res_b["lines"]])

    assert text_a != text_b
    assert "SUGAR" in text_a or "ORGANIC" in text_a
    assert "SODIUM" in text_b or "500" in text_b


def test_empty_blank_image(tmp_path: Path, ocr_engine: OCREngine):
    """A completely blank image with no text should return 'no_text_detected'."""
    blank_img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    blank_path = tmp_path / "blank.png"
    blank_img.save(blank_path)

    res = ocr_engine.run_ocr(blank_path)

    assert res["status"] == "no_text_detected"
    assert res["line_count"] == 0
    assert res["lines"] == []
    assert res["error"] is None


def test_corrupted_image_handling(tmp_path: Path, ocr_engine: OCREngine):
    """Corrupted files should be handled safely with status 'invalid_image'."""
    corrupt_file = tmp_path / "corrupt.jpg"
    corrupt_file.write_bytes(b"corrupted_header_data_not_an_image_123456789")

    res = ocr_engine.run_ocr(corrupt_file)

    assert res["status"] == "invalid_image"
    assert res["line_count"] == 0
    assert res["lines"] == []
    assert "Image ingestion failed" in res["error"]


def test_nonexistent_image_handling(ocr_engine: OCREngine):
    """Non-existent image paths should return 'invalid_image' with clear error."""
    res = ocr_engine.run_ocr("non_existent_image_path_987654.png")

    assert res["status"] == "invalid_image"
    assert res["line_count"] == 0
    assert res["lines"] == []
    assert "does not exist" in res["error"]


def test_confidence_threshold_filtering(tmp_path: Path):
    """Verifies that lines below the confidence threshold are filtered out."""
    img = Image.new("RGB", (400, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 30), "INGREDIENTS: OATS", fill=(0, 0, 0))
    path = tmp_path / "thresh_test.png"
    img.save(path)

    ocr_strict = OCREngine(confidence_threshold=0.99, require_real_ocr=True)
    res_strict = ocr_strict.run_ocr(path)

    for line in res_strict["lines"]:
        assert line["confidence"] >= 0.99


def test_initialization_failure_raises_when_required():
    """When require_real_ocr=True, initialization failure must raise RuntimeError."""
    with patch("paddleocr.PaddleOCR", side_effect=ImportError("Simulated missing PaddleOCR")):
        with pytest.raises(RuntimeError) as exc_info:
            OCREngine(require_real_ocr=True)
        assert "Genuine PaddleOCR initialization failed" in str(exc_info.value)


def test_failure_reported_when_real_ocr_not_required(tmp_path: Path):
    """When require_real_ocr=False, initialization failure sets error status and never fakes success."""
    with patch("paddleocr.PaddleOCR", side_effect=ImportError("Simulated missing PaddleOCR")):
        engine = OCREngine(require_real_ocr=False)
        assert engine.is_ready is False
        assert engine._engine_type == "ocr_unavailable"

        # Create dummy image
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        img_path = tmp_path / "test.png"
        img.save(img_path)

        res = engine.run_ocr(img_path)
        assert res["status"] == "ocr_failed"
        assert res["line_count"] == 0
        assert res["lines"] == []
        assert "OCR Engine not available" in res["error"]
