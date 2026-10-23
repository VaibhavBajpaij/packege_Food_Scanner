#!/usr/bin/env python3
"""Download, index, and audit a documented, reproducible subset of Open Food Facts packaged products.

Licensing & Scope:
- Source: Open Food Facts (ODbL 1.0 database, DbCL 1.0 contents, CC BY-SA 3.0 images)
- Total remote database: ~1.49 GB compressed (~15 GB decompressed)
- Downloaded subset: Exactly 5 MB (5,242,880 bytes) compressed stream (~16,700 products)
- Remaining unfetched: ~1.44 GB
- Database: datasets/processed/products/products.db (SQLite)
- Audit report: reports/licensing/open_food_facts_license_report.md
"""

import gzip
import io
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
import requests
from food_engine.data_ingestion.download_manager import DownloadManager

OFF_EXPORT_URL = "https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz"
TOTAL_REMOTE_BYTES = 1491292191  # ~1.49 GB
SUBSET_BYTES = 5 * 1024 * 1024   # 5 MB
RESOURCE_ID = "open_food_facts_packaged_products_subset"


def download_and_index_open_food_facts():
    repo_root = Path(__file__).resolve().parent.parent
    dm = DownloadManager(repo_root=repo_root)

    raw_dir = repo_root / "datasets" / "raw" / "open_food_facts"
    raw_dir.mkdir(parents=True, exist_ok=True)
    sample_gz = raw_dir / "open_food_facts_sample.csv.gz"

    headers = {
        "User-Agent": "FoodIntelligenceEngine/1.0 (Standalone Research Engine; contact@example.com)"
    }

    print(f"=== Downloading Open Food Facts Bounded Stream ({SUBSET_BYTES} bytes) ===")
    print(f"Total remote database size: {TOTAL_REMOTE_BYTES} bytes ({round(TOTAL_REMOTE_BYTES/(1024**3), 2)} GB)")

    t0 = time.time()
    buf = bytearray()
    with requests.get(OFF_EXPORT_URL, headers=headers, stream=True, timeout=30) as r:
        if r.status_code != 200:
            raise RuntimeError(f"Open Food Facts download failed: HTTP {r.status_code} {r.reason}")
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if chunk:
                buf.extend(chunk)
                if len(buf) >= SUBSET_BYTES:
                    break

    downloaded_data = bytes(buf[:SUBSET_BYTES])
    sample_gz.write_bytes(downloaded_data)
    elapsed = time.time() - t0
    actual_downloaded = len(downloaded_data)
    sha256_hash = dm.calculate_sha256(sample_gz)
    remaining_bytes = TOTAL_REMOTE_BYTES - actual_downloaded

    print(f"Downloaded: {actual_downloaded} bytes in {round(elapsed, 2)}s, SHA-256: {sha256_hash}")
    print(f"Remaining database bytes not downloaded: {remaining_bytes} bytes (~{round(remaining_bytes/(1024**3), 2)} GB)")

    # Index into SQLite
    processed_dir = repo_root / "datasets" / "processed" / "products"
    processed_dir.mkdir(parents=True, exist_ok=True)
    db_path = processed_dir / "products.db"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS off_products (
            code TEXT PRIMARY KEY,
            product_name TEXT,
            brands TEXT,
            categories TEXT,
            countries TEXT,
            ingredients_text TEXT,
            allergens TEXT,
            serving_size TEXT,
            energy_100g REAL,
            proteins_100g REAL,
            carbohydrates_100g REAL,
            sugars_100g REAL,
            fat_100g REAL,
            saturated_fat_100g REAL,
            fiber_100g REAL,
            sodium_100g REAL,
            salt_100g REAL,
            nutrients_json TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_off_code ON off_products(code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_off_name ON off_products(product_name)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_off_brand ON off_products(brands)")

    records = []
    line_count = 0

    try:
        with gzip.GzipFile(fileobj=io.BytesIO(downloaded_data)) as gz:
            text_stream = io.TextIOWrapper(gz, encoding="utf-8", errors="replace")
            header_line = text_stream.readline().rstrip("\r\n")
            header_fields = header_line.split("\t")
            field_idx = {name: i for i, name in enumerate(header_fields)}

            def get_col(row, col_name, default=""):
                idx = field_idx.get(col_name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            for line in text_stream:
                line_count += 1
                row = line.rstrip("\r\n").split("\t")
                code = get_col(row, "code")
                product_name = get_col(row, "product_name")
                if not code or not product_name:
                    continue

                brands = get_col(row, "brands")
                categories = get_col(row, "categories")
                countries = get_col(row, "countries")
                ingredients_text = get_col(row, "ingredients_text")
                allergens = get_col(row, "allergens")
                serving_size = get_col(row, "serving_size")

                def safe_float(col):
                    v = get_col(row, col)
                    try:
                        return float(v) if v else None
                    except ValueError:
                        return None

                energy = safe_float("energy-kcal_100g") or safe_float("energy_100g")
                protein = safe_float("proteins_100g")
                carbs = safe_float("carbohydrates_100g")
                sugars = safe_float("sugars_100g")
                fat = safe_float("fat_100g")
                sat_fat = safe_float("saturated-fat_100g")
                fiber = safe_float("fiber_100g")
                sodium = safe_float("sodium_100g")
                salt = safe_float("salt_100g")

                nut_dict = {
                    "energy_kcal": energy,
                    "protein_g": protein,
                    "carbohydrates_g": carbs,
                    "sugars_g": sugars,
                    "total_fat_g": fat,
                    "saturated_fat_g": sat_fat,
                    "dietary_fibre_g": fiber,
                    "sodium_mg": round(sodium * 1000, 2) if sodium is not None else None,
                    "salt_g": salt,
                }

                records.append((
                    code, product_name, brands, categories, countries,
                    ingredients_text, allergens, serving_size,
                    energy, protein, carbs, sugars, fat, sat_fat, fiber, sodium, salt,
                    json.dumps(nut_dict)
                ))

                if len(records) >= 2000:
                    cur.executemany("""
                        INSERT OR REPLACE INTO off_products VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                    """, records)
                    conn.commit()
                    records = []
    except (EOFError, gzip.BadGzipFile):
        pass

    if records:
        cur.executemany("""
            INSERT OR REPLACE INTO off_products VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, records)
        conn.commit()

    cur.execute("SELECT COUNT(*) FROM off_products")
    total_indexed = cur.fetchone()[0]
    conn.close()

    print(f"Processed and indexed {total_indexed} products into {db_path} successfully.")

    # Record in manifest
    dm.record_resource(
        resource_id=RESOURCE_ID,
        name="Open Food Facts Packaged Products (Documented Subset)",
        source_url=OFF_EXPORT_URL,
        category="dataset",
        license_name="Open Database License (ODbL) 1.0",
        license_url="https://opendatacommons.org/licenses/odbl/1-0/",
        file_path=sample_gz,
        sha256=sha256_hash,
        file_size=actual_downloaded,
        metadata={
            "total_remote_bytes": TOTAL_REMOTE_BYTES,
            "downloaded_bytes": actual_downloaded,
            "remaining_bytes": remaining_bytes,
            "indexed_products_count": total_indexed,
            "format": "tsv_in_gzip",
            "scope": "Packaged food barcodes, ingredient declarations, nutrition facts per 100g, allergen declarations"
        }
    )

    # Generate Licensing Report
    lic_report = repo_root / "reports" / "licensing" / "open_food_facts_license_report.md"
    lic_report.parent.mkdir(parents=True, exist_ok=True)
    lic_report.write_text(f"""# Open Food Facts — Licensing & Commercial Use Compliance Report

- **Source**: Open Food Facts Project
- **Official Data Download Page**: [https://world.openfoodfacts.org/data](https://world.openfoodfacts.org/data)
- **Official Licensing Documentation**: [Open Food Facts License Guidance](https://openfoodfacts.github.io/documentation/docs/Product-Opener/api/tutorials/license-be-on-the-legal-side/)
- **Total Remote Dataset Size**: `{TOTAL_REMOTE_BYTES} bytes` (~{round(TOTAL_REMOTE_BYTES/(1024**3), 2)} GB)
- **Downloaded Subset Size**: `{actual_downloaded} bytes` (~{round(actual_downloaded/(1024**2), 2)} MB)
- **Remaining Unfetched Size**: `{remaining_bytes} bytes` (~{round(remaining_bytes/(1024**3), 2)} GB)
- **Total Indexed Packaged Products**: `{total_indexed}` items
- **Local Subset SHA-256**: `{sha256_hash}`

---

## 1. Licensing Hierarchy
Open Food Facts uses a tripartite licensing model:
1. **The Database Structure**: Licensed under **Open Database License (ODbL) v1.0**.
2. **Individual Factual Contents**: Licensed under the **Database Contents License (DbCL) v1.0**.
3. **Product Packaging Images**: Contributed under **Creative Commons Attribution-ShareAlike 3.0 Unported (CC BY-SA 3.0)** or applicable local fair use rights.

---

## 2. Commercial Use Compliance Analysis
- **Status**: `Permitted with Specific Legal Obligations`
- **Key Obligations under ODbL**:
  - **Attribution**: The application or service must prominently display:
    *"This product contains data from Open Food Facts, which is made available under the Open Database License (ODbL)."*
  - **Share-Alike for Derivative Databases**: If you publicly distribute or operate a service based on a modified or enhanced version of the Open Food Facts database, you must make the derivative database available under ODbL terms.
  - **No DRM / Technological Restrictions on the Database**: You cannot apply technical protection measures (such as encrypted proprietary database locks) that prevent users from accessing the underlying public database contents.
  - **Private / Internal Processing**: Internal analysis, model training, and private evaluations do not trigger the public Share-Alike redistribution requirement until public launch.
- **Product Images Caution**:
  Do **not** bulk-download all product images for proprietary commercial distribution. Individual product images carry CC BY-SA terms and may depict copyrighted packaging artwork or registered trademarks. Use product images strictly for verification or model validation, not as proprietary redistributed assets.
""", encoding="utf-8")
    print(f"License report saved to {lic_report}")


if __name__ == "__main__":
    download_and_index_open_food_facts()
