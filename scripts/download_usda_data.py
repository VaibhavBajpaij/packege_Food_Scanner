#!/usr/bin/env python3
"""Download, extract, and normalize USDA FoodData Central Foundation Foods dataset.

Downloads:
- URL: https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2024-10-31.zip
- Size: ~3.25 MB
- License: U.S. Public Domain (CC0 equivalent)

Extracts and Normalizes:
- food.csv: fdc_id, description, data_type, publication_date
- nutrient.csv: id, name, unit_name, nutrient_nbr
- food_nutrient.csv: fdc_id, nutrient_id, amount
- food_portion.csv: fdc_id, amount, measure_unit_id, portion_description, gram_weight

Outputs:
- datasets/raw/usda_fooddata_central/FoodData_Central_foundation_food_csv_2024-10-31.zip
- datasets/processed/nutrient_reference/usda_foundation_foods.json
"""

import csv
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from food_engine.data_ingestion.download_manager import DownloadManager

USDA_URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_foundation_food_csv_2024-10-31.zip"
RESOURCE_ID = "usda_fdc_foundation_2024_10_31"
LICENSE_NAME = "U.S. Public Domain / CC0 Equivalent"
LICENSE_URL = "https://www.usda.gov/policies-and-links"


def download_and_normalize_usda():
    repo_root = Path(__file__).resolve().parent.parent
    dm = DownloadManager(repo_root=repo_root)

    raw_dir = repo_root / "datasets" / "raw" / "usda_fooddata_central"
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / "FoodData_Central_foundation_food_csv_2024-10-31.zip"
    extract_dir = raw_dir / "extracted"

    print(f"=== Downloading USDA Foundation Foods Dataset from {USDA_URL} ===")
    res = dm.download_file(url=USDA_URL, dest_path=zip_path)
    print(f"Download complete: {res['total_bytes']} bytes, SHA-256: {res['sha256']}")

    print("Extracting ZIP archive ...")
    ext_res = dm.extract_archive(archive_path=zip_path, extract_dir=extract_dir)
    print(f"Extracted {ext_res['extracted_count']} files ({ext_res['total_extracted_bytes']} bytes)")

    dm.record_resource(
        resource_id=RESOURCE_ID,
        name="USDA FoodData Central Foundation Foods (CSV)",
        source_url=USDA_URL,
        category="dataset",
        license_name=LICENSE_NAME,
        license_url=LICENSE_URL,
        file_path=zip_path,
        sha256=res["sha256"],
        file_size=res["total_bytes"],
        extracted_path=extract_dir,
        extracted_bytes=ext_res["total_extracted_bytes"],
        metadata={"release_date": "2024-10-31", "data_type": "Foundation Foods"}
    )

    # Locate extracted CSV files (might be inside a subfolder)
    csv_files = {p.name: p for p in extract_dir.rglob("*.csv")}
    print(f"Found CSV files: {list(csv_files.keys())}")

    food_csv = csv_files.get("food.csv")
    nutrient_csv = csv_files.get("nutrient.csv")
    food_nutrient_csv = csv_files.get("food_nutrient.csv")

    if not (food_csv and nutrient_csv and food_nutrient_csv):
        raise RuntimeError("Required USDA CSV files (food.csv, nutrient.csv, food_nutrient.csv) not found in archive.")

    # 1. Parse nutrients dictionary
    print("Parsing nutrient definitions ...")
    nutrient_dict = {}  # nutrient_id -> {"name": ..., "unit_name": ...}
    with open(nutrient_csv, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nutrient_dict[row["id"]] = {
                "name": row.get("name", "").strip(),
                "unit": row.get("unit_name", "").strip().lower(),
                "number": row.get("nutrient_nbr", "").strip(),
            }

    # 2. Parse foods
    print("Parsing foods ...")
    foods = {}  # fdc_id -> {"description": ..., "nutrients": {}}
    with open(food_csv, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fdc_id = row["fdc_id"]
            foods[fdc_id] = {
                "fdc_id": fdc_id,
                "description": row.get("description", "").strip(),
                "data_type": row.get("data_type", "foundation_food"),
                "publication_date": row.get("publication_date", ""),
                "nutrients": {}
            }

    # 3. Associate nutrients with foods
    print("Mapping food nutrients ...")
    with open(food_nutrient_csv, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fdc_id = row.get("fdc_id")
            nut_id = row.get("nutrient_id")
            amount_str = row.get("amount")
            if fdc_id in foods and nut_id in nutrient_dict:
                try:
                    val = float(amount_str) if amount_str else 0.0
                    nut_info = nutrient_dict[nut_id]
                    nut_name_clean = nut_info["name"].lower()
                    foods[fdc_id]["nutrients"][nut_info["name"]] = {
                        "value": val,
                        "unit": nut_info["unit"],
                        "nutrient_id": nut_id,
                    }
                except ValueError:
                    continue

    # Save to JSON and SQLite
    processed_dir = repo_root / "datasets" / "processed" / "nutrient_reference"
    processed_dir.mkdir(parents=True, exist_ok=True)
    out_json = processed_dir / "usda_foundation_foods.json"

    food_list = list(foods.values())
    print(f"Normalizing {len(food_list)} USDA reference foods to {out_json} ...")
    out_json.write_text(json.dumps(food_list[:1000], indent=2), encoding="utf-8")

    db_path = processed_dir / "nutrient_reference.db"
    print(f"Writing reference database to SQLite: {db_path} ...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS usda_foods (
            fdc_id TEXT PRIMARY KEY,
            description TEXT,
            data_type TEXT,
            nutrients_json TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usda_desc ON usda_foods(description)")

    cur.executemany(
        "INSERT OR REPLACE INTO usda_foods (fdc_id, description, data_type, nutrients_json) VALUES (?, ?, ?, ?)",
        [
            (f["fdc_id"], f["description"], f["data_type"], json.dumps(f["nutrients"]))
            for f in food_list
        ]
    )
    conn.commit()
    conn.close()

    print(f"USDA Foundation Foods imported successfully. Total records: {len(food_list)}")


if __name__ == "__main__":
    download_and_normalize_usda()
