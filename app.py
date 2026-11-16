"""Food Intelligence Engine - Local Image Testing Interface.

A standalone Streamlit testing workbench for packaged-food barcode lookup,
PaddleOCR nutrition-label extraction, ingredient and allergen parsing,
nutrient data enrichment, and ground-truth accuracy evaluation.
"""

import io
import json
import logging
import os
import queue
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure 'src' directory is in Python path for cloud deployments (Streamlit Cloud, Render, Docker)
_ROOT_DIR = Path(__file__).resolve().parent
_SRC_DIR = _ROOT_DIR / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import av
import cv2
import numpy as np
import pandas as pd
from PIL import Image
import streamlit as st
from streamlit_webrtc import (
    RTCConfiguration,
    VideoProcessorBase,
    WebRtcMode,
    webrtc_streamer,
)

from food_engine.validation.barcode_validator import BarcodeValidator

logger = logging.getLogger("food_intelligence_scanner")

# Configure page layout
st.set_page_config(
    page_title="Food Packet Scanner - Testing UI",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for rich aesthetics and status badges
st.markdown(
    """
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #475569;
        margin-bottom: 1.5rem;
    }
    .badge-declared {
        background-color: #DEF7EC;
        color: #03543F;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-exact-db {
        background-color: #E1EFFE;
        color: #1E429F;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-reference {
        background-color: #FEF08A;
        color: #854D0E;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-calculated {
        background-color: #F3E8FF;
        color: #6B21A8;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-missing {
        background-color: #FDE8E8;
        color: #9B1C1C;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.78rem;
        display: inline-block;
    }
    .badge-correct {
        background-color: #10B981;
        color: white;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-incorrect {
        background-color: #EF4444;
        color: white;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .badge-missed {
        background-color: #F59E0B;
        color: white;
        padding: 0.2rem 0.55rem;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .info-callout {
        border-left: 4px solid #3B82F6;
        background-color: #EFF6FF;
        padding: 0.75rem 1rem;
        border-radius: 0 6px 6px 0;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Repo Root Resolution
REPO_ROOT = Path(__file__).resolve().parent

# Cached Engine Initialization
@st.cache_resource(show_spinner="Initializing Food Intelligence Engine & Pretrained PP-OCRv4...")
def get_engine():
    from food_engine.engine import FoodIntelligenceEngine
    return FoodIntelligenceEngine(repo_root=REPO_ROOT)


# WebRTC Configuration with public Google STUN server for NAT traversal
RTC_CONFIGURATION = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)

MEDIA_STREAM_CONSTRAINTS = {
    "video": {
        "facingMode": {"ideal": "environment"},
        "width": {"ideal": 1920},
        "height": {"ideal": 1080},
        "advanced": [{"focusMode": "continuous"}],
    },
    "audio": False,
}


def decode_barcode_from_image(
    image_input: Any,
    ocr_lines: Optional[List[str]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Decodes 1D barcode directly from image pixels using ZXing-C++ with multi-scale/rotation,
    CLAHE, OpenCV, and printed OCR line fallback."""
    from food_engine.validation.barcode_validator import BarcodeValidator

    try:
        pil_img = None
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input))
        elif isinstance(image_input, Image.Image):
            pil_img = image_input
        elif hasattr(image_input, "read"):
            file_bytes = image_input.read()
            pil_img = Image.open(io.BytesIO(file_bytes))
            image_input.seek(0)
        elif isinstance(image_input, np.ndarray):
            pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
        else:
            return None, "Unsupported image object for barcode detection."

        if pil_img is None:
            return None, "Failed to load image pixels for barcode detection."

        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        w, h = pil_img.size

        # Strategy 1 & 2: ZXing-C++ with multi-scale downscaling and rotations
        try:
            import zxingcpp
            scales = [1.0]
            if max(w, h) > 1500:
                scales.extend([0.75, 0.5, 0.35])

            for scale in scales:
                cur_img = pil_img if scale == 1.0 else pil_img.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
                results = zxingcpp.read_barcodes(
                    cur_img,
                    try_rotate=True,
                    try_downscale=True,
                    try_invert=True,
                    return_errors=True,
                )
                if results:
                    for r in results:
                        txt = str(r.text).strip()
                        if txt:
                            val = BarcodeValidator.validate(txt)
                            if val.is_valid:
                                return val.normalized_code, None
                            elif val.lookup_candidates:
                                return val.lookup_candidates[0], None
                            return txt, None

            # Strategy 3: Contrast enhancement with CLAHE on grayscale
            scaled_for_clahe = pil_img if max(w, h) <= 1800 else pil_img.resize((int(w * (1800.0 / max(w, h))), int(h * (1800.0 / max(w, h)))), Image.Resampling.BILINEAR)
            cv_gray = cv2.cvtColor(np.array(scaled_for_clahe), cv2.COLOR_RGB2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
            enhanced = clahe.apply(cv_gray)
            results = zxingcpp.read_barcodes(enhanced, try_rotate=True, try_downscale=True, try_invert=True, return_errors=True)
            if results:
                for r in results:
                    txt = str(r.text).strip()
                    if txt:
                        val = BarcodeValidator.validate(txt)
                        if val.is_valid:
                            return val.normalized_code, None
                        elif val.lookup_candidates:
                            return val.lookup_candidates[0], None
                        return txt, None
        except Exception as exc:
            logger.debug(f"[Barcode Strategy 1/2/3 Exception]: {exc}")

        # Strategy 4: Fallback to OpenCV BarcodeDetector
        try:
            cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            detector = cv2.barcode.BarcodeDetector()
            res = detector.detectAndDecode(cv_img)
            if len(res) == 3:
                decoded_info, decoded_type, _ = res
                if decoded_info:
                    code_str = str(decoded_info).strip()
                    if code_str:
                        val = BarcodeValidator.validate(code_str)
                        if val.is_valid:
                            return val.normalized_code, None
                        elif val.lookup_candidates:
                            return val.lookup_candidates[0], None
                        return code_str, None
        except Exception as exc:
            logger.debug(f"[Barcode Strategy 4 Exception]: {exc}")

        # Strategy 5: OCR Line printed barcode numbers fallback
        if ocr_lines:
            recovered = BarcodeValidator.extract_barcode_from_ocr_lines(ocr_lines)
            if recovered:
                return recovered, None

        return None, "No barcode detected. Ensure barcode is in focus, well-lit, and visible in frame."
    except Exception as exc:
        logger.error(f"[decode_barcode_from_image Error]: {exc}\n{traceback.format_exc()}")
        return None, f"Barcode scanner error: {exc}"


class BarcodeProcessor(VideoProcessorBase):
    """Real-time WebRTC video processor for continuous barcode detection and smart OCR auto-capture."""

    def __init__(self):
        self.frame_count = 0
        self.barcode_queue: "queue.Queue[str]" = queue.Queue()
        self.ocr_queue: "queue.Queue[np.ndarray]" = queue.Queue()
        self.ocr_mode: bool = False
        self.barcode_detected: bool = False
        self.ocr_captured: bool = False
        self.steady_frames: int = 0
        self.latest_sharpness: float = 0.0

    def recv(self, frame: av.VideoFrame) -> av.VideoFrame:
        try:
            img_bgr = frame.to_ndarray(format="bgr24")
        except Exception as exc:
            logger.error(f"[BarcodeProcessor] Error converting frame to ndarray: {exc}\n{traceback.format_exc()}")
            return frame

        self.frame_count += 1
        h, w = img_bgr.shape[:2]

        if not self.ocr_mode:
            # --- PHASE 1: CONTINUOUS BARCODE DETECTION WITH FULL PARITY ---
            if not self.barcode_detected and (self.frame_count % 3 == 0):
                # Analyze every 3rd frame using robust multi-angle, CLAHE, and OpenCV fallback pipeline
                try:
                    detected_code, decode_err = decode_barcode_from_image(img_bgr)
                    if detected_code:
                        self.barcode_detected = True
                        self.barcode_queue.put(detected_code)
                        logger.info(f"[BarcodeProcessor] Barcode detected in real-time stream: {detected_code}")
                    elif decode_err and "No barcode detected" not in decode_err:
                        logger.warning(f"[BarcodeProcessor] Barcode decoding notice: {decode_err}")
                except Exception as exc:
                    logger.error(f"[BarcodeProcessor Worker Thread Error]: {exc}\n{traceback.format_exc()}")

            if self.barcode_detected:
                cv2.putText(
                    img_bgr,
                    "BARCODE DETECTED! PROCESSING...",
                    (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85,
                    (0, 255, 0),
                    2,
                )
            else:
                # Reticle viewfinder overlay
                box_w, box_h = int(w * 0.72), int(h * 0.36)
                x1, y1 = (w - box_w) // 2, (h - box_h) // 2
                x2, y2 = x1 + box_w, y1 + box_h
                cv2.rectangle(img_bgr, (x1, y1), (x2, y2), (0, 255, 255), 2)
                cv2.putText(
                    img_bgr,
                    "HOLD BARCODE INSIDE BOX",
                    (x1, max(30, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )

        else:
            # --- PHASE 2: SMART OCR AUTO-CAPTURE ---
            if not self.ocr_captured:
                try:
                    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
                    self.latest_sharpness = sharpness

                    if sharpness >= 100.0:
                        self.steady_frames += 1
                        color = (0, 255, 0)
                        status_txt = f"STEADY ({self.steady_frames}/2) - Sharpness: {sharpness:.0f}"
                    else:
                        self.steady_frames = 0
                        color = (0, 165, 255)
                        status_txt = f"HOLD STILL... (Sharpness: {sharpness:.0f} / 100)"

                    cv2.putText(
                        img_bgr,
                        status_txt,
                        (20, 45),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        color,
                        2,
                    )

                    if self.steady_frames >= 2:
                        self.ocr_captured = True
                        clean_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                        self.ocr_queue.put(clean_rgb)
                        logger.info(f"[BarcodeProcessor] Auto-captured steady frame with sharpness {sharpness:.1f}")
                except Exception as exc:
                    logger.error(f"[BarcodeProcessor OCR Sharpness Error]: {exc}\n{traceback.format_exc()}")
            else:
                cv2.putText(
                    img_bgr,
                    "LABEL CAPTURED! RUNNING OCR...",
                    (20, 45),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.85,
                    (0, 255, 0),
                    2,
                )

        return av.VideoFrame.from_ndarray(img_bgr, format="bgr24")


@st.dialog("📋 FSSAI & WHO Dietary Compliance Diagnosis")
def show_diagnosis_dialog(payload_data: Dict[str, Any]):
    """Displays a prominent executive compliance diagnosis modal."""
    alerts = payload_data.get("evidence_based_alerts", [])
    pm = payload_data.get("product_match", {})
    p_name = pm.get("product_name") or "Packaged Food Item"
    brand = pm.get("brand") or "Brand Not Stated"

    st.markdown(f"### Product: **{p_name}** ({brand})")

    if not alerts:
        st.success("✅ **Fully Compliant**: No excessive sugar, sodium, saturated fat, or trans fat detected under WHO and FSSAI dietary limits.")
    else:
        st.markdown("**Compliance Alerts & Health Warnings:**")
        for alt in alerts:
            sev = alt.get("severity", "info").lower()
            title = alt.get("title", "Notice")
            reason = alt.get("reason", "")
            src = alt.get("authority_source", "")
            ref = alt.get("threshold_reference", "")

            if sev in ("critical", "error"):
                st.error(f"🚨 **{title}**\n\n{reason}\n\n*Statutory Reference: {src} ({ref})*")
            elif sev == "warning":
                st.warning(f"⚠️ **{title}**\n\n{reason}\n\n*Reference: {src} ({ref})*")
            else:
                st.info(f"ℹ️ **{title}**\n\n{reason}\n\n*Reference: {src}*")

    st.markdown("---")
    ing = payload_data.get("ingredients", {})
    allergens = ing.get("declared_allergens", [])
    traces = ing.get("potential_traces", [])
    if allergens:
        st.error(f"⚠️ **Declared Major Allergens:** {', '.join(allergens)}")
    if traces:
        st.warning(f"ℹ️ **Precautionary Traces:** {', '.join(traces)}")



def load_ground_truth_samples() -> Dict[str, Any]:
    """Loads benchmark ground truth data from ground_truth_v4.json."""
    gt_path = REPO_ROOT / "tests" / "fixtures" / "real_photos" / "ground_truth_v4.json"
    if gt_path.exists():
        try:
            with open(gt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {s["sample_id"]: s for s in data.get("samples", [])}
        except Exception:
            pass
    return {}


# Preset Test Case Definitions
PRESETS = {
    "None (Custom Upload)": {
        "description": "Upload your own packaging photos or test custom inputs.",
        "nutrition_img": None,
        "ingredients_img": None,
        "barcode": "",
        "package_weight_g": None,
        "expected": {},
    },
    "Preset 1: Sample Biscuit Packet (Full Panel)": {
        "description": "Complete nutrition table + ingredients list + declared allergens (Wheat, Milk, Soy).",
        "nutrition_img": REPO_ROOT / "tests" / "fixtures" / "sample_biscuit_packet.png",
        "ingredients_img": None,
        "barcode": "8901030000001",
        "package_weight_g": 120.0,
        "expected": {
            "energy_kcal": 460.0,
            "protein_g": 7.5,
            "carbohydrates_g": 68.0,
            "sugars_g": 24.5,
            "added_sugars_g": 22.0,
            "total_fat_g": 18.0,
            "saturated_fat_g": 8.5,
            "trans_fat_g": 0.0,
            "dietary_fibre_g": 6.2,
            "sodium_mg": 380.0,
            "salt_g": 0.95,
        },
    },
    "Preset 2: Sample Juice Bottle (Beverage Panel)": {
        "description": "Beverage label with liquid basis (per 100ml) and high sugar alert.",
        "nutrition_img": REPO_ROOT / "tests" / "fixtures" / "sample_juice_bottle.png",
        "ingredients_img": None,
        "barcode": "",
        "package_weight_g": None,
        "expected": {
            "energy_kcal": 54.0,
            "protein_g": 0.2,
            "carbohydrates_g": 13.2,
            "sugars_g": 12.8,
            "total_fat_g": 0.1,
            "sodium_mg": 15.0,
        },
    },
    "Preset 3: Real Photo 01 (French LU Bar - Comma Decimals)": {
        "description": "Real packaging photo with European decimal commas (5,6 g) and per 100g basis.",
        "nutrition_img": REPO_ROOT / "tests" / "fixtures" / "real_photos" / "real_photo_01_7622210449283.jpg",
        "ingredients_img": None,
        "barcode": "7622210449283",
        "package_weight_g": 20.0,
        "expected": {
            "energy_kcal": 467.0,
            "energy_kj": 1962.0,
            "protein_g": 6.3,
            "carbohydrates_g": 69.0,
            "sugars_g": 32.0,
            "total_fat_g": 17.0,
            "saturated_fat_g": 5.6,
            "dietary_fibre_g": 4.0,
            "salt_g": 0.49,
            "sodium_mg": 196.0,
        },
    },
    "Preset 4: Real Photo 02 (Oreo - Multi-Column Panel)": {
        "description": "Two-column label with per 100g and per serving columns.",
        "nutrition_img": REPO_ROOT / "tests" / "fixtures" / "real_photos" / "real_photo_02_0044000032029.jpg",
        "ingredients_img": None,
        "barcode": "0044000032029",
        "package_weight_g": None,
        "expected": {
            "energy_kcal": 471.0,
            "protein_g": 4.7,
            "carbohydrates_g": 71.0,
            "sugars_g": 41.0,
            "total_fat_g": 19.0,
            "saturated_fat_g": 9.4,
            "sodium_mg": 400.0,
        },
    },
    "Preset 5: Real Photo 08 (Sourdough Pasta - High Fibre)": {
        "description": "Real label with high protein and fibre declaration.",
        "nutrition_img": REPO_ROOT / "tests" / "fixtures" / "real_photos" / "real_photo_08_737628064502.jpg",
        "ingredients_img": None,
        "barcode": "737628064502",
        "package_weight_g": None,
        "expected": {
            "energy_kcal": 375.0,
            "protein_g": 14.3,
            "carbohydrates_g": 75.0,
            "sugars_g": 3.6,
            "total_fat_g": 1.8,
            "dietary_fibre_g": 3.6,
            "sodium_mg": 0.0,
        },
    },
    "Preset 6: Barcode Only (Local DB Exact Match 8901030000001)": {
        "description": "Tests Step 1 & 2 barcode-first flow with an exact match from local SQLite DB.",
        "nutrition_img": None,
        "ingredients_img": None,
        "barcode": "8901030000001",
        "package_weight_g": 120.0,
        "expected": {
            "energy_kcal": 460.0,
            "protein_g": 7.5,
            "carbohydrates_g": 68.0,
            "sugars_g": 24.5,
            "total_fat_g": 18.0,
        },
    },
    "Preset 7: Unknown Barcode Fallback Demo (9999999999994)": {
        "description": "Tests Step 2 completeness decision when barcode is unknown, safely prompting label scan.",
        "nutrition_img": None,
        "ingredients_img": None,
        "barcode": "9999999999994",
        "package_weight_g": None,
        "expected": {},
    },
}


def load_global_dataset_presets() -> Dict[str, Any]:
    """Loads verified products from global_packaged_food/global_ground_truth.json."""
    global_gt_path = REPO_ROOT / "datasets" / "evaluation" / "global_packaged_food" / "global_ground_truth.json"
    if global_gt_path.exists():
        try:
            with open(global_gt_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = {}
                for s in data.get("samples", []):
                    img_p = REPO_ROOT / s["local_image_path"]
                    if img_p.exists():
                        name_key = f"🌐 Global: {s['product_name'][:25]} ({s['country']})"
                        nuts = s.get("ground_truth_nutrients_100g", {})
                        expected = {k: v for k, v in nuts.items() if v is not None}
                        res[name_key] = {
                            "description": f"Verified product from {s['country']} ({s['region']}). Barcode: {s['barcode']}.",
                            "nutrition_img": img_p,
                            "ingredients_img": None,
                            "barcode": s["barcode"],
                            "package_weight_g": None,
                            "expected": expected,
                        }
                return res
        except Exception:
            pass
    return {}


def load_tested_images_catalog() -> List[Dict[str, Any]]:
    """Loads metadata for verified food package images from tested_images/metadata.json."""
    candidates_dirs = [
        REPO_ROOT.parent / "tested_images",
        REPO_ROOT / "tested_images",
        REPO_ROOT.parent / "tested images",
    ]
    for d in candidates_dirs:
        meta_file = d / "metadata.json"
        if meta_file.exists():
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    valid_items = []
                    for item in data:
                        p = d / item["filename"]
                        if p.exists():
                            item_copy = dict(item)
                            item_copy["local_path"] = str(p)
                            valid_items.append(item_copy)
                    return valid_items
            except Exception as exc:
                logger.warning(f"Error loading tested_images metadata: {exc}")
    return []


TESTED_IMAGES_CATALOG = load_tested_images_catalog()
GLOBAL_PRESETS = load_global_dataset_presets()
ALL_PRESETS = {**PRESETS, **GLOBAL_PRESETS}


# --- UI HEADER ---
st.markdown('<div class="main-header">🥗 Food Packet Scanner & Label OCR Testing Interface</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-header">Interactive testing workbench for Barcode-First Ingestion, PaddleOCR Nutrition Extraction, Ingredient/Allergen Parsing, and Ground-Truth Evaluation.</div>',
    unsafe_allow_html=True,
)

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("⚙️ Engine Configuration")

# Engine status indicator
try:
    engine = get_engine()
    st.sidebar.success("✅ Food Intelligence Engine Ready")
except Exception as e:
    st.sidebar.error(f"❌ Engine initialization failed: {e}")
    st.stop()

st.sidebar.markdown("---")
st.sidebar.subheader("📂 Select Test Preset")
selected_preset_name = st.sidebar.selectbox(
    "Choose a built-in test case or custom upload:",
    options=list(ALL_PRESETS.keys()),
    index=1,
)
active_preset = ALL_PRESETS[selected_preset_name]
st.sidebar.info(active_preset["description"])

st.sidebar.markdown("---")
st.sidebar.subheader("🔧 Runtime Settings")
allow_online_lookup = st.sidebar.checkbox("Allow Live Open Food Facts API fallback", value=True)
comparison_tolerance = st.sidebar.slider("Evaluation Tolerance (± %)", min_value=1.0, max_value=20.0, value=5.0, step=0.5)

# --- MAIN TABS ---
tab_scan, tab_accuracy, tab_triage, tab_guide = st.tabs([
    "📸 Image & Barcode Scanner",
    "🎯 Accuracy & Ground Truth Evaluator",
    "🗂️ Failure Triage Queue",
    "📖 Testing Guide & Scenarios",
])

with tab_scan:
    col_input, col_output = st.columns([1, 1.25], gap="large")

    with col_input:
        st.subheader("1. Food Package Ingestion & Scanner")

        # Preset image resolution
        default_nut_img = active_preset["nutrition_img"]
        default_ing_img = active_preset["ingredients_img"]
        default_barcode = active_preset["barcode"]

        scan_mode = st.radio(
            "Select Scanner Input Method:",
            [
                "📁 Upload Food Package Photo",
                "📸 Take Photo with Camera",
                "⚡ Quick-Test Verified Real Packets",
                "📹 Real-Time WebRTC Live Video Stream",
                "⌨️ Enter Barcode Digits Manually",
            ],
            index=0,
            help="Upload a photo from your device, take a real-time camera snapshot, or select from verified package dataset.",
        )

        active_image = None
        active_image_label = None
        manual_barcode = default_barcode or ""

        if scan_mode == "📁 Upload Food Package Photo":
            uploaded_file = st.file_uploader(
                "Upload food packet photo (front, back, or full label):",
                type=["png", "jpg", "jpeg", "webp"],
                key="unified_package_uploader",
                help="Accepts any photo of packaged food. Automatically scans barcode and traces nutrition & ingredients.",
            )
            if uploaded_file is not None:
                active_image = uploaded_file
                active_image_label = f"Uploaded Photo: {uploaded_file.name}"
            elif default_nut_img and Path(default_nut_img).exists():
                active_image = default_nut_img
                active_image_label = f"Preset Default: {Path(default_nut_img).name}"

        elif scan_mode == "📸 Take Photo with Camera":
            camera_snap = st.camera_input(
                "📸 Point camera at food package and click 'Take Photo':",
                key="unified_package_camera",
                help="Take a clear snapshot of the food packet. Automatically scans barcode and traces nutrition & ingredients.",
            )
            if camera_snap is not None:
                active_image = camera_snap
                active_image_label = "Camera Snapshot"

        elif scan_mode == "⚡ Quick-Test Verified Real Packets":
            if TESTED_IMAGES_CATALOG:
                c_filt1, c_filt2 = st.columns(2)
                with c_filt1:
                    origin_filter = st.selectbox("Region Filter:", ["All Packets (40)", "India (15)", "USA & World (25)"])

                filtered_catalog = TESTED_IMAGES_CATALOG
                if "India" in origin_filter:
                    filtered_catalog = [it for it in TESTED_IMAGES_CATALOG if it.get("country") == "India"]
                elif "USA" in origin_filter:
                    filtered_catalog = [it for it in TESTED_IMAGES_CATALOG if it.get("country") != "India"]

                tested_options = {
                    f"{'🇮🇳' if it.get('country') == 'India' else '🌐'} {it['filename']}": it
                    for it in filtered_catalog
                }
                sel_label = st.selectbox("Select Verified Test Packet:", options=list(tested_options.keys()))
                sel_pkg = tested_options[sel_label]
                active_image = sel_pkg["local_path"]
                active_image_label = f"Verified Packet: {sel_pkg['filename']}"
                manual_barcode = sel_pkg.get("barcode", "")
            else:
                st.info("No tested_images catalog found; using preset samples.")
                if default_nut_img and Path(default_nut_img).exists():
                    active_image = default_nut_img
                    active_image_label = f"Preset Default: {Path(default_nut_img).name}"

        elif scan_mode == "📹 Real-Time WebRTC Live Video Stream":
            is_ocr_fallback = st.session_state.get("ocr_fallback_mode", False)
            if is_ocr_fallback:
                st.warning("⚠️ **Barcode lookup required label scan.** Point camera at back package label. Hold it steady (>100 sharpness) for auto-capture.")
                if st.button("↩️ Reset to Barcode Scanner Mode"):
                    st.session_state["ocr_fallback_mode"] = False
                    st.rerun()
            else:
                st.caption("Point camera at barcode or label. Stream analyzes video frames in real time:")

            webrtc_ctx = webrtc_streamer(
                key="realtime_scanner_stream",
                mode=WebRtcMode.SENDRECV,
                rtc_configuration=RTC_CONFIGURATION,
                video_processor_factory=BarcodeProcessor,
                media_stream_constraints=MEDIA_STREAM_CONSTRAINTS,
                async_processing=True,
            )

            if webrtc_ctx.video_processor:
                webrtc_ctx.video_processor.ocr_mode = is_ocr_fallback
                try:
                    detected_bc = webrtc_ctx.video_processor.barcode_queue.get_nowait()
                    if detected_bc and detected_bc != st.session_state.get("last_auto_scanned_barcode"):
                        st.session_state["last_auto_scanned_barcode"] = detected_bc
                        t0 = time.time()
                        bc_res = engine.scan_barcode(detected_bc, allow_online=allow_online_lookup)
                        st.session_state["barcode_scan_result"] = bc_res
                        st.session_state["barcode_scan_time"] = time.time() - t0
                        if bc_res.get("action_required") in ("scan_label_required", "scan_label_recommended"):
                            st.session_state["ocr_fallback_mode"] = True
                        else:
                            st.session_state["ocr_fallback_mode"] = False
                        st.rerun()
                except queue.Empty:
                    pass

                try:
                    captured_frame_rgb = webrtc_ctx.video_processor.ocr_queue.get_nowait()
                    if captured_frame_rgb is not None:
                        with st.spinner("Auto-captured steady frame! Running PaddleOCR extraction..."):
                            t0 = time.time()
                            scan_payload = engine.process_image(
                                image_input=captured_frame_rgb,
                                barcode=st.session_state.get("last_auto_scanned_barcode"),
                            )
                            st.session_state["last_scan_payload"] = scan_payload
                            st.session_state["last_scan_time"] = time.time() - t0
                            st.session_state["ocr_fallback_mode"] = False
                            st.rerun()
                except queue.Empty:
                    pass

        else:  # Manual barcode digits
            manual_barcode = st.text_input(
                "Enter Barcode Digits (EAN-13, UPC-A, etc.):",
                value=default_barcode,
                placeholder="e.g. 8901030000001",
                help="Preserves significant leading zeros and verifies checksum.",
            )

        # Image preview & quality audit
        preview_img = None
        if active_image is not None:
            if isinstance(active_image, (str, Path)):
                preview_img = Image.open(str(active_image))
            elif isinstance(active_image, Image.Image):
                preview_img = active_image
            elif hasattr(active_image, "read"):
                file_bytes = active_image.read()
                preview_img = Image.open(io.BytesIO(file_bytes))
                active_image.seek(0)

            if preview_img is not None:
                st.image(preview_img, caption=active_image_label or "Loaded Food Package Image", use_container_width=True)
                from food_engine.validation.triage_logger import check_image_quality
                is_sharp, b_score, b_msg = check_image_quality(preview_img)
                if not is_sharp:
                    st.warning(f"⚠️ **Image Blur Warning** (Sharpness: {b_score:.1f} < 80.0 required). Edge blur may degrade small table text OCR.")
                else:
                    st.caption(f"🔍 Image Edge Sharpness: **{b_score:.1f}** (Passed quality threshold 80.0)")

        # Advanced options expander
        with st.expander("⚙️ Advanced Package Options (Net Weight, Dual-Image Mode, Barcode Override)", expanded=False):
            package_weight = st.number_input(
                "Package Net Weight (g, optional):",
                min_value=0.0,
                value=float(active_preset["package_weight_g"]) if active_preset.get("package_weight_g") else 0.0,
                step=10.0,
                help="Computes package totals (e.g. 120g package scaling)",
            )
            ingredients_file = st.file_uploader(
                "Separate Ingredients Image (Optional - Dual Panel Mode):",
                type=["png", "jpg", "jpeg", "webp"],
                key="dual_ingredients_uploader",
            )
            user_barcode_override = st.text_input(
                "Manual Barcode Override (Optional):",
                value=manual_barcode,
                help="Leave empty to let the scanner automatically detect barcode from the image.",
            )

        # Main Execute Button
        st.markdown("---")
        run_scan = st.button("🚀 Scan & Trace Food Package", type="primary", use_container_width=True)

    with col_output:
        st.subheader("2. Real Engine Results & Diagnostics")

        # Execute Unified Pipeline
        if run_scan:
            target_image = active_image
            target_barcode = user_barcode_override.strip() if user_barcode_override.strip() else None
            net_weight = package_weight if package_weight > 0 else None

            # Prepare bytes for target image
            img_bytes = None
            if target_image is not None:
                if isinstance(target_image, (str, Path)):
                    img_bytes = str(target_image)
                elif hasattr(target_image, "seek"):
                    target_image.seek(0)
                    img_bytes = target_image.read()
                elif hasattr(target_image, "read"):
                    img_bytes = target_image.read()
                elif isinstance(target_image, Image.Image):
                    buf = io.BytesIO()
                    target_image.save(buf, format="PNG")
                    img_bytes = buf.getvalue()

            ing_bytes = None
            if ingredients_file is not None:
                if hasattr(ingredients_file, "seek"):
                    ingredients_file.seek(0)
                    ing_bytes = ingredients_file.read()
                elif hasattr(ingredients_file, "read"):
                    ing_bytes = ingredients_file.read()

            if img_bytes is None and not target_barcode:
                st.error("❌ Please provide a Package Photo (upload or camera snapshot) or enter a Barcode.")
            else:
                with st.spinner("🔍 Scanning package: detecting barcode, running PaddleOCR, parsing nutrition & ingredients..."):
                    t_start = time.time()
                    try:
                        # Step A: Barcode Detection directly from image pixels if not manually overridden
                        detected_bc = target_barcode
                        barcode_notice = None
                        if img_bytes is not None and not target_barcode:
                            detected_bc, bc_err = decode_barcode_from_image(img_bytes)
                            if detected_bc:
                                val_chk = BarcodeValidator.validate(detected_bc)
                                if val_chk.is_valid:
                                    detected_bc = val_chk.normalized_code
                            else:
                                barcode_notice = bc_err

                        # Step B: Unified Pipeline Execution
                        if img_bytes is not None:
                            if ing_bytes is not None:
                                scan_payload = engine.scan_package_label(
                                    nutrition_image=img_bytes,
                                    ingredients_image=ing_bytes,
                                    barcode=detected_bc,
                                    package_weight_g=net_weight,
                                )
                            else:
                                scan_payload = engine.scan_package_label(
                                    label_image=img_bytes,
                                    barcode=detected_bc,
                                    package_weight_g=net_weight,
                                )
                        else:
                            scan_payload = engine.scan_barcode(
                                barcode=detected_bc,
                                allow_online=allow_online_lookup,
                            )

                        # Step C: OCR line fallback if barcode was undetected on pixels
                        final_barcode = scan_payload.get("product_match", {}).get("barcode") or detected_bc
                        if not final_barcode and scan_payload.get("ocr_result", {}).get("lines"):
                            ocr_lines = [l["text"] for l in scan_payload["ocr_result"]["lines"]]
                            recovered_code = BarcodeValidator.extract_barcode_from_ocr_lines(ocr_lines)
                            if recovered_code:
                                final_barcode = recovered_code
                                scan_payload["product_match"]["barcode"] = recovered_code

                        t_total = time.time() - t_start
                        st.session_state["last_scan_payload"] = scan_payload
                        st.session_state["last_scan_time"] = t_total
                        st.session_state["last_scanned_barcode"] = final_barcode
                        st.session_state["last_barcode_notice"] = barcode_notice
                        st.session_state["last_tested_preset"] = selected_preset_name

                    except Exception as exc:
                        st.error(f"❌ Scanner Pipeline Error: {type(exc).__name__}: {exc}")
                        import traceback
                        with st.expander("View Exception Traceback"):
                            st.code(traceback.format_exc())

        # Render Active Payload Results
        if "last_scan_payload" in st.session_state:
            payload = st.session_state["last_scan_payload"]
            exec_time = st.session_state.get("last_scan_time", 0.0)
            pm = payload.get("product_match", {})
            scanned_bc = payload.get("product_match", {}).get("barcode") or st.session_state.get("last_scanned_barcode")

            # 0. Barcode Status Banner (Graceful & Non-blocking)
            if scanned_bc:
                val = BarcodeValidator.validate(scanned_bc)
                if val.is_valid:
                    if pm.get("status") == "exact_barcode_match":
                        st.success(f"🎯 **Barcode Verified:** `{val.normalized_code}` ({val.format}) — Found in Product Database: **{pm.get('product_name')}** ({pm.get('brand', 'Unknown Brand')})")
                    else:
                        st.info(f"🏷️ **Barcode Detected:** `{val.normalized_code}` ({val.format}) — Packaging details traced directly via OCR.")
                else:
                    st.info(f"ℹ️ **Barcode Notice:** `{scanned_bc}` ({val.error_message or 'Unrecognized format'}). Tracing all product information directly from package label via OCR.")
            else:
                st.info("ℹ️ **Barcode unreadable or absent on packaging.** Tracing all nutrition facts, ingredients, allergens, and dietary compliance directly from package label via OCR.")

            # 1. Diagnostic Summary Banner
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("Pipeline Latency", f"{exec_time:.2f} s")
            ocr_res = payload.get("ocr_result", {})
            d2.metric("OCR Lines Detected", ocr_res.get("line_count", 0))
            pm = payload.get("product_match", {})
            d3.metric("Product Match", pm.get("status", "none").upper())
            dq = payload.get("data_quality", {})
            d4.metric("Manual Review Required", "Yes" if dq.get("manual_review_required") else "No")

            # 2. Product Identity
            p_name = pm.get("product_name") or "Product Name Not Detected"
            p_brand = pm.get("brand") or "Brand Not Stated"
            p_barcode = pm.get("barcode") or "None"
            p_source = pm.get("source") or "Physical Packaging Label"

            st.markdown(
                f"""
                <div class="metric-card">
                    <h3 style="margin:0 0 0.5rem 0;">📦 {p_name}</h3>
                    <p style="margin:0 0 0.25rem 0;"><b>Brand:</b> {p_brand} &nbsp;|&nbsp; <b>Barcode:</b> {p_barcode}</p>
                    <p style="margin:0;"><b>Source Authority:</b> {p_source} &nbsp; 
                    <span class="badge-exact-db">{pm.get('match_type', 'none').upper()}</span></p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # --- PHASE 3: TOP-LEVEL COMPLIANCE DIAGNOSIS & MODAL ---
            col_modal_btn, _ = st.columns([1.5, 1])
            with col_modal_btn:
                if st.button("📋 View Final Dietary Diagnosis Modal", type="primary", use_container_width=True):
                    show_diagnosis_dialog(payload)

            st.markdown("### 🏥 FSSAI & WHO Dietary Compliance Diagnosis")
            alerts = payload.get("evidence_based_alerts", [])
            ing = payload.get("ingredients", {})
            decl_allergens = ing.get("declared_allergens", [])

            # High-visibility allergen alert card
            if decl_allergens:
                st.error(f"🚨 **ALLERGEN SAFETY WARNING**: Packaging explicitly declares: **{', '.join(decl_allergens)}**")

            # FSSAI & WHO threshold alerts
            if alerts:
                for alt in alerts:
                    sev = alt.get("severity", "info").lower()
                    t_title = alt.get("title", "Nutrient Alert")
                    r_reason = alt.get("reason", "")
                    s_source = alt.get("authority_source", "")
                    t_ref = alt.get("threshold_reference", "")
                    if sev in ("critical", "error"):
                        st.error(f"🚨 **{t_title}**\n\n{r_reason}\n\n*Statutory Standard: {s_source} ({t_ref})*")
                    elif sev == "warning":
                        st.error(f"⚠️ **{t_title}**\n\n{r_reason}\n\n*Reference: {s_source} ({t_ref})*")
                    else:
                        st.info(f"ℹ️ **{t_title}**\n\n{r_reason}\n\n*Reference: {s_source}*")
            else:
                st.success("✅ **FSSAI & WHO Dietary Compliant**: No excessive sugar, sodium, saturated fat, or industrial trans fat detected.")

            # --- PHASE 3: INTERACTIVE MANUAL OVERRIDE FOR MISSING DATA ---
            missing_fields = payload.get("missing_fields", [])
            manual_review_needed = dq.get("manual_review_required", False)

            if manual_review_needed or missing_fields:
                with st.expander("✏️ Correct or Fill Missing Nutrient Values (Interactive Recalculation)", expanded=False):
                    st.info("Some nutrient fields were missing or flagged. Enter values below to recalculate FSSAI & WHO compliance dynamically:")
                    with st.form("manual_override_form"):
                        fields_to_prompt = list(dict.fromkeys(missing_fields + ["sugars_g", "sodium_mg", "saturated_fat_g", "trans_fat_g", "protein_g", "carbohydrates_g"]))[:6]
                        f_cols = st.columns(3)
                        override_inputs = {}
                        for idx, field in enumerate(fields_to_prompt):
                            c = f_cols[idx % 3]
                            with c:
                                f_label = field.replace("_", " ").title()
                                curr_val = payload.get("nutrition", {}).get("nutrients", {}).get(field, {}).get("value")
                                default_input = float(curr_val) if curr_val is not None else 0.0
                                override_inputs[field] = st.number_input(
                                    f"{f_label}:",
                                    value=default_input,
                                    step=0.5 if "g" in field else 10.0,
                                    min_value=0.0,
                                    key=f"input_override_{field}",
                                )
                        recalc_clicked = st.form_submit_button("🔄 Recalculate Compliance Diagnosis", type="primary")
                        if recalc_clicked:
                            from food_engine.reporting.health_rules import EvidenceBasedHealthRules
                            nuts = payload.get("nutrition", {}).get("nutrients", {})
                            for k_f, v_f in override_inputs.items():
                                if v_f > 0.0 or (nuts.get(k_f, {}).get("value") is not None):
                                    if k_f not in nuts:
                                        nuts[k_f] = {}
                                    nuts[k_f]["value"] = v_f
                                    nuts[k_f]["status"] = "declared"
                                    nuts[k_f]["source"] = "user_manual_override"

                            recalced_alerts = EvidenceBasedHealthRules.evaluate(
                                nutrients=nuts,
                                declared_allergens=ing.get("declared_allergens", []),
                                potential_traces=ing.get("potential_traces", []),
                                basis=payload.get("nutrition", {}).get("basis", "per_100_g"),
                            )
                            payload["evidence_based_alerts"] = recalced_alerts
                            st.session_state["last_scan_payload"] = payload
                            st.success("✅ Dietary compliance diagnosis recalculated!")
                            st.rerun()

            st.markdown("---")

            # 3. Nutrition Facts Table
            st.markdown("### 🥗 Extracted Nutrition Values")
            nut = payload.get("nutrition", {})
            basis_str = nut.get("basis", "per_100_g").replace("_", " ").title()
            serving_raw = nut.get("serving_size_raw")
            if serving_raw:
                st.caption(f"Basis: **{basis_str}** | Declared Serving Size: **{serving_raw}**")
            else:
                st.caption(f"Basis: **{basis_str}**")

            nutrients = nut.get("nutrients", {})
            if nutrients:
                nut_rows = []
                for k, v in nutrients.items():
                    val = v.get("value")
                    unit = v.get("unit", "")
                    status = v.get("status", "missing")
                    src = v.get("source", "label")
                    ub = v.get("upper_bound", False)
                    comp = v.get("comparator", "<") if ub else ""

                    if val is not None:
                        val_display = f"{comp} {val}".strip()
                    else:
                        val_display = "Not Declared"

                    # HTML Badge
                    if status == "declared":
                        badge_html = '<span class="badge-declared">DECLARED</span>'
                    elif status == "calculated":
                        badge_html = '<span class="badge-calculated">CALCULATED</span>'
                    elif status == "reference_derived":
                        badge_html = '<span class="badge-reference">REFERENCE_DB</span>'
                    else:
                        badge_html = '<span class="badge-missing">MISSING</span>'

                    nut_rows.append({
                        "Nutrient": k.replace("_", " ").title(),
                        "Amount": val_display,
                        "Unit": unit,
                        "Status": badge_html,
                        "Provenance / Source": src,
                        "Confidence": f"{v.get('confidence', 0.0):.2f}" if v.get("confidence") else "—",
                    })

                df_nut = pd.DataFrame(nut_rows)
                st.write(df_nut.to_html(escape=False, index=False), unsafe_allow_html=True)
            else:
                st.info("No nutrition facts extracted from input.")

            # 4. Ingredients & Allergens
            st.markdown("### 🌾 Ingredients & Declared Allergens")
            ing = payload.get("ingredients", {})
            decl_allergens = ing.get("declared_allergens", [])
            traces = ing.get("potential_traces", [])

            a_col1, a_col2 = st.columns(2)
            with a_col1:
                st.markdown("**Declared Allergens (on label):**")
                if decl_allergens:
                    for a in decl_allergens:
                        st.error(f"⚠️ {a}")
                else:
                    st.success("None declared on packaging label.")

            with a_col2:
                st.markdown("**Precautionary Traces (May Contain):**")
                if traces:
                    for t in traces:
                        st.warning(f"ℹ️ {t}")
                else:
                    st.info("No trace allergens stated.")

            parsed_items = ing.get("parsed_ingredients", [])
            if parsed_items:
                st.markdown(f"**Parsed Ingredients ({len(parsed_items)} items):**")
                st.write(", ".join([f"`{it}`" for it in parsed_items]))

            raw_ing_text = ing.get("original_text")
            if raw_ing_text:
                with st.expander("View Raw Printed Ingredient Text"):
                    st.text(raw_ing_text)

            # 5. Source Discrepancies
            discrepancies = dq.get("conflicting_fields", [])
            if discrepancies:
                st.markdown("### ⚖️ Source Discrepancies Audit")
                st.warning("Discrepancies >35% detected between label claim and reference baseline:")
                for d in discrepancies:
                    st.write(f"- {d}")

            # 6. Formatted Report and JSON Payload
            with st.expander("📄 View Formatted Human-Readable Report"):
                from food_engine.reporting.output_builder import format_text_report
                st.code(format_text_report(payload), language="text")

            with st.expander("🔍 View Raw Structured JSON Payload"):
                st.json(payload)


with tab_accuracy:
    st.subheader("🎯 Ground Truth & Extraction Accuracy Comparison (Requirement 8)")
    st.markdown(
        """
        <div class="info-callout">
            <b>Distinguishing Execution from Accuracy:</b><br>
            A pipeline run can succeed with 0 runtime errors while still missing or misreading difficult label rows.<br>
            Use this panel to compare extracted values against manually entered or preset ground truth values.
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Pre-populate expected values from selected preset or empty
    preset_expected = active_preset.get("expected", {})

    st.markdown("**Expected Ground Truth Values for Current Test:**")
    exp_col1, exp_col2, exp_col3 = st.columns(3)

    with exp_col1:
        e_kcal = st.number_input("Expected Energy (kcal):", value=float(preset_expected.get("energy_kcal", 0.0)), step=10.0)
        e_prot = st.number_input("Expected Protein (g):", value=float(preset_expected.get("protein_g", 0.0)), step=0.5)
        e_carb = st.number_input("Expected Carbohydrate (g):", value=float(preset_expected.get("carbohydrates_g", 0.0)), step=1.0)

    with exp_col2:
        e_sug = st.number_input("Expected Sugars (g):", value=float(preset_expected.get("sugars_g", 0.0)), step=0.5)
        e_fat = st.number_input("Expected Total Fat (g):", value=float(preset_expected.get("total_fat_g", 0.0)), step=0.5)
        e_sat_fat = st.number_input("Expected Saturated Fat (g):", value=float(preset_expected.get("saturated_fat_g", 0.0)), step=0.5)

    with exp_col3:
        e_sod = st.number_input("Expected Sodium (mg):", value=float(preset_expected.get("sodium_mg", 0.0)), step=10.0)
        e_salt = st.number_input("Expected Salt (g):", value=float(preset_expected.get("salt_g", 0.0)), step=0.1)
        e_fib = st.number_input("Expected Fibre (g):", value=float(preset_expected.get("dietary_fibre_g", 0.0)), step=0.5)

    user_expected = {
        "energy_kcal": e_kcal if e_kcal > 0 else None,
        "protein_g": e_prot if e_prot > 0 else None,
        "carbohydrates_g": e_carb if e_carb > 0 else None,
        "sugars_g": e_sug if e_sug > 0 else None,
        "total_fat_g": e_fat if e_fat > 0 else None,
        "saturated_fat_g": e_sat_fat if e_sat_fat > 0 else None,
        "sodium_mg": e_sod if e_sod > 0 else None,
        "salt_g": e_salt if e_salt > 0 else None,
        "dietary_fibre_g": e_fib if e_fib > 0 else None,
    }

    if "last_scan_payload" not in st.session_state:
        st.info("ℹ️ Please run a scan in the 'Image & Barcode Scanner' tab first to compare extracted values.")
    else:
        payload = st.session_state["last_scan_payload"]
        extracted_nutrients = payload.get("nutrition", {}).get("nutrients", {})

        tp, fp, fn = 0, 0, 0
        eval_rows = []

        all_fields = sorted(list(set(list(user_expected.keys()) + list(extracted_nutrients.keys()))))
        tol_ratio = comparison_tolerance / 100.0

        for field in all_fields:
            exp_val = user_expected.get(field)
            ext_obj = extracted_nutrients.get(field, {})
            ext_val = ext_obj.get("value")

            if exp_val is None and (ext_val is None or ext_obj.get("status") == "missing"):
                continue  # Neither expected nor extracted

            field_label = field.replace("_", " ").title()

            if exp_val is not None and ext_val is not None:
                # Compare with tolerance
                abs_diff = abs(ext_val - exp_val)
                allowed_tol = max(exp_val * tol_ratio, 0.5)
                if abs_diff <= allowed_tol:
                    eval_status = '<span class="badge-correct">CORRECT (TP)</span>'
                    tp += 1
                else:
                    eval_status = f'<span class="badge-incorrect">INCORRECT (FP) (Δ={abs_diff:.2f})</span>'
                    fp += 1
            elif exp_val is not None and ext_val is None:
                eval_status = '<span class="badge-missed">MISSED (FN)</span>'
                fn += 1
            elif exp_val is None and ext_val is not None:
                eval_status = '<span class="badge-incorrect">EXTRA / UNVERIFIED (FP)</span>'
                fp += 1
            else:
                eval_status = "—"

            eval_rows.append({
                "Nutrient Field": field_label,
                "Expected Ground Truth": f"{exp_val}" if exp_val is not None else "Not Specified",
                "Extracted Engine Value": f"{ext_val}" if ext_val is not None else "MISSING",
                "Evaluation": eval_status,
            })

        # Summary Metrics
        st.markdown("### 📊 Field-Level Accuracy Scorecard")
        total_eval = tp + fp + fn
        prec = (tp / (tp + fp)) * 100.0 if (tp + fp) > 0 else 0.0
        rec = (tp / (tp + fn)) * 100.0 if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("True Positives (Correct)", tp)
        m2.metric("False Positives (Incorrect)", fp)
        m3.metric("False Negatives (Missed)", fn)
        m4.metric("Field Precision", f"{prec:.1f}%")
        m5.metric("Field Recall", f"{rec:.1f}%")

        st.write(pd.DataFrame(eval_rows).to_html(escape=False, index=False), unsafe_allow_html=True)


with tab_triage:
    st.subheader("🗂️ Automated Failure Triage & Hard Example Queue (Active Learning)")
    st.markdown(
        """
        When scans encounter blur, unreadable text, low confidence, or physical sanity violations (e.g., Atwater discrepancy),
        they are automatically isolated into the **Triage Queue** with companion JSON sidecars.
        
        - **📷 Bucket A (Camera / Photographic Fault):** Blurry or distorted image. Prompt user to retake photo.
        - **⚙️ Bucket B (Engine / Parser Bug):** Image is sharp, but extraction/normalization missed fields. Added to developer backlog.
        """
    )
    from food_engine.validation.triage_logger import get_triage_summary, TRIAGE_IMAGES_DIR

    triage_info = get_triage_summary()
    tm1, tm2, tm3 = st.columns(3)
    tm1.metric("Total Quarantined Scans", triage_info["total_cases"])
    tm2.metric("📷 Bucket A: Camera Faults", triage_info["bucket_a_image_quality"], help="Blur, glare, or motion degradation")
    tm3.metric("⚙️ Bucket B: Engine Bugs", triage_info["bucket_b_engine_bug"], help="Clean image but parser or dictionary missed values")

    st.markdown("---")
    if triage_info["total_cases"] == 0:
        st.success("No failed or uncertain scans in the quarantine queue.")
    else:
        st.markdown("### 📋 Quarantined Incident Reports")
        cases = triage_info["cases"]
        case_options = [f"{c['triage_id']} | {c.get('suspected_bucket', 'UNKNOWN')} | {c.get('product_name', 'Unknown') or 'Unknown'} ({c.get('failure_reason')})" for c in cases]
        selected_case_str = st.selectbox("Select an incident report to inspect:", options=case_options)
        sel_idx = case_options.index(selected_case_str)
        sel_case = cases[sel_idx]

        t_col_img, t_col_diag = st.columns([1, 1.2])
        with t_col_img:
            st.markdown(f"**Image File: `{sel_case.get('image_file')}`**")
            img_file_path = TRIAGE_IMAGES_DIR / sel_case.get("image_file", "")
            if img_file_path.exists():
                st.image(str(img_file_path), caption=f"Quarantined Image ({sel_case.get('triage_id')})", use_container_width=True)
            else:
                st.info("Image file not available on local disk.")

        with t_col_diag:
            st.markdown(f"**Triage Classification:** `{sel_case.get('suspected_bucket')}`")
            st.info(f"**Category:** {sel_case.get('category_description')}")
            st.write(f"**Recommended Action:** {sel_case.get('recommended_action')}")
            st.write(f"**Sharpness Score:** `{sel_case.get('sharpness_score', 0):.1f}` (Threshold: {sel_case.get('blur_threshold', 80.0)})")
            st.write(f"**Failure Reason:** `{sel_case.get('failure_reason')}`")
            st.write(f"**Timestamp:** `{sel_case.get('timestamp')}`")

            with st.expander("View Full Diagnostic JSON"):
                st.json(sel_case)


with tab_guide:
    st.subheader("📖 Testing Instructions & Workflow Verification (Requirement 9)")
    st.markdown(
        """
        ### 1. Verification of the Barcode-First Flow (Step 1 & 2)
        - **Test Complete Match**: Select `Preset 6: Barcode Only (8901030000001)` and click **Scan Barcode Only**.
          *Notice*: The product is found in the local Open Food Facts database with complete macros. Completeness policy recommends `proceed`.
        - **Test Unknown / Incomplete Barcode**: Select `Preset 7: Unknown Barcode (9999999999994)` and click **Scan Barcode Only**.
          *Notice*: The system confirms the barcode format is valid, detects that no record exists, and safely issues an action decision of `scan_label_required` with missing fields listed.

        ### 2. Verification of Real Pixel OCR Extraction (Steps 3 to 6)
        - **Test Single Full Package**: Select `Preset 1: Sample Biscuit Packet` and click **Run Full Packaging Scanner**.
          *Notice*: Real OCR reads 100% of rows from image pixels. It extracts `460 kcal`, `7.5g protein`, `68g carbohydrates`, parses 7 ingredients, and flags `Wheat`, `Milk`, and `Soy` allergens.
        - **Test European Decimals (`5,6 g`)**: Select `Preset 3: Real Photo 01 (French LU Bar)`.
          *Notice*: The parser accurately detects comma decimals (`5,6 g` saturated fat) without dropping the decimal point.
        - **Test Multi-Column Resolution**: Select `Preset 4: Real Photo 02 (Oreo)`.
          *Notice*: The spatial column detector disambiguates between the per-100g and per-serving columns.

        ### 3. Verification of Data Provenance & Precedence (Step 7)
        - Observe the status badges in the results table:
          - `[DECLARED]`: Directly extracted from the image pixels (highest authority).
          - `[EXACT_DB]`: Derived from exact barcode match without overwriting label values.
          - `[CALCULATED]`: Deterministic stoichiometry (e.g. Sodium calculated from Salt).
          - `[REFERENCE_DB]`: Secondary generic reference from USDA Foundation Foods or IFCT 2017.
          - `[MISSING]`: Clearly marked missing without being converted to zero.

        ### 4. Verification of Safe Offline Operation
        - Disable the **Allow Live Open Food Facts API fallback** checkbox in the sidebar and run queries.
        - The engine continues to operate reliably using local SQLite caches (`products.db` and `nutrient_reference.db`).
        """
    )
