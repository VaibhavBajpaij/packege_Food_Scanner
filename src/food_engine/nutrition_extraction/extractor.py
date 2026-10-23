"""Stage 5: Nutrition Table Facts Extraction.

Parses OCR lines to extract nutrition facts declarations, identifies serving basis,
extracts all standard macronutrients and micronutrients with explicit units,
and uses a structured missing-value status.

Enforces:
- Never assign 0 to an absent nutrient field. Absent fields are strictly marked 'missing'.
- Retains distinction between Sodium (mg) and Salt (g).
- Detects basis: per 100g, per 100ml, per serving, per piece, per package.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


NUTRIENT_REGEX_MAP = {
    "energy_kcal": [
        r"(?:energy|calories|calorie|energetic\s*value)\s*(?:[^\d\n]*?)(\d+(?:\.\d+)?)\s*(?:kcal|calories)?",
        r"(\d+(?:\.\d+)?)\s*kcal",
    ],
    "energy_kj": [
        r"(?:energy|energetic\s*value)\s*(?:[^\d\n]*?)(\d+(?:\.\d+)?)\s*kj",
        r"(\d+(?:\.\d+)?)\s*kj",
    ],
    "protein_g": [
        r"(?:protein|proteins)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "carbohydrates_g": [
        r"(?:total\s*carbohydrate|carbohydrates?|carbs?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "sugars_g": [
        r"(?:total\s*sugars?|sugars?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "added_sugars_g": [
        r"(?:added\s*sugars?|of\s*which\s*added\s*sugars?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "dietary_fibre_g": [
        r"(?:dietary\s*fib(?:re|er)|fib(?:re|er))\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "total_fat_g": [
        r"(?:total\s*fat|fat)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "saturated_fat_g": [
        r"(?:saturated\s*fat(?:ty\s*acids?)?|saturates?)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "trans_fat_g": [
        r"(?:trans\s*fat(?:ty\s*acids?)?|trans\s*fat)\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "cholesterol_mg": [
        r"cholesterol\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "sodium_mg": [
        r"sodium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "salt_g": [
        r"salt\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*g?",
    ],
    "iron_mg": [
        r"iron\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "calcium_mg": [
        r"calcium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "potassium_mg": [
        r"potassium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "zinc_mg": [
        r"zinc\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "magnesium_mg": [
        r"magnesium\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "vitamin_c_mg": [
        r"vitamin\s*c\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*mg?",
    ],
    "vitamin_d_mcg": [
        r"vitamin\s*d\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:mcg|µg|ug)?",
    ],
}

DEFAULT_UNITS = {
    "energy_kcal": "kcal",
    "energy_kj": "kJ",
    "protein_g": "g",
    "carbohydrates_g": "g",
    "sugars_g": "g",
    "added_sugars_g": "g",
    "dietary_fibre_g": "g",
    "total_fat_g": "g",
    "saturated_fat_g": "g",
    "trans_fat_g": "g",
    "cholesterol_mg": "mg",
    "sodium_mg": "mg",
    "salt_g": "g",
    "iron_mg": "mg",
    "calcium_mg": "mg",
    "potassium_mg": "mg",
    "zinc_mg": "mg",
    "magnesium_mg": "mg",
    "vitamin_c_mg": "mg",
    "vitamin_d_mcg": "mcg",
}


class NutritionExtractor:
    """Extracts nutrition facts from OCR lines with explicit basis and missing field audit."""

    @classmethod
    def extract(cls, ocr_lines: List[str]) -> Dict[str, Any]:
        full_text = "\n".join(ocr_lines)
        basis, serving_raw, serving_g, serving_ml = cls._detect_basis_and_serving(full_text)

        nutrients: Dict[str, Dict[str, Any]] = {}
        missing_fields: List[str] = []
        conflicting_fields: List[str] = []

        for field_name, patterns in NUTRIENT_REGEX_MAP.items():
            unit = DEFAULT_UNITS.get(field_name, "g")
            val, conf = cls._search_patterns(ocr_lines, patterns)

            if val is not None:
                nutrients[field_name] = {
                    "value": val,
                    "unit": unit,
                    "status": "declared",
                    "confidence": conf,
                }
            else:
                nutrients[field_name] = {
                    "value": None,
                    "unit": unit,
                    "status": "missing",
                    "confidence": None,
                }
                # Track important missing fields
                if field_name in ["energy_kcal", "protein_g", "carbohydrates_g", "total_fat_g", "sodium_mg", "salt_g"]:
                    missing_fields.append(field_name)

        # Internal consistency check: If sodium is missing but salt is declared, calculate sodium
        if nutrients["sodium_mg"]["status"] == "missing" and nutrients["salt_g"]["status"] == "declared":
            salt_val = nutrients["salt_g"]["value"]
            if salt_val is not None:
                # 1g salt ~ 400mg sodium
                calc_sodium = round(salt_val * 400.0, 2)
                nutrients["sodium_mg"] = {
                    "value": calc_sodium,
                    "unit": "mg",
                    "status": "calculated",
                    "confidence": 0.90,
                }
                if "sodium_mg" in missing_fields:
                    missing_fields.remove("sodium_mg")

        # Vice-versa: If salt is missing but sodium is declared
        elif nutrients["salt_g"]["status"] == "missing" and nutrients["sodium_mg"]["status"] == "declared":
            sod_val = nutrients["sodium_mg"]["value"]
            if sod_val is not None:
                calc_salt = round((sod_val / 1000.0) * 2.5, 3)
                nutrients["salt_g"] = {
                    "value": calc_salt,
                    "unit": "g",
                    "status": "calculated",
                    "confidence": 0.90,
                }
                if "salt_g" in missing_fields:
                    missing_fields.remove("salt_g")

        return {
            "basis": basis,
            "serving_size_raw": serving_raw,
            "serving_size_g": serving_g,
            "serving_size_ml": serving_ml,
            "nutrients": nutrients,
            "missing_fields": missing_fields,
            "conflicting_fields": conflicting_fields,
        }

    @classmethod
    def _detect_basis_and_serving(cls, text: str) -> Tuple[str, Optional[str], Optional[float], Optional[float]]:
        lower = text.lower()
        basis = "per_100_g"
        serving_raw = None
        serving_g = None
        serving_ml = None

        # Check explicit serving size declaration
        m_srv = re.search(r"serving\s*size\s*[:\-]?\s*([^\n,;]+)", lower)
        if m_srv:
            serving_raw = m_srv.group(1).strip()
            # Extract grams or ml from serving text
            mg = re.search(r"(\d+(?:\.\d+)?)\s*g\b", serving_raw)
            if mg:
                serving_g = float(mg.group(1))
            mml = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", serving_raw)
            if mml:
                serving_ml = float(mml.group(1))

        # Check basis
        if "per 100 ml" in lower or "per 100ml" in lower or "/100 ml" in lower or "/100ml" in lower:
            basis = "per_100_ml"
        elif "per 100 g" in lower or "per 100g" in lower or "/100 g" in lower or "/100g" in lower:
            basis = "per_100_g"
        elif "per serving" in lower or "/serving" in lower:
            basis = "per_serving"
        elif "per piece" in lower or "per biscuit" in lower:
            basis = "per_piece"
        elif "per package" in lower or "per pack" in lower:
            basis = "per_package"

        return basis, serving_raw, serving_g, serving_ml

    @classmethod
    def _search_patterns(cls, lines: List[str], patterns: List[str]) -> Tuple[Optional[float], Optional[float]]:
        for line in lines:
            clean_l = line.strip().lower()
            for pat in patterns:
                m = re.search(pat, clean_l, re.IGNORECASE)
                if m:
                    try:
                        val = float(m.group(1))
                        # Basic confidence heuristic
                        conf = 0.90 if len(lines) > 0 else 0.70
                        return val, conf
                    except (ValueError, IndexError):
                        continue
        return None, None
