#!/usr/bin/env python3
"""Run end-to-end food intelligence inference on an image of packaged food.

Usage:
    python scripts/run_image_inference.py --image path/to/image.jpg [--barcode 8901030000001] [--weight 120] [--output outputs/result.json]

Outputs:
    - Validated structured JSON conforming to config/nutrient_schema.yaml
    - Formatted terminal report with nutrition, allergens, alerts, and provenance
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from food_engine.engine import FoodIntelligenceEngine


def main():
    parser = argparse.ArgumentParser(description="Food Intelligence Engine Image Inference CLI")
    parser.add_argument("--image", type=str, default=None, help="Path to input packaged food image")
    parser.add_argument("--barcode", type=str, default=None, help="Optional barcode / GTIN / UPC")
    parser.add_argument("--weight", type=float, default=None, help="Optional package net weight in grams")
    parser.add_argument("--volume", type=float, default=None, help="Optional package volume in millilitres")
    parser.add_argument("--output", type=str, default="outputs/inference_result.json", help="Path to save output JSON")
    parser.add_argument("--gpu", action="store_true", help="Enable GPU acceleration if available")

    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent

    # If no image specified, use the realistic sample biscuit fixture
    if not args.image:
        fixture_path = repo_root / "tests" / "fixtures" / "sample_biscuit_packet.png"
        if not fixture_path.exists():
            from tests.fixtures.create_sample_images import create_sample_label_images
            create_sample_label_images(repo_root / "tests" / "fixtures")
        image_path = fixture_path
        print(f"No --image argument provided. Running demonstration on test fixture: {image_path}")
        package_weight = args.weight or 120.0
    else:
        image_path = Path(args.image)
        package_weight = args.weight

    engine = FoodIntelligenceEngine(repo_root=repo_root, use_gpu=args.gpu)

    print(f"\nProcessing packaged food image: {image_path} ...")
    payload = engine.process_image(
        image_input=image_path,
        barcode=args.barcode,
        package_weight_g=package_weight,
        package_volume_ml=args.volume,
    )

    # Save JSON output
    out_file = repo_root / args.output
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # Print Formatted Human-Readable Summary
    print("\n" + "=" * 70)
    print("           FOOD INTELLIGENCE ENGINE — STRUCTURED AUDIT REPORT")
    print("=" * 70)
    print(f"Input Image:           {payload['input_image']}")
    print(f"Timestamp:             {payload['timestamp']}")
    print(f"Dimensions:            {payload['image_metadata']['width']}x{payload['image_metadata']['height']} ({payload['image_metadata']['format']})")
    print(f"OCR Engine:            {payload['ocr_result']['engine']} (Model: {payload['ocr_result']['model_version']}, Time: {payload['ocr_result']['execution_time_sec']}s)")

    pm = payload["product_match"]
    print("\n--- [PRODUCT IDENTIFICATION] ---")
    print(f"Status:                {pm['status']} (Match Type: {pm['match_type']})")
    print(f"Identified Name:       {pm['product_name'] or 'N/A'}")
    print(f"Brand:                 {pm['brand'] or 'N/A'}")
    print(f"Barcode:               {pm['barcode'] or 'N/A'}")
    print(f"Database Source:       {pm['source']}")

    ing = payload["ingredients"]
    print("\n--- [INGREDIENTS & ALLERGENS] ---")
    print(f"Declared Allergens:    {', '.join(ing['declared_allergens']) if ing['declared_allergens'] else 'None declared'}")
    print(f"Trace Warnings:        {', '.join(ing['potential_traces']) if ing['potential_traces'] else 'None'}")
    print(f"Parsed Ingredients:    {len(ing['parsed_ingredients'])} items identified")
    print(f"Safety Review Req:     {ing['review_required']}")

    nut = payload["nutrition"]
    print(f"\n--- [NUTRITION FACTS ({nut['basis'].upper()})] ---")
    print(f"{'Nutrient':<25} | {'Amount':<12} | {'Status':<15}")
    print("-" * 58)
    for k, v in nut["nutrients"].items():
        if v["value"] is not None:
            amt_str = f"{v['value']} {v['unit']}"
            print(f"{k:<25} | {amt_str:<12} | {v['status']:<15}")

    calc = payload["calculated_package_totals"]
    if calc.get("calculated_nutrients"):
        print(f"\n--- [CALCULATED FULL PACKAGE TOTALS ({calc.get('package_weight_g')}g)] ---")
        for k, v in calc["calculated_nutrients"].items():
            if v["value"] is not None:
                print(f"  - {k:<23}: {v['value']} {v['unit']}")

    print("\n--- [EVIDENCE-BASED HEALTH ALERTS] ---")
    if payload["evidence_based_alerts"]:
        for a in payload["evidence_based_alerts"]:
            print(f"[{a['severity'].upper()}] {a['title']}")
            print(f"   Reason:    {a['reason']}")
            print(f"   Authority: {a['authority_source']}")
    else:
        print("No critical threshold or allergen alerts triggered.")

    print("\n--- [DATA QUALITY AUDIT] ---")
    dq = payload["data_quality"]
    print(f"Missing Core Fields:   {dq['missing_fields'] if dq['missing_fields'] else 'None'}")
    print(f"Conflicting Baselines: {dq['conflicting_fields'] if dq['conflicting_fields'] else 'None'}")
    print(f"Manual Review Needed:  {dq['manual_review_required']}")
    print("=" * 70)
    print(f"Full validated schema JSON saved to: {out_file}\n")


if __name__ == "__main__":
    main()
