#!/usr/bin/env python3
"""Build and optimize product lookup indexes in SQLite.

Creates covering indexes on:
- off_products (code, product_name, brands)
- usda_foods (fdc_id, description)
- indian_foods (code, name)

Enables fast exact barcode lookup (<1ms) and responsive name searches.
"""

import sqlite3
import time
from pathlib import Path


def build_and_optimize_indexes():
    repo_root = Path(__file__).resolve().parent.parent
    products_db = repo_root / "datasets" / "processed" / "products" / "products.db"
    nutrient_db = repo_root / "datasets" / "processed" / "nutrient_reference" / "nutrient_reference.db"

    t0 = time.time()
    print("=== Optimizing Product Database Indexes ===")
    if products_db.exists():
        conn = sqlite3.connect(products_db)
        cur = conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_off_code ON off_products(code)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_off_name ON off_products(product_name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_off_brand ON off_products(brands)")
        cur.execute("ANALYZE off_products")
        cur.execute("SELECT COUNT(*) FROM off_products")
        count = cur.fetchone()[0]
        conn.close()
        print(f"Optimized off_products index: {count} items indexed.")
    else:
        print(f"Warning: {products_db} does not exist yet. Run scripts/download_open_food_facts.py first.")

    print("\n=== Optimizing Nutrient Reference Database Indexes ===")
    if nutrient_db.exists():
        conn = sqlite3.connect(nutrient_db)
        cur = conn.cursor()
        cur.execute("CREATE INDEX IF NOT EXISTS idx_usda_desc ON usda_foods(description)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_in_food_name ON indian_foods(name)")
        cur.execute("ANALYZE usda_foods")
        cur.execute("ANALYZE indian_foods")
        cur.execute("SELECT COUNT(*) FROM usda_foods")
        usda_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM indian_foods")
        in_count = cur.fetchone()[0]
        conn.close()
        print(f"Optimized nutrient reference indexes: {usda_count} USDA foods, {in_count} Indian foods.")
    else:
        print(f"Warning: {nutrient_db} does not exist yet.")

    print(f"\nIndex optimization completed in {round(time.time() - t0, 3)}s.")


if __name__ == "__main__":
    build_and_optimize_indexes()
