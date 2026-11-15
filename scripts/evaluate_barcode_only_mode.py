"""Evaluates Barcode-Only Image Upload for all 40 verified packaging images.

Tests:
1. Uploading the image of the packet/barcode.
2. Decoding the barcode from image pixels via multi-scale ZXing-C++, CLAHE, OpenCV.
3. Normalization and validation via BarcodeValidator.
4. Database lookup via engine.scan_barcode (checking local SQLite and Open Food Facts dataset).
5. Completeness audit: Does barcode alone provide complete nutrition & ingredients ('proceed'),
   or is nutrition label scanning required/recommended ('scan_label_recommended' / 'scan_label_required')?
"""

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.engine import FoodIntelligenceEngine
from food_engine.validation.barcode_validator import BarcodeValidator
from app import decode_barcode_from_image, load_tested_images_catalog


def main():
    catalog = load_tested_images_catalog()
    if not catalog:
        print("ERROR: tested_images catalog not found.")
        sys.exit(1)

    engine = FoodIntelligenceEngine(repo_root=REPO_ROOT)
    results = []

    print(f"Evaluating Barcode-Only Image Upload for {len(catalog)} packaging images...\n")
    print(f"{'Test ID':<9} | {'Filename':<35} | {'Detected BC':<14} | {'Valid?':<6} | {'DB Match?':<10} | {'Action':<22} | {'Complete?'}")
    print("-" * 115)

    barcode_detected_cnt = 0
    valid_format_cnt = 0
    exact_match_cnt = 0
    complete_proceed_cnt = 0
    needed_nutrition_cnt = 0

    for idx, item in enumerate(catalog, 1):
        test_id = f"TEST-{idx:02d}"
        fname = item["filename"]
        country = item.get("country", "World")
        expected_bc = item.get("barcode")
        local_path = item["local_path"]

        t0 = time.time()
        detected_bc, decode_err = decode_barcode_from_image(local_path)
        latency = round(time.time() - t0, 3)

        val_obj = None
        is_valid = False
        format_name = None
        norm_code = None
        match_status = "unmatched"
        product_name = None
        action_required = "scan_label_required"
        is_complete = False
        completeness_score = 0.0
        missing_fields = []

        if detected_bc:
            barcode_detected_cnt += 1
            val_obj = BarcodeValidator.validate(detected_bc)
            is_valid = val_obj.is_valid
            format_name = val_obj.format
            norm_code = val_obj.normalized_code
            if is_valid:
                valid_format_cnt += 1

            # Engine scan_barcode
            bc_res = engine.scan_barcode(detected_bc, allow_online=False)
            pm = bc_res.get("product_match", {})
            audit = bc_res.get("completeness_audit", {})
            action_required = bc_res.get("action_required", "scan_label_required")
            is_complete = audit.get("is_complete", False)
            completeness_score = audit.get("completeness_score", 0.0)
            missing_fields = audit.get("missing_fields", [])

            if pm.get("status") == "exact_barcode_match":
                exact_match_cnt += 1
                match_status = "EXACT_MATCH"
                product_name = pm.get("product_name")

            if action_required == "proceed" and is_complete:
                complete_proceed_cnt += 1
            else:
                needed_nutrition_cnt += 1
        else:
            needed_nutrition_cnt += 1

        rec = {
            "test_id": test_id,
            "filename": fname,
            "country": country,
            "expected_barcode": expected_bc,
            "detected_barcode": detected_bc,
            "normalized_barcode": norm_code,
            "barcode_format": format_name,
            "is_valid_format": is_valid,
            "db_match_status": match_status,
            "product_name": product_name,
            "completeness_score": completeness_score,
            "is_complete_in_db": is_complete,
            "action_required": action_required,
            "barcode_alone_gave_info": (action_required == "proceed" and is_complete),
            "needed_nutrition_scan": not (action_required == "proceed" and is_complete),
            "decode_latency_sec": latency,
            "decode_error": decode_err,
        }
        results.append(rec)

        bc_disp = str(detected_bc) if detected_bc else "NONE"
        valid_disp = "YES" if is_valid else "NO"
        complete_disp = "YES (Complete)" if rec["barcode_alone_gave_info"] else "NO (Scan Needed)"
        print(f"{test_id:<9} | {fname[:35]:<35} | {bc_disp:<14} | {valid_disp:<6} | {match_status:<10} | {action_required:<22} | {complete_disp}")

    total = len(catalog)
    print("\n" + "=" * 80)
    print("BARCODE-ONLY IMAGE UPLOAD EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Total Packaging Images Tested:                         {total}")
    print(f"Barcodes Successfully Detected from Image Pixels:      {barcode_detected_cnt} / {total} ({barcode_detected_cnt/total*100:.1f}%)")
    print(f"Valid Standard Formats (EAN-13, UPC-A, etc.):          {valid_format_cnt} / {total} ({valid_format_cnt/total*100:.1f}%)")
    print(f"Products Found in Local/Open Food Facts DB:           {exact_match_cnt} / {total} ({exact_match_cnt/total*100:.1f}%)")
    print(f"Times Barcode Alone Gave Complete Information:         {complete_proceed_cnt} / {total} ({complete_proceed_cnt/total*100:.1f}%)")
    print(f"Times Needed to Get Nutrition via Label OCR:           {needed_nutrition_cnt} / {total} ({needed_nutrition_cnt/total*100:.1f}%)")
    print("=" * 80)

    out_file = REPO_ROOT / "datasets" / "evaluation" / "barcode_only_evaluation_results.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    summary_data = {
        "total_images_tested": total,
        "barcodes_detected_from_image": barcode_detected_cnt,
        "barcode_detection_rate_pct": round(barcode_detected_cnt / total * 100, 1),
        "valid_barcode_formats": valid_format_cnt,
        "products_matched_in_database": exact_match_cnt,
        "barcode_alone_gave_complete_information": complete_proceed_cnt,
        "barcode_alone_success_rate_pct": round(complete_proceed_cnt / total * 100, 1),
        "needed_nutrition_label_scan": needed_nutrition_cnt,
        "needed_nutrition_scan_rate_pct": round(needed_nutrition_cnt / total * 100, 1),
        "results": results,
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)
    print(f"Saved results to: {out_file}")


if __name__ == "__main__":
    main()
