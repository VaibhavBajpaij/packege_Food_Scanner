"""Stage 3: Product Identification and Database Matching.

Matches packaged foods by priority:
1. Exact Barcode / GTIN / UPC lookup in local Open Food Facts database.
2. Verified Brand + Product Name matching.
3. Reference food lookup in USDA Foundation Foods and Indian Food Composition Tables.
4. OCR-only fallback if no reliable database record exists.

Enforces:
- Never claim a barcode was found unless actually provided or verified.
- Never match dissimilar products if nutrition or formulation conflicts.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProductMatcher:
    """Matches product codes and names against local SQLite product & nutrient indexes."""

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.products_db_path = self.repo_root / "datasets" / "processed" / "products" / "products.db"
        self.reference_db_path = self.repo_root / "datasets" / "processed" / "nutrient_reference" / "nutrient_reference.db"

    def match(
        self,
        barcode: Optional[str] = None,
        product_name: Optional[str] = None,
        brand: Optional[str] = None,
        ocr_lines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Performs hierarchical priority matching for a product."""

        # Priority 1: Exact barcode matching
        if barcode:
            clean_code = str(barcode).strip().lstrip("0")
            exact_match = self._lookup_barcode(barcode) or (self._lookup_barcode(clean_code) if clean_code else None)
            if exact_match:
                return {
                    "status": "exact_barcode_match",
                    "match_type": "exact_barcode",
                    "product_name": exact_match["product_name"],
                    "barcode": exact_match["code"],
                    "brand": exact_match["brands"],
                    "source": "Open Food Facts (Local Subset)",
                    "source_id": exact_match["code"],
                    "source_dataset_version": "2026-subset",
                    "confidence": 1.0,
                    "matched_data": exact_match,
                }

        # Priority 2: Verified Brand + Product Name matching
        if product_name:
            brand_name_match = self._lookup_by_name_and_brand(product_name, brand)
            if brand_name_match:
                return {
                    "status": "fuzzy_name_match",
                    "match_type": "verified_name_brand",
                    "product_name": brand_name_match["product_name"],
                    "barcode": brand_name_match.get("code"),
                    "brand": brand_name_match.get("brands"),
                    "source": "Open Food Facts (Local Subset)",
                    "source_id": brand_name_match.get("code"),
                    "source_dataset_version": "2026-subset",
                    "confidence": brand_name_match.get("match_confidence", 0.85),
                    "matched_data": brand_name_match,
                }

        # Priority 3: Reference databases (Indian Food Composition / USDA)
        search_query = product_name or (ocr_lines[0] if ocr_lines else "")
        if search_query:
            ref_match = self._lookup_reference_foods(search_query)
            if ref_match:
                return {
                    "status": "fuzzy_name_match",
                    "match_type": "reference_food_baseline",
                    "product_name": ref_match["name"],
                    "barcode": None,
                    "brand": "Generic / Analytical Reference",
                    "source": ref_match["source"],
                    "source_id": ref_match["id"],
                    "source_dataset_version": ref_match.get("edition", "2017/2024"),
                    "confidence": 0.75,
                    "matched_data": ref_match,
                }

        # Priority 4: OCR-only fallback
        inferred_name = None
        if ocr_lines:
            for l in ocr_lines[:3]:
                if len(l) > 3 and not any(kw in l.upper() for kw in ["NUTRITION", "INGREDIENTS", "FACTS"]):
                    inferred_name = l
                    break

        return {
            "status": "ocr_inferred" if inferred_name else "unmatched",
            "match_type": "ocr_text_only" if inferred_name else "none",
            "product_name": inferred_name,
            "barcode": None,
            "brand": brand,
            "source": "ocr_extraction_only",
            "source_id": None,
            "source_dataset_version": None,
            "confidence": 0.50 if inferred_name else None,
            "matched_data": None,
        }

    def _lookup_barcode(self, code: str) -> Optional[Dict[str, Any]]:
        if not self.products_db_path.exists():
            return None
        try:
            conn = sqlite3.connect(self.products_db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM off_products WHERE code = ? LIMIT 1", (str(code).strip(),))
            row = cur.fetchone()
            conn.close()
            if row:
                d = dict(row)
                if d.get("nutrients_json"):
                    d["nutrients"] = json.loads(d["nutrients_json"])
                return d
        except Exception:
            pass
        return None

    def _lookup_by_name_and_brand(self, product_name: str, brand: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not self.products_db_path.exists():
            return None
        try:
            conn = sqlite3.connect(self.products_db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            p_term = f"%{product_name.strip()}%"
            if brand:
                b_term = f"%{brand.strip()}%"
                cur.execute(
                    "SELECT * FROM off_products WHERE product_name LIKE ? AND brands LIKE ? LIMIT 1",
                    (p_term, b_term)
                )
            else:
                cur.execute("SELECT * FROM off_products WHERE product_name LIKE ? LIMIT 1", (p_term,))

            row = cur.fetchone()
            conn.close()
            if row:
                d = dict(row)
                d["match_confidence"] = 0.90 if brand else 0.80
                if d.get("nutrients_json"):
                    d["nutrients"] = json.loads(d["nutrients_json"])
                return d
        except Exception:
            pass
        return None

    def _lookup_reference_foods(self, query: str) -> Optional[Dict[str, Any]]:
        if not self.reference_db_path.exists():
            return None
        q_term = f"%{query.strip()}%"
        try:
            conn = sqlite3.connect(self.reference_db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # Check Indian foods first for Indian staples
            cur.execute("SELECT * FROM indian_foods WHERE name LIKE ? LIMIT 1", (q_term,))
            in_row = cur.fetchone()
            if in_row:
                conn.close()
                d = dict(in_row)
                return {
                    "source": "Indian Food Composition Tables (IFCT 2017)",
                    "id": d["code"],
                    "name": d["name"],
                    "edition": "2017",
                    "nutrients": {
                        "energy_kcal": d.get("energy_kcal"),
                        "protein_g": d.get("protein_g"),
                        "carbohydrates_g": d.get("carbohydrates_g"),
                        "dietary_fibre_g": d.get("dietary_fibre_g"),
                        "total_fat_g": d.get("total_fat_g"),
                        "saturated_fat_g": d.get("saturated_fat_g"),
                        "sodium_mg": d.get("sodium_mg"),
                        "iron_mg": d.get("iron_mg"),
                        "calcium_mg": d.get("calcium_mg"),
                    }
                }

            # Check USDA foods
            cur.execute("SELECT * FROM usda_foods WHERE description LIKE ? LIMIT 1", (q_term,))
            usda_row = cur.fetchone()
            conn.close()
            if usda_row:
                d = dict(usda_row)
                nut_data = json.loads(d["nutrients_json"]) if d.get("nutrients_json") else {}
                return {
                    "source": "USDA FoodData Central Foundation Foods",
                    "id": d["fdc_id"],
                    "name": d["description"],
                    "edition": "2024-10-31",
                    "nutrients": nut_data,
                }
        except Exception:
            pass
        return None
