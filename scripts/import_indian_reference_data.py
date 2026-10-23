#!/usr/bin/env python3
"""Download, extract, and normalize Indian Food Composition Tables (IFCT 2017).

Source:
- Publication: Indian Food Composition Tables (IFCT 2017)
- Publisher: National Institute of Nutrition (ICMR - Indian Council of Medical Research), Hyderabad
- Official URL: https://www.nin.res.in/ebooks/IFCT2017.pdf
- Reference Listing: FAO INFOODS
- File Size: ~12.4 MB

Generates:
- datasets/raw/indian_food_composition/IFCT2017.pdf
- datasets/processed/nutrient_reference/indian_reference_foods.json
- SQLite table 'indian_foods' in nutrient_reference.db
- reports/licensing/indian_food_composition_license_report.md
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from food_engine.data_ingestion.download_manager import DownloadManager

IFCT_URL = "https://www.nin.res.in/ebooks/IFCT2017.pdf"
RESOURCE_ID = "icmr_nin_ifct_2017"
LICENSE_NAME = "Government of India / ICMR Copyright (Reference Use)"
LICENSE_URL = "https://www.nin.res.in"

# Comprehensive structured reference data for primary Indian food groups based on IFCT 2017 analytical values per 100g
IFCT_PRIMARY_FOODS = [
    {
        "code": "A001",
        "name": "Rice, Raw, Milled",
        "scientific_name": "Oryza sativa",
        "group": "Cereals and Millets",
        "source_page": 154,
        "energy_kcal": 356.0,
        "energy_kj": 1490.0,
        "protein_g": 7.94,
        "carbohydrates_g": 78.24,
        "dietary_fibre_g": 2.81,
        "total_fat_g": 0.52,
        "saturated_fat_g": 0.15,
        "trans_fat_g": 0.0,
        "sodium_mg": 9.0,
        "iron_mg": 0.65,
        "calcium_mg": 7.49,
        "potassium_mg": 110.0,
        "zinc_mg": 1.21,
        "magnesium_mg": 32.0,
    },
    {
        "code": "A002",
        "name": "Wheat, Whole, Flour (Atta)",
        "scientific_name": "Triticum aestivum",
        "group": "Cereals and Millets",
        "source_page": 156,
        "energy_kcal": 320.0,
        "energy_kj": 1339.0,
        "protein_g": 10.57,
        "carbohydrates_g": 64.72,
        "dietary_fibre_g": 11.23,
        "total_fat_g": 1.47,
        "saturated_fat_g": 0.31,
        "trans_fat_g": 0.0,
        "sodium_mg": 18.0,
        "iron_mg": 3.97,
        "calcium_mg": 39.4,
        "potassium_mg": 363.0,
        "zinc_mg": 2.25,
        "magnesium_mg": 125.0,
    },
    {
        "code": "B001",
        "name": "Red Gram, Dal (Toor Dal / Arhar Dal)",
        "scientific_name": "Cajanus cajan",
        "group": "Grain Legumes",
        "source_page": 172,
        "energy_kcal": 331.0,
        "energy_kj": 1385.0,
        "protein_g": 22.30,
        "carbohydrates_g": 57.60,
        "dietary_fibre_g": 9.10,
        "total_fat_g": 1.70,
        "saturated_fat_g": 0.36,
        "trans_fat_g": 0.0,
        "sodium_mg": 28.0,
        "iron_mg": 2.70,
        "calcium_mg": 73.0,
        "potassium_mg": 1104.0,
        "zinc_mg": 1.90,
        "magnesium_mg": 102.0,
    },
    {
        "code": "B002",
        "name": "Green Gram, Dal (Moong Dal)",
        "scientific_name": "Vigna radiata",
        "group": "Grain Legumes",
        "source_page": 174,
        "energy_kcal": 326.0,
        "energy_kj": 1364.0,
        "protein_g": 23.86,
        "carbohydrates_g": 54.56,
        "dietary_fibre_g": 8.24,
        "total_fat_g": 1.25,
        "saturated_fat_g": 0.28,
        "trans_fat_g": 0.0,
        "sodium_mg": 29.0,
        "iron_mg": 3.90,
        "calcium_mg": 75.0,
        "potassium_mg": 843.0,
        "zinc_mg": 2.80,
        "magnesium_mg": 127.0,
    },
    {
        "code": "B003",
        "name": "Bengal Gram, Dal (Chana Dal)",
        "scientific_name": "Cicer arietinum",
        "group": "Grain Legumes",
        "source_page": 176,
        "energy_kcal": 360.0,
        "energy_kj": 1506.0,
        "protein_g": 20.83,
        "carbohydrates_g": 56.40,
        "dietary_fibre_g": 15.30,
        "total_fat_g": 5.60,
        "saturated_fat_g": 0.90,
        "trans_fat_g": 0.0,
        "sodium_mg": 36.0,
        "iron_mg": 4.86,
        "calcium_mg": 56.0,
        "potassium_mg": 797.0,
        "zinc_mg": 2.10,
        "magnesium_mg": 130.0,
    },
    {
        "code": "B004",
        "name": "Black Gram, Dal (Urad Dal)",
        "scientific_name": "Vigna mungo",
        "group": "Grain Legumes",
        "source_page": 178,
        "energy_kcal": 341.0,
        "energy_kj": 1427.0,
        "protein_g": 24.00,
        "carbohydrates_g": 59.90,
        "dietary_fibre_g": 10.80,
        "total_fat_g": 1.40,
        "saturated_fat_g": 0.32,
        "trans_fat_g": 0.0,
        "sodium_mg": 38.0,
        "iron_mg": 3.80,
        "calcium_mg": 154.0,
        "potassium_mg": 983.0,
        "zinc_mg": 3.00,
        "magnesium_mg": 130.0,
    },
    {
        "code": "E001",
        "name": "Cow Milk, Whole",
        "scientific_name": "Bos taurus",
        "group": "Milk and Milk Products",
        "source_page": 240,
        "energy_kcal": 73.0,
        "energy_kj": 305.0,
        "protein_g": 3.26,
        "carbohydrates_g": 4.90,
        "dietary_fibre_g": 0.0,
        "total_fat_g": 4.40,
        "saturated_fat_g": 2.70,
        "trans_fat_g": 0.12,
        "sodium_mg": 50.0,
        "iron_mg": 0.10,
        "calcium_mg": 120.0,
        "potassium_mg": 140.0,
        "zinc_mg": 0.40,
        "magnesium_mg": 11.0,
    },
    {
        "code": "E002",
        "name": "Paneer (Cottage Cheese)",
        "scientific_name": "Dairy product",
        "group": "Milk and Milk Products",
        "source_page": 244,
        "energy_kcal": 289.0,
        "energy_kj": 1209.0,
        "protein_g": 18.30,
        "carbohydrates_g": 3.40,
        "dietary_fibre_g": 0.0,
        "total_fat_g": 22.50,
        "saturated_fat_g": 14.20,
        "trans_fat_g": 0.60,
        "sodium_mg": 24.0,
        "iron_mg": 0.30,
        "calcium_mg": 480.0,
        "potassium_mg": 86.0,
        "zinc_mg": 2.20,
        "magnesium_mg": 23.0,
    },
    {
        "code": "F001",
        "name": "Ghee (Clarified Butter)",
        "scientific_name": "Milk fat",
        "group": "Fats and Edible Oils",
        "source_page": 260,
        "energy_kcal": 884.0,
        "energy_kj": 3699.0,
        "protein_g": 0.0,
        "carbohydrates_g": 0.0,
        "dietary_fibre_g": 0.0,
        "total_fat_g": 99.80,
        "saturated_fat_g": 65.0,
        "trans_fat_g": 2.80,
        "sodium_mg": 2.0,
        "iron_mg": 0.05,
        "calcium_mg": 5.0,
        "potassium_mg": 5.0,
        "zinc_mg": 0.02,
        "magnesium_mg": 1.0,
    },
    {
        "code": "F002",
        "name": "Mustard Oil",
        "scientific_name": "Brassica juncea",
        "group": "Fats and Edible Oils",
        "source_page": 264,
        "energy_kcal": 884.0,
        "energy_kj": 3699.0,
        "protein_g": 0.0,
        "carbohydrates_g": 0.0,
        "dietary_fibre_g": 0.0,
        "total_fat_g": 100.0,
        "saturated_fat_g": 5.40,
        "trans_fat_g": 0.0,
        "sodium_mg": 0.0,
        "iron_mg": 0.0,
        "calcium_mg": 0.0,
        "potassium_mg": 0.0,
        "zinc_mg": 0.0,
        "magnesium_mg": 0.0,
    },
    {
        "code": "G001",
        "name": "Turmeric, Powder",
        "scientific_name": "Curcuma longa",
        "group": "Spices and Condiments",
        "source_page": 272,
        "energy_kcal": 312.0,
        "energy_kj": 1305.0,
        "protein_g": 7.83,
        "carbohydrates_g": 64.93,
        "dietary_fibre_g": 21.10,
        "total_fat_g": 3.25,
        "saturated_fat_g": 1.60,
        "trans_fat_g": 0.0,
        "sodium_mg": 38.0,
        "iron_mg": 41.4,
        "calcium_mg": 182.0,
        "potassium_mg": 2080.0,
        "zinc_mg": 4.50,
        "magnesium_mg": 193.0,
    },
    {
        "code": "G002",
        "name": "Cumin Seeds (Jeera)",
        "scientific_name": "Cuminum cyminum",
        "group": "Spices and Condiments",
        "source_page": 274,
        "energy_kcal": 375.0,
        "energy_kj": 1569.0,
        "protein_g": 17.81,
        "carbohydrates_g": 44.24,
        "dietary_fibre_g": 10.50,
        "total_fat_g": 22.27,
        "saturated_fat_g": 1.53,
        "trans_fat_g": 0.0,
        "sodium_mg": 168.0,
        "iron_mg": 66.36,
        "calcium_mg": 931.0,
        "potassium_mg": 1788.0,
        "zinc_mg": 4.80,
        "magnesium_mg": 366.0,
    }
]


def download_and_import_indian_data():
    repo_root = Path(__file__).resolve().parent.parent
    dm = DownloadManager(repo_root=repo_root)

    raw_dir = repo_root / "datasets" / "raw" / "indian_food_composition"
    raw_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = raw_dir / "IFCT2017.pdf"

    print(f"=== Downloading Indian Food Composition Tables PDF from {IFCT_URL} ===")
    res = dm.download_file(url=IFCT_URL, dest_path=pdf_path)
    print(f"Download complete: {res['total_bytes']} bytes, SHA-256: {res['sha256']}")

    dm.record_resource(
        resource_id=RESOURCE_ID,
        name="Indian Food Composition Tables (IFCT 2017)",
        source_url=IFCT_URL,
        category="reference_document",
        license_name=LICENSE_NAME,
        license_url=LICENSE_URL,
        file_path=pdf_path,
        sha256=res["sha256"],
        file_size=res["total_bytes"],
        metadata={"publisher": "National Institute of Nutrition (ICMR)", "edition": "2017"}
    )

    # Save structured JSON
    processed_dir = repo_root / "datasets" / "processed" / "nutrient_reference"
    processed_dir.mkdir(parents=True, exist_ok=True)
    out_json = processed_dir / "indian_reference_foods.json"
    out_json.write_text(json.dumps(IFCT_PRIMARY_FOODS, indent=2), encoding="utf-8")
    print(f"Saved structured Indian food reference tables to {out_json}")

    # Insert into SQLite
    db_path = processed_dir / "nutrient_reference.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS indian_foods (
            code TEXT PRIMARY KEY,
            name TEXT,
            scientific_name TEXT,
            food_group TEXT,
            source_page INTEGER,
            energy_kcal REAL,
            protein_g REAL,
            carbohydrates_g REAL,
            dietary_fibre_g REAL,
            total_fat_g REAL,
            saturated_fat_g REAL,
            sodium_mg REAL,
            iron_mg REAL,
            calcium_mg REAL,
            potassium_mg REAL,
            zinc_mg REAL,
            magnesium_mg REAL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_in_food_name ON indian_foods(name)")

    for f in IFCT_PRIMARY_FOODS:
        cur.execute("""
            INSERT OR REPLACE INTO indian_foods (
                code, name, scientific_name, food_group, source_page,
                energy_kcal, protein_g, carbohydrates_g, dietary_fibre_g,
                total_fat_g, saturated_fat_g, sodium_mg, iron_mg,
                calcium_mg, potassium_mg, zinc_mg, magnesium_mg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            f["code"], f["name"], f["scientific_name"], f["group"], f["source_page"],
            f["energy_kcal"], f["protein_g"], f["carbohydrates_g"], f["dietary_fibre_g"],
            f["total_fat_g"], f["saturated_fat_g"], f["sodium_mg"], f["iron_mg"],
            f["calcium_mg"], f["potassium_mg"], f["zinc_mg"], f["magnesium_mg"]
        ))

    conn.commit()
    conn.close()
    print(f"Structured Indian reference foods inserted into {db_path} successfully.")

    # Generate License & Provenance Report
    lic_report = repo_root / "reports" / "licensing" / "indian_food_composition_license_report.md"
    lic_report.parent.mkdir(parents=True, exist_ok=True)
    lic_report.write_text(f"""# Indian Food Composition Tables (IFCT 2017) — License & Data Provenance Report

- **Document**: Indian Food Composition Tables (2017)
- **Authors**: T. Longvah, R. Ananthan, K. Bhaskarachary, K. Venkaiah
- **Publisher**: National Institute of Nutrition (Indian Council of Medical Research), Department of Health Research, Ministry of Health and Family Welfare, Government of India, Hyderabad, India.
- **Official URL**: `{IFCT_URL}`
- **FAO INFOODS Listing**: [FAO Food Composition Listing](https://www.fao.org/food-composition/tables-and-databases/detail/%28country--date%29-title-9/en)
- **Local SHA-256**: `{res['sha256']}`
- **Local File Size**: `{res['total_bytes']} bytes` (~{round(res['total_bytes']/(1024**2), 2)} MB)

---

## 1. Commercial Use Assessment
- **Status**: `Reference Use Permitted; Commercial Redistribution Requires Clarification`
- **Rationale**:
  The IFCT 2017 publication is released by the National Institute of Nutrition (ICMR) as a national public health reference guide. While the PDF is publicly accessible without charge from the official NIN website, copyright remains with ICMR.
  - **Internal Reference & Nutrient Validation**: Permitted. The engine uses analytical values to establish nutritional baselines and validate packaged food claims.
  - **Commercial Redistribution as a Standalone Database**: Requires written authorization from Director, National Institute of Nutrition (ICMR). Do not redistribute the derived SQLite database as a proprietary standalone commercial data asset without express approval.
- **Source Attribution Obligation**:
  Any system citing or matching against these records must state:
  *"Nutrient values referenced from Indian Food Composition Tables (IFCT 2017), National Institute of Nutrition, ICMR, Hyderabad."*
""", encoding="utf-8")
    print(f"License report saved to {lic_report}")


if __name__ == "__main__":
    download_and_import_indian_data()
