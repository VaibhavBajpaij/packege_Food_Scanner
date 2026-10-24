"""Stage 2: Real Food-Label OCR Pipeline using PaddleOCR Pretrained Models.

Integrates with genuine PaddleOCR PP-OCRv4:
- Text detection (PP-OCRv4 mobile detection)
- Direction classifier (textline orientation / angle classification)
- Text recognition (en_PP-OCRv4 mobile English recognition)

Features:
- Operates strictly on image pixels (no PNG metadata or synthetic fallbacks)
- Reliable CPU inference on Windows with MKLDNN PIR compatibility patch
- Extracts recognized text, confidence scores, and bounding polygon boxes
- Reports explicit errors when OCR fails or cannot run
"""

import math
import os
import statistics
import sys
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union
import numpy as np
from PIL import Image

from food_engine.ocr.image_ingestion import ImageIngestion

logger = logging.getLogger(__name__)


def _apply_windows_mkldnn_compatibility() -> None:
    """Configures PaddleX MKLDNN blocklist on Windows to avoid the OneDnn PIR double-attribute bug."""
    try:
        import paddlex.inference.models.runners.paddle_static.config as pdx_cfg
        target_models = [
            "PP-OCRv4_mobile_det",
            "PP-OCRv6_medium_det",
            "PP-LCNet_x1_0_textline_ori",
            "en_PP-OCRv4_mobile_rec",
            "ch_PP-OCRv4_det",
            "en_PP-OCRv4_rec",
        ]
        for m in target_models:
            if m not in pdx_cfg.MKLDNN_BLOCKLIST:
                pdx_cfg.MKLDNN_BLOCKLIST.append(m)
    except Exception as exc:
        logger.debug("PaddleX static config MKLDNN patch skipped: %s", exc)


def _estimate_text_skew(lines: Sequence[Dict[str, Any]]) -> float:
    """Estimates page skew from the top edges of recognized text boxes."""
    angles: List[float] = []
    for line in lines:
        box = line.get("bounding_box") or []
        if len(box) < 2:
            continue
        try:
            (x0, y0), (x1, y1) = box[0], box[1]
            dx, dy = float(x1) - float(x0), float(y1) - float(y0)
        except (TypeError, ValueError):
            continue
        if abs(dx) < 1.0:
            continue
        angle = math.degrees(math.atan2(dy, dx))
        while angle <= -90.0:
            angle += 180.0
        while angle > 90.0:
            angle -= 180.0
        if abs(angle) <= 30.0 and len(str(line.get("text", "")).strip()) >= 3:
            angles.append(angle)
    return statistics.median(angles) if angles else 0.0


class OCREngine:
    """OCR Engine managing text detection and recognition on food packaging images."""

    def __init__(
        self,
        repo_root: Optional[Path] = None,
        use_gpu: bool = False,
        confidence_threshold: float = 0.50,
        require_real_ocr: bool = True,
    ):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.use_gpu = use_gpu
        self.confidence_threshold = confidence_threshold
        self.require_real_ocr = require_real_ocr

        self._ocr_instance = None
        self._engine_type = "uninitialized"
        self._init_error: Optional[str] = None
        self._init_time_sec: float = 0.0

        # Pre-configure environment flags
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        _apply_windows_mkldnn_compatibility()

        self._init_ocr()

    def _init_ocr(self) -> None:
        """Initializes genuine PaddleOCR PP-OCRv4 on CPU/GPU."""
        t0 = time.time()
        try:
            from paddleocr import PaddleOCR
            device_str = "gpu" if self.use_gpu else "cpu"

            # PaddleOCR 3.x API initialization
            self._ocr_instance = PaddleOCR(
                ocr_version="PP-OCRv4",
                lang="en",
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=True,
                device=device_str,
            )
            self._engine_type = f"paddleocr_ppocrv4_{device_str}"
            self._init_time_sec = round(time.time() - t0, 4)
            self._init_error = None
            logger.info("PaddleOCR PP-OCRv4 initialized successfully in %.2fs on %s", self._init_time_sec, device_str)

        except Exception as exc:
            self._ocr_instance = None
            self._init_error = f"{type(exc).__name__}: {str(exc)}"
            self._engine_type = "ocr_unavailable"
            self._init_time_sec = round(time.time() - t0, 4)
            logger.error("Genuine PaddleOCR initialization failed: %s", self._init_error)
            if self.require_real_ocr:
                raise RuntimeError(
                    f"Genuine PaddleOCR initialization failed: {self._init_error}. "
                    "Ensure paddlepaddle and paddleocr are installed and compatible."
                ) from exc

    @property
    def is_ready(self) -> bool:
        """Returns True if genuine OCR engine is loaded and ready for inference."""
        return self._ocr_instance is not None

    def _predict_lines(self, np_img: np.ndarray) -> List[Dict[str, Any]]:
        lines: List[Dict[str, Any]] = []
        preds = self._ocr_instance.predict(np_img)
        if not preds:
            return lines
        first_page = preds[0]
        rec_texts = first_page.get("rec_texts", [])
        rec_scores = first_page.get("rec_scores", [])
        rec_polys = first_page.get("rec_polys", [])
        for i, (text, score) in enumerate(zip(rec_texts, rec_scores)):
            score_val = float(score)
            if score_val < self.confidence_threshold:
                continue
            bbox = []
            if i < len(rec_polys) and rec_polys[i] is not None:
                poly_arr = rec_polys[i]
                if hasattr(poly_arr, "tolist"):
                    bbox = poly_arr.tolist()
                else:
                    bbox = [list(pt) for pt in poly_arr]
            lines.append({
                "text": str(text).strip(),
                "confidence": round(score_val, 4),
                "bounding_box": bbox,
            })
        return lines

    def run_ocr(self, img_input: Any, scale: float = 1.0) -> Dict[str, Any]:
        """Runs genuine OCR on image pixels and returns structured detected lines.

        Never reads PNG metadata, filenames, or embedded fixture text.
        """
        start_time = time.time()

        if self._ocr_instance is None:
            return {
                "status": "ocr_failed",
                "error": f"OCR Engine not available: {self._init_error}",
                "engine": self._engine_type,
                "model_version": "PP-OCRv4-mobile",
                "execution_time_sec": 0.0,
                "line_count": 0,
                "lines": [],
                "image_metadata": {},
            }

        try:
            img, meta = ImageIngestion.load_image(img_input)
        except Exception as exc:
            return {
                "status": "invalid_image",
                "error": f"Image ingestion failed: {type(exc).__name__}: {str(exc)}",
                "engine": self._engine_type,
                "model_version": "PP-OCRv4-mobile",
                "execution_time_sec": round(time.time() - start_time, 4),
                "line_count": 0,
                "lines": [],
                "image_metadata": {},
            }

        # Check for empty / zero-dimension image
        if img.width == 0 or img.height == 0:
            return {
                "status": "empty_image",
                "error": "Image has zero dimensions",
                "engine": self._engine_type,
                "model_version": "PP-OCRv4-mobile",
                "execution_time_sec": round(time.time() - start_time, 4),
                "line_count": 0,
                "lines": [],
                "image_metadata": meta,
            }

        if scale != 1.0:
            resample = getattr(Image, "Resampling", Image).LANCZOS
            img = img.resize(
                (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
                resample,
            )

        # Convert strictly to RGB numpy array for genuine pixel-based inference
        np_img = np.array(img.convert("RGB"))

        lines: List[Dict[str, Any]] = []
        ocr_error: Optional[str] = None
        deskew_angle = 0.0

        try:
            lines = self._predict_lines(np_img)

            # Correct page-level skew before recognition. The line orientation
            # classifier handles upside-down runs, but it does not level a
            # diagonally photographed panel, which loses many row labels.
            angle = _estimate_text_skew(lines)
            if 8.0 <= abs(angle) <= 25.0:
                rotated = img.rotate(angle, expand=True, fillcolor=(255, 255, 255))
                deskewed = self._predict_lines(np.array(rotated.convert("RGB")))
                if len(deskewed) >= int(len(lines) * 0.8):
                    lines = deskewed
                    deskew_angle = round(angle, 2)

        except Exception as exc:
            ocr_error = f"OCR inference error: {type(exc).__name__}: {str(exc)}"
            logger.error("PaddleOCR inference exception: %s", ocr_error)

        elapsed = time.time() - start_time

        status = "success"
        if ocr_error:
            status = "ocr_failed"
        elif len(lines) == 0:
            status = "no_text_detected"

        return {
            "status": status,
            "engine": self._engine_type,
            "model_version": "PP-OCRv4-mobile",
            "execution_time_sec": round(elapsed, 4),
            "line_count": len(lines),
            "lines": lines,
            "image_metadata": meta,
            "deskew_angle": deskew_angle,
            "ocr_scale": scale,
            "error": ocr_error,
        }
