"""Food Intelligence Engine - Local Image Testing Interface.

A standalone Streamlit testing workbench for packaged-food barcode lookup,
PaddleOCR nutrition-label extraction, ingredient and allergen parsing,
nutrient data enrichment, and ground-truth accuracy evaluation.
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
from PIL import Image
import streamlit as st

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


def decode_barcode_from_image(image_input: Any) -> Tuple[Optional[str], Optional[str]]:
    """Attempts to decode 1D barcode directly from image pixels using OpenCV."""
    try:
        if isinstance(image_input, (str, Path)):
            cv_img = cv2.imread(str(image_input))
        elif isinstance(image_input, Image.Image):
            cv_img = cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
        elif hasattr(image_input, "read"):
            file_bytes = np.frombuffer(image_input.read(), np.uint8)
            cv_img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            image_input.seek(0)
        elif isinstance(image_input, np.ndarray):
            cv_img = image_input
        else:
            return None, "Unsupported image object for barcode detection."

        if cv_img is None:
            return None, "Failed to load image pixels for barcode detection."

        detector = cv2.barcode.BarcodeDetector()
        res = detector.detectAndDecode(cv_img)
        # OpenCV 4.10 returns (decoded_info, decoded_type, points)
        if len(res) == 3:
            decoded_info, decoded_type, _ = res
            if decoded_info:
                code_str = str(decoded_info).strip()
                if code_str:
                    return code_str, None
        return None, "No barcode detected by 1D scanner."
    except Exception as exc:
        return None, f"Barcode scanner error: {exc}"


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
        st.subheader("1. Ingestion & Image Inputs")

        # Preset image resolution
        default_nut_img = active_preset["nutrition_img"]
        default_ing_img = active_preset["ingredients_img"]
        default_barcode = active_preset["barcode"]

        # Option: Barcode input (Text or Image)
        st.markdown("**Product Barcode (Step 1)**")
        barcode_input_col, barcode_upload_col = st.columns([1.2, 1])

        with barcode_input_col:
            user_barcode = st.text_input(
                "Enter barcode digits (EAN-13, UPC-A, etc.):",
                value=default_barcode,
                placeholder="e.g. 8901030000001",
                help="Preserves significant leading zeros and verifies checksum.",
            )

        with barcode_upload_col:
            barcode_img_file = st.file_uploader(
                "Or upload barcode image:",
                type=["png", "jpg", "jpeg", "webp"],
                key="barcode_uploader",
                help="Automatically decodes 1D barcode with OpenCV.",
            )

        # Handle barcode image decoding if uploaded
        if barcode_img_file is not None:
            detected_bc, bc_err = decode_barcode_from_image(barcode_img_file)
            if detected_bc:
                st.success(f"🔍 Barcode detected from image: **{detected_bc}**")
                user_barcode = detected_bc
            elif bc_err:
                st.warning(f"Barcode image note: {bc_err}. You can type it manually above.")

        # Quick Barcode-Only Check Button
        if st.button("🔍 Step 1: Scan Barcode Only", help="Run fast database lookup without OCR"):
            if not user_barcode.strip():
                st.error("Please enter or upload a barcode to run Step 1.")
            else:
                with st.spinner("Checking barcode and completeness policy..."):
                    t0 = time.time()
                    bc_res = engine.scan_barcode(user_barcode, allow_online=allow_online_lookup)
                    t_elapsed = time.time() - t0

                st.session_state["barcode_scan_result"] = bc_res
                st.session_state["barcode_scan_time"] = t_elapsed

        st.markdown("---")
        st.markdown("**Package Label Images (Step 3)**")
        st.caption("Upload either a single back-of-package label, or test with separate nutrition and ingredient photos.")

        # Nutrition image uploader
        nutrition_file = st.file_uploader(
            "Upload Nutrition Facts Label (Required for OCR):",
            type=["png", "jpg", "jpeg", "webp"],
            key="nutrition_uploader",
        )

        # Ingredients image uploader (Optional)
        ingredients_file = st.file_uploader(
            "Upload Ingredients Panel (Optional - Dual Panel Mode):",
            type=["png", "jpg", "jpeg", "webp"],
            key="ingredients_uploader",
        )

        package_weight = st.number_input(
            "Package Net Weight (g, optional):",
            min_value=0.0,
            value=float(active_preset["package_weight_g"]) if active_preset["package_weight_g"] else 0.0,
            step=10.0,
            help="Computes package totals (e.g. 120g package scaling)",
        )

        # Preview loaded images
        preview_img = None
        if nutrition_file is not None:
            preview_img = Image.open(nutrition_file)
            st.image(preview_img, caption="Uploaded Nutrition Label", use_container_width=True)
        elif default_nut_img and Path(default_nut_img).exists():
            preview_img = Image.open(default_nut_img)
            st.image(preview_img, caption=f"Preset Image: {Path(default_nut_img).name}", use_container_width=True)

        if preview_img is not None:
            from food_engine.validation.triage_logger import calculate_blur_score, check_image_quality
            is_sharp, b_score, b_msg = check_image_quality(preview_img)
            if not is_sharp:
                st.warning(f"⚠️ **Image Blur Detected** (Sharpness Score: {b_score:.1f} < 80.0 required). Edge blur may degrade OCR extraction.")
            else:
                st.caption(f"🔍 Image Edge Sharpness: **{b_score:.1f}** (Passed quality threshold 80.0)")

        if ingredients_file is not None:
            ing_preview = Image.open(ingredients_file)
            st.image(ing_preview, caption="Uploaded Ingredients Panel", use_container_width=True)

        # Main Execute Button
        st.markdown("---")
        run_scan = st.button("🚀 Run Full Packaging Scanner", type="primary", use_container_width=True)

    with col_output:
        st.subheader("2. Real Engine Results & Diagnostics")

        # Display Barcode Scan result if triggered
        if "barcode_scan_result" in st.session_state:
            bc_res = st.session_state["barcode_scan_result"]
            st.markdown("### 🏷️ Step 1 & 2: Barcode Lookup Result")
            val = bc_res.get("barcode_validation", {})
            audit = bc_res.get("completeness_audit", {})
            action = bc_res.get("action_required", "unknown")

            b_col1, b_col2, b_col3 = st.columns(3)
            b_col1.metric("Barcode Valid", "Yes" if val.get("is_valid") else "No", delta=val.get("format"))
            b_col2.metric("Completeness Score", f"{audit.get('completeness_score', 0):.0%}")
            b_col3.metric("Action Decision", action.upper())

            if val.get("is_valid"):
                pm = bc_res.get("product_match", {})
                if pm.get("status") == "exact_barcode_match":
                    st.success(f"**Found in Database:** {pm.get('product_name')} by {pm.get('brand', 'Unknown')} ({pm.get('source')})")
                else:
                    st.warning(f"**Unknown Barcode in DB:** {bc_res.get('prompt_message')}")
            else:
                st.error(f"**Invalid Barcode:** {val.get('error_message')}")

            with st.expander("View Completeness Audit Details"):
                st.write("**Present Fields:**", audit.get("present_fields", []))
                st.write("**Missing Fields:**", audit.get("missing_fields", []))
                st.write("**Reasons for Recommendation:**", audit.get("recommendation_reasons", []))

            st.markdown("---")

        # Execute Full Pipeline
        if run_scan:
            target_nut_img = nutrition_file
            if target_nut_img is None and default_nut_img and Path(default_nut_img).exists():
                target_nut_img = default_nut_img

            if target_nut_img is None and not user_barcode.strip():
                st.error("❌ Please provide either a Nutrition Label Image or a Barcode to run the scanner.")
            else:
                with st.spinner("Processing packaging through OCR, table parser, and fusion engine..."):
                    t_start = time.time()
                    try:
                        clean_barcode = user_barcode.strip() if user_barcode.strip() else None
                        net_weight = package_weight if package_weight > 0 else None

                        if target_nut_img is not None:
                            # Package label OCR workflow (single or dual image)
                            if ingredients_file is not None:
                                scan_payload = engine.scan_package_label(
                                    nutrition_image=target_nut_img,
                                    ingredients_image=ingredients_file,
                                    barcode=clean_barcode,
                                    package_weight_g=net_weight,
                                )
                            else:
                                scan_payload = engine.scan_package_label(
                                    label_image=target_nut_img,
                                    barcode=clean_barcode,
                                    package_weight_g=net_weight,
                                )
                        else:
                            # Barcode only workflow
                            scan_payload = engine.scan_barcode(
                                barcode=clean_barcode,
                                allow_online=allow_online_lookup,
                            )

                        t_total = time.time() - t_start
                        st.session_state["last_scan_payload"] = scan_payload
                        st.session_state["last_scan_time"] = t_total
                        st.session_state["last_tested_preset"] = selected_preset_name

                    except Exception as exc:
                        st.error(f"❌ Engine Pipeline Error: {type(exc).__name__}: {exc}")
                        import traceback
                        with st.expander("View Exception Traceback"):
                            st.code(traceback.format_exc())

        # Render Active Payload Results
        if "last_scan_payload" in st.session_state:
            payload = st.session_state["last_scan_payload"]
            exec_time = st.session_state.get("last_scan_time", 0.0)

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

            # 5. Evidence-based Health Alerts
            alerts = payload.get("evidence_based_alerts", [])
            if alerts:
                st.markdown("### ⚠️ Evidence-Based Health Alerts (WHO / FSSAI)")
                for alt in alerts:
                    sev = alt.get("severity", "info").lower()
                    if sev == "warning":
                        st.warning(f"**{alt.get('title')}:** {alt.get('reason')}")
                    else:
                        st.info(f"**{alt.get('title')}:** {alt.get('reason')}")

            # 6. Source Discrepancies
            discrepancies = dq.get("conflicting_fields", [])
            if discrepancies:
                st.markdown("### ⚖️ Source Discrepancies Audit")
                st.warning("Discrepancies >35% detected between label claim and reference baseline:")
                for d in discrepancies:
                    st.write(f"- {d}")

            # 7. Formatted Report and JSON Payload
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
