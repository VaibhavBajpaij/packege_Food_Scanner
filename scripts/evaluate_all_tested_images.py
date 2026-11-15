"""Batch testing script to evaluate Food Intelligence Engine on all 40 verified test images."""

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


def main():
    catalog = load_tested_images_catalog()
    if not catalog:
        print("ERROR: No tested images catalog found.")
        sys.exit(1)

    print(f"Loaded {len(catalog)} verified test images from catalog.")
    engine = FoodIntelligenceEngine(repo_root=REPO_ROOT)

    results = []
    t_start_all = time.time()

    for idx, item in enumerate(catalog, 1):
        filename = item["filename"]
        country = item.get("country", "World")
        expected_bc = item.get("barcode")
        local_path = item["local_path"]

        print(f"[{idx}/{len(catalog)}] Testing: {filename} ({country})...", end=" ", flush=True)
        t0 = time.time()
        res_record = {
            "index": idx,
            "filename": filename,
            "country": country,
            "expected_barcode": expected_bc,
            "detected_barcode": None,
            "barcode_match": False,
            "ocr_lines_count": 0,
            "nutrients_extracted_count": 0,
            "nutrients_extracted": [],
            "ingredients_count": 0,
            "declared_allergens": [],
            "health_alerts": [],
            "latency_sec": 0.0,
            "status": "PASS",
            "notes": "",
        }

        try:
            # 1. Barcode decoding
            code, bc_err = decode_barcode_from_image(local_path)
            res_record["detected_barcode"] = code
            if code and expected_bc:
                val = BarcodeValidator.validate(code)
                exp_val = BarcodeValidator.validate(expected_bc)
                res_record["barcode_match"] = (val.normalized_code == exp_val.normalized_code) or (code == expected_bc)
            elif code:
                res_record["barcode_match"] = True

            # 2. Complete label OCR & intelligence extraction
            payload = engine.process_image(image_input=local_path, barcode=code)
            res_record["latency_sec"] = round(time.time() - t0, 2)

            ocr_res = payload.get("ocr_result", {})
            res_record["ocr_lines_count"] = ocr_res.get("line_count", 0)

            # Check if OCR line barcode was recovered if pixel decode was None
            if not res_record["detected_barcode"]:
                ocr_code = payload.get("product_match", {}).get("barcode")
                if ocr_code:
                    res_record["detected_barcode"] = ocr_code
                    if expected_bc:
                        res_record["barcode_match"] = (ocr_code == expected_bc)

            # Nutrients
            nuts = payload.get("nutrition", {}).get("nutrients", {})
            ext_nuts = [k for k, v in nuts.items() if v.get("value") is not None]
            res_record["nutrients_extracted_count"] = len(ext_nuts)
            res_record["nutrients_extracted"] = ext_nuts

            # Ingredients & Allergens
            ing = payload.get("ingredients", {})
            parsed_ing = ing.get("parsed_ingredients", [])
            res_record["ingredients_count"] = len(parsed_ing)
            res_record["declared_allergens"] = ing.get("declared_allergens", [])

            # Alerts
            alerts = payload.get("evidence_based_alerts", [])
            res_record["health_alerts"] = [a.get("title") for a in alerts]

            # Quality Assessment
            if res_record["ocr_lines_count"] > 0 and (res_record["nutrients_extracted_count"] > 0 or res_record["ingredients_count"] > 0):
                res_record["status"] = "PASS"
                print(f"PASS (OCR: {res_record['ocr_lines_count']} lines, Nutrients: {res_record['nutrients_extracted_count']}, Latency: {res_record['latency_sec']}s)")
            else:
                res_record["status"] = "WARN"
                print(f"WARN (OCR: {res_record['ocr_lines_count']} lines, Nutrients: {res_record['nutrients_extracted_count']})")

        except Exception as exc:
            res_record["status"] = "FAIL"
            res_record["notes"] = f"{type(exc).__name__}: {exc}"
            print(f"FAIL: {exc}")

        results.append(res_record)

    total_time = round(time.time() - t_start_all, 2)
    print("\n" + "=" * 60)
    print(f"EVALUATION COMPLETE ({len(results)} images in {total_time}s)")
    print("=" * 60)

    # Summary calculations
    total_imgs = len(results)
    pass_count = sum(1 for r in results if r["status"] == "PASS")
    bc_detected_count = sum(1 for r in results if r["detected_barcode"] is not None)
    nut_extracted_count = sum(1 for r in results if r["nutrients_extracted_count"] > 0)
    alerts_triggered_count = sum(1 for r in results if len(r["health_alerts"]) > 0)
    avg_latency = round(sum(r["latency_sec"] for r in results) / max(total_imgs, 1), 2)

    summary = {
        "total_images_tested": total_imgs,
        "successful_scans": pass_count,
        "success_rate_percent": round(pass_count / total_imgs * 100.0, 1),
        "barcodes_detected": bc_detected_count,
        "barcode_detection_rate": round(bc_detected_count / total_imgs * 100.0, 1),
        "nutrition_tables_extracted": nut_extracted_count,
        "nutrition_extraction_rate": round(nut_extracted_count / total_imgs * 100.0, 1),
        "dietary_compliance_alerts_evaluated": alerts_triggered_count,
        "average_latency_sec": avg_latency,
        "total_evaluation_time_sec": total_time,
        "results": results,
    }

    out_file = REPO_ROOT / "datasets" / "evaluation" / "tested_images_comprehensive_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Summary JSON report saved to: {out_file}")
    print(f"Overall Success Rate: {summary['success_rate_percent']}%")
    print(f"Nutrition Table Extraction Rate: {summary['nutrition_extraction_rate']}%")
    print(f"Barcode Detection: {bc_detected_count}/{total_imgs}")
    print(f"Average Latency: {avg_latency}s")


if __name__ == "__main__":
    main()
