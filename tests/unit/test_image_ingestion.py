"""Unit tests for Stage 1: Image Ingestion and Preprocessing."""

from pathlib import Path
import pytest
from PIL import Image
from food_engine.ocr.image_ingestion import ImageIngestion, ImageIngestionError


def test_valid_image_ingestion(tmp_path: Path):
    test_img = Image.new("RGB", (640, 480), color=(200, 100, 50))
    img_path = tmp_path / "valid.jpg"
    test_img.save(img_path)

    loaded_img, meta = ImageIngestion.load_image(img_path)
    assert loaded_img.size == (640, 480)
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["format"] == "JPEG"
    assert meta["aspect_ratio"] == round(640 / 480, 4)


def test_invalid_image_raises_error(tmp_path: Path):
    bad_file = tmp_path / "corrupt.png"
    bad_file.write_bytes(b"not_a_valid_image_header")

    with pytest.raises(ImageIngestionError):
        ImageIngestion.load_image(bad_file)


def test_nonexistent_image_raises_error():
    with pytest.raises(ImageIngestionError):
        ImageIngestion.load_image("non_existent_image_path_12345.png")


def test_prepare_for_ocr_scaling(tmp_path: Path):
    huge_img = Image.new("RGB", (3000, 2000), color=(255, 255, 255))
    np_img, scale = ImageIngestion.prepare_for_ocr(huge_img, max_side_len=1500)
    assert scale == 0.5
    assert np_img.shape[0] == 1000
    assert np_img.shape[1] == 1500
