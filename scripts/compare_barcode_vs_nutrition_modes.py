"""Comprehensive comparative benchmark: Barcode-Only Image Upload vs. Full Nutrition Label OCR.

Evaluates:
1. Condition A (Barcode-Only Image Upload):
   - Upload image of package/barcode.
   - Decode barcode from image pixels via multi-scale ZXing-C++, CLAHE, OpenCV.
   - Run BarcodeValidator format & checksum verification.
   - Run database lookup & completeness audit (engine.scan_barcode).
   - Record whether barcode-only gave complete information ('proceed') or whether nutrition label scan was needed ('scan_label_recommended' / 'scan_label_required').

2. Condition B (Full Package Label / Nutrition OCR Scan):
   - Run PaddleOCR PP-OCRv4 label extraction (engine.process_image).
   - Extract nutrition facts table, ingredients, allergens, and dietary compliance diagnosis.
   - Record whether OCR succeeded in recovering physical label data.

3. Merged Report:
   - Side-by-side comparison for all 40 test samples.
   - Exact counts of:
     * Barcode alone gave information vs. Needed nutrition scan.
     * Barcode detected vs undetected on image.
     * Nutrition table extracted vs missed.
     * Successes and failures for both modes.
"""

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.engine import FoodIntelligenceEngine
from food_engine.validation.barcode_validator import BarcodeValidator
from app import decode_barcode_from_image, load_tested_images_catalog


def run_comparative_benchmark():
    catalog = load_tested_images_catalog()
    if not catalog:
        print("ERROR: tested_images catalog not found.")
        sys.exit(1)

    print(f"Loaded {len(catalog)} test packaging images.")
    engine = FoodIntelligenceEngine(repo_root=REPO_ROOT)

    # Check if partial or full OCR results exist from task-483
    ocr_cache_path = REPO_ROOT / "datasets" / "evaluation" / "tested_images_comprehensive_report.json"
    cached_ocr = {}
    if ocr_cache_path.exists():
        try:
            with open(ocr_cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for r in data.get("results", []):
                    cached_ocr[r["filename"]] = r
        except Exception:
            pass

    records = []
    
    # Statistics counters
    total_samples = len(catalog)
    barcode_detected_from_image = 0
    barcode_valid_format = 0
    barcode_found_in_db = 0
    barcode_only_complete_proceed = 0
    needed_nutrition_scan = 0
    
    nutrition_ocr_successful = 0
    allergens_detected_count = 0
    health_alerts_evaluated_count = 0

    print("=" * 75)
    print("STARTING COMPARATIVE BENCHMARK: BARCODE-ONLY VS NUTRITION OCR")
    print("=" * 75)

    for idx, item in enumerate(catalog, 1):
        fname = item["filename"]
        country = item.get("country", "World")
        expected_bc = item.get("barcode")
        local_path = item["local_path"]

        # -------------------------------------------------------------
        # CONDITION A: BARCODE-ONLY IMAGE UPLOAD (Scan Barcode Only)
        # -------------------------------------------------------------
        t_bc_start = time.time()
        detected_bc, decode_err = decode_barcode_from_image(local_path)
        t_bc_decode = round(time.time() - t_bc_start, 3)

        bc_valid = False
        bc_format = None
        bc_normalized = None
        bc_match_status = "unmatched"
        bc_product_name = None
        bc_completeness_score = 0.0
        bc_action_required = "scan_label_required"
        barcode_only_success = False

        if detected_bc:
            barcode_detected_from_image += 1
            val_res = BarcodeValidator.validate(detected_bc)
            bc_valid = val_res.is_valid
            bc_format = val_res.format
            bc_normalized = val_res.normalized_code

            if bc_valid:
                barcode_valid_format += 1

            # Database lookup & completeness audit
            bc_scan = engine.scan_barcode(detected_bc, allow_online=False)
            pm = bc_scan.get("product_match", {})
            audit = bc_scan.get("completeness_audit", {})
            bc_action_required = bc_scan.get("action_required", "scan_label_required")
            bc_completeness_score = audit.get("completeness_score", 0.0)

            if pm.get("status") == "exact_barcode_match":
                barcode_found_in_db += 1
                bc_match_status = "exact_match"
                bc_product_name = pm.get("product_name")

            if bc_action_required == "proceed" and audit.get("is_complete"):
                barcode_only_complete_proceed += 1
                barcode_only_success = True
            else:
                needed_nutrition_scan += 1
        else:
            # Barcode not decoded on image -> needed nutrition label scan
            needed_nutrition_scan += 1

        # -------------------------------------------------------------
        # CONDITION B: FULL PACKAGE LABEL / NUTRITION OCR SCAN
        # -------------------------------------------------------------
        ocr_lines_cnt = 0
        nutrients_extracted = []
        ingredients_cnt = 0
        allergens = []
        alerts = []
        ocr_success = False
        ocr_latency = 0.0

        if fname in cached_ocr:
            c = cached_ocr[fname]
            ocr_lines_cnt = c.get("ocr_lines_count", 0)
            nutrients_extracted = c.get("nutrients_extracted", [])
            ingredients_cnt = c.get("ingredients_count", 0)
            allergens = c.get("declared_allergens", [])
            alerts = c.get("health_alerts", [])
            ocr_latency = c.get("latency_sec", 0.0)
            if ocr_lines_cnt > 0 and (len(nutrients_extracted) > 0 or ingredients_cnt > 0):
                ocr_success = True
        else:
            # If not yet cached, run engine process_image
            t_ocr_start = time.time()
            try:
                payload = engine.process_image(image_input=local_path, barcode=detected_bc)
                ocr_latency = round(time.time() - t_ocr_start, 2)
                ocr_lines_cnt = payload.get("ocr_result", {}).get("line_count", 0)
                nuts = payload.get("nutrition", {}).get("nutrients", {})
                nutrients_extracted = [k for k, v in nuts.items() if v.get("value") is not None]
                ing = payload.get("ingredients", {})
                ingredients_cnt = len(ing.get("parsed_ingredients", []))
                allergens = ing.get("declared_allergens", [])
                alerts = [a.get("title") for a in payload.get("evidence_based_alerts", [])]
                if ocr_lines_cnt > 0 and (len(nutrients_extracted) > 0 or ingredients_cnt > 0):
                    ocr_success = True
            except Exception as e:
                ocr_latency = round(time.time() - t_ocr_start, 2)
                print(f"OCR Error on {fname}: {e}")

        if ocr_success:
            nutrition_ocr_successful += 1
        if allergens:
            allergens_detected_count += 1
        if alerts:
            health_alerts_evaluated_count += 1

        # Status categorization
        reason_label_needed = []
        if not detected_bc:
            reason_label_needed.append("Barcode not visible on cropped panel")
        elif not bc_valid:
            reason_label_needed.append("Barcode checksum/format invalid")
        elif bc_match_status != "exact_match":
            reason_label_needed.append("Barcode not found in local DB")
        elif not barcode_only_success:
            reason_label_needed.append("DB record missing nutrition macros")

        rec = {
            "test_id": f"TEST-{idx:02d}",
            "filename": fname,
            "country": country,
            "expected_barcode": expected_bc,
            # Condition A: Barcode-Only
            "barcode_detected": detected_bc,
            "barcode_format": bc_format,
            "barcode_valid": bc_valid,
            "barcode_db_match": bc_match_status,
            "db_product_name": bc_product_name,
            "barcode_only_info_complete": barcode_only_success,
            "action_required": bc_action_required,
            "needed_nutrition_scan": not barcode_only_success,
            "reason_nutrition_needed": ", ".join(reason_label_needed) if not barcode_only_success else "None (Complete in DB)",
            # Condition B: Nutrition Label OCR
            "ocr_lines_count": ocr_lines_cnt,
            "nutrients_extracted_count": len(nutrients_extracted),
            "nutrients_extracted": nutrients_extracted,
            "ingredients_count": ingredients_cnt,
            "allergens": allergens,
            "health_alerts": alerts,
            "nutrition_ocr_successful": ocr_success,
            "ocr_latency_sec": ocr_latency,
        }
        records.append(rec)

        status_str = "PROCEED (DB Complete)" if barcode_only_success else f"NEEDED NUTRITION SCAN ({rec['reason_nutrition_needed']})"
        print(f"[{idx:02d}/40] {fname[:35]:<35} | Barcode: {str(detected_bc):<14} | BC-Only: {status_str} | OCR Nutrients: {len(nutrients_extracted)}")

    # Summary Statistics
    summary = {
        "benchmark_title": "Comparative Analysis: Barcode-Only Image Upload vs. Full Nutrition Label OCR",
        "total_images_tested": total_samples,
        "barcode_only_workflow": {
            "images_tested": total_samples,
            "barcodes_detected_from_image": barcode_detected_from_image,
            "barcode_detection_rate_pct": round(barcode_detected_from_image / total_samples * 100, 1),
            "valid_barcode_formats": barcode_valid_format,
            "products_matched_in_database": barcode_found_in_db,
            "barcode_alone_gave_complete_information": barcode_only_complete_proceed,
            "barcode_alone_success_rate_pct": round(barcode_only_complete_proceed / total_samples * 100, 1),
            "needed_nutrition_label_scan": needed_nutrition_scan,
            "needed_nutrition_scan_rate_pct": round(needed_nutrition_scan / total_samples * 100, 1),
            "reasons_for_nutrition_scan_needed": {
                "barcode_not_in_database": sum(1 for r in records if r["barcode_detected"] and r["barcode_db_match"] != "exact_match"),
                "barcode_unreadable_or_absent_on_image": sum(1 for r in records if not r["barcode_detected"]),
                "db_record_incomplete_missing_macros": sum(1 for r in records if r["barcode_db_match"] == "exact_match" and not r["barcode_only_info_complete"]),
            }
        },
        "nutrition_label_ocr_workflow": {
            "images_tested": total_samples,
            "successful_ocr_extractions": nutrition_ocr_successful,
            "ocr_success_rate_pct": round(nutrition_ocr_successful / total_samples * 100, 1),
            "samples_with_declared_allergens": allergens_detected_count,
            "samples_with_health_compliance_alerts": health_alerts_evaluated_count,
            "average_ocr_latency_sec": round(sum(r["ocr_latency_sec"] for r in records) / max(total_samples, 1), 2),
        },
        "records": records,
    }

    out_path = REPO_ROOT / "datasets" / "evaluation" / "comparative_barcode_vs_nutrition_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 75)
    print("COMPARATIVE BENCHMARK SUMMARY")
    print("=" * 75)
    print(f"Total Packaging Images Tested:               {total_samples}")
    print(f"Barcodes Detected from Image Pixels:        {barcode_detected_from_image} ({summary['barcode_only_workflow']['barcode_detection_rate_pct']}%)")
    print(f"Products Found in Local/OFF Database:       {barcode_found_in_db}")
    print(f"Barcode Alone Gave Complete Information:    {barcode_only_complete_proceed} ({summary['barcode_only_workflow']['barcode_alone_success_rate_pct']}%)")
    print(f"Times Needed to Get Nutrition via OCR:      {needed_nutrition_scan} ({summary['barcode_only_workflow']['needed_nutrition_scan_rate_pct']}%)")
    print(f"Nutrition Label OCR Extraction Success:     {nutrition_ocr_successful} ({summary['nutrition_label_ocr_workflow']['ocr_success_rate_pct']}%)")
    print(f"Report written to: {out_path}")


if __name__ == "__main__":
    run_comparative_benchmark()
