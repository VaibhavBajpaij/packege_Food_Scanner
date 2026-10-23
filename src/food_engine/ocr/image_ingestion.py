"""Stage 1: Image Ingestion and Preprocessing.

Accepts local image paths or raw bytes, validates decoding (JPEG, PNG, WebP),
retains dimensions, checks orientation, and applies safe preprocessing.
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageOps


class ImageIngestionError(Exception):
    """Raised when an image cannot be read or decoded."""
    pass


class ImageIngestion:
    """Handles image loading, format validation, and preprocessing for OCR."""

    SUPPORTED_FORMATS = {"JPEG", "JPG", "PNG", "WEBP"}

    @classmethod
    def load_image(cls, image_input: Union[str, Path, bytes]) -> Tuple[Image.Image, Dict[str, Any]]:
        """Loads and validates an image, returning PIL Image and metadata."""
        try:
            if isinstance(image_input, (str, Path)):
                path = Path(image_input)
                if not path.exists():
                    raise ImageIngestionError(f"Image file does not exist: {path}")
                img = Image.open(path)
                source_identifier = str(path)
            elif isinstance(image_input, bytes):
                import io
                img = Image.open(io.BytesIO(image_input))
                source_identifier = "in_memory_bytes"
            else:
                raise ImageIngestionError(f"Unsupported image input type: {type(image_input)}")

            img_format = (img.format or "JPEG").upper()
            if img_format == "JPG":
                img_format = "JPEG"

            preprocessing_applied = []

            # 1. EXIF orientation correction
            try:
                transposed = ImageOps.exif_transpose(img)
                if transposed != img:
                    img = transposed
                    preprocessing_applied.append("exif_orientation_correction")
            except Exception:
                pass

            # 2. Convert palette or 1-bit images to RGB
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
                preprocessing_applied.append(f"color_mode_conversion_to_{img.mode}")

            width, height = img.size
            aspect_ratio = round(width / max(height, 1), 4)

            metadata = {
                "source": source_identifier,
                "width": width,
                "height": height,
                "format": img_format,
                "color_mode": img.mode,
                "aspect_ratio": aspect_ratio,
                "preprocessing_applied": preprocessing_applied,
            }

            return img, metadata

        except Exception as e:
            if isinstance(e, ImageIngestionError):
                raise
            raise ImageIngestionError(f"Failed to decode image: {e}") from e

    @classmethod
    def prepare_for_ocr(cls, img: Image.Image, max_side_len: int = 1920) -> Tuple[np.ndarray, float]:
        """Resizes moderately if image is excessively large to fit within memory without losing label text detail."""
        w, h = img.size
        scale = 1.0
        max_dim = max(w, h)
        if max_dim > max_side_len:
            scale = max_side_len / max_dim
            new_w = int(w * scale)
            new_h = int(h * scale)
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        np_img = np.array(img)
        return np_img, scale
