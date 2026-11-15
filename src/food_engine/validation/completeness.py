"""Transparent Completeness Policy for Packaged Food Records.

Determines whether a product record (from barcode lookup or label OCR) provides
sufficient nutritional and ingredient facts to fulfill the food intelligence workflow.

Distinguishes:
- Present: field is declared or reliably available with a validated numeric value.
- Absent: field is missing from source record but expected for packaged food.
- Not Applicable: field is not applicable to product category (e.g., alcohol in snacks).

Provides:
- An explicit decision on whether back-of-package label scanning is recommended.
- Transparent reasons for any recommendation.
- Graceful handling of partial data when back-of-package label is unavailable.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# Core nutritional fields required for minimum nutrition assessment
CORE_MANDATORY_NUTRIENTS = (
    "energy_kcal",
    "protein_g",
    "carbohydrates_g",
    "total_fat_g",
)

# Core secondary fields that are expected on modern packaging
SECONDARY_EXPECTED_NUTRIENTS = (
    "sugars_g",
    "saturated_fat_g",
)

# Sodium or salt is mandatory on packaged food
SODIUM_OR_SALT = ("sodium_mg", "salt_g")


@dataclass
class CompletenessAudit:
    """Detailed audit of product record completeness."""
    is_complete: bool
    is_sufficient_for_basic_use: bool
    completeness_score: float  # 0.0 to 1.0
    present_fields: List[str] = field(default_factory=list)
    missing_fields: List[str] = field(default_factory=list)
    not_applicable_fields: List[str] = field(default_factory=list)
    label_scan_recommended: bool = False
    recommendation_reasons: List[str] = field(default_factory=list)
    can_continue_with_partial: bool = True


class CompletenessPolicy:
    """Evaluates whether product data meets required completeness standards."""

    @classmethod
    def audit_record(
        cls,
        product_record: Optional[Dict[str, Any]],
        category: Optional[str] = None,
    ) -> CompletenessAudit:
        """Audits product record for required identity, nutrients, and ingredients."""
        if not product_record or not isinstance(product_record, dict):
            return CompletenessAudit(
                is_complete=False,
                is_sufficient_for_basic_use=False,
                completeness_score=0.0,
                missing_fields=["product_identity", "energy", "macronutrients", "ingredients", "basis"],
                label_scan_recommended=True,
                recommendation_reasons=["No product record found for barcode."],
                can_continue_with_partial=False,
            )

        present = []
        missing = []
        not_applicable = []
        reasons = []

        # 1. Product Identity
        p_name = product_record.get("product_name")
        if p_name and str(p_name).strip():
            present.append("product_name")
        else:
            missing.append("product_name")
            reasons.append("Product name is missing or unknown.")

        brand = product_record.get("brand") or product_record.get("brands")
        if brand and str(brand).strip():
            present.append("brand")
        else:
            # Brand might be non-branded or unknown; not hard blocker
            missing.append("brand")

        # 2. Extract Nutrients Dict
        # Could be under 'nutrients', 'nutrition.nutrients', or flat in record
        nutrients = {}
        if "nutrition" in product_record and isinstance(product_record["nutrition"], dict):
            nutrients = product_record["nutrition"].get("nutrients", {})
        elif "nutrients" in product_record and isinstance(product_record["nutrients"], dict):
            nutrients = product_record["nutrients"]
        elif "matched_data" in product_record and isinstance(product_record["matched_data"], dict):
            nutrients = product_record["matched_data"].get("nutrients", {})

        def get_nutrient_value(k: str) -> Optional[float]:
            val = nutrients.get(k)
            if isinstance(val, dict):
                return val.get("value")
            if isinstance(val, (int, float)):
                return float(val)
            # Check Open Food Facts style field e.g. energy_100g, proteins_100g
            off_key = k.replace("_g", "_100g").replace("_mg", "_100g").replace("_kcal", "_100g")
            if off_key in product_record and product_record[off_key] is not None:
                try:
                    return float(product_record[off_key])
                except (ValueError, TypeError):
                    pass
            return None

        # 3. Energy Check (kcal or kJ)
        kcal = get_nutrient_value("energy_kcal")
        kj = get_nutrient_value("energy_kj")
        if kcal is not None or kj is not None:
            present.append("energy")
        else:
            missing.append("energy")
            reasons.append("Energy declaration (calories/kJ) is missing.")

        # 4. Mandatory Macronutrients
        for field_name in CORE_MANDATORY_NUTRIENTS:
            if field_name == "energy_kcal":
                continue
            val = get_nutrient_value(field_name)
            if val is not None:
                present.append(field_name)
            else:
                missing.append(field_name)

        if any(f in missing for f in ("protein_g", "carbohydrates_g", "total_fat_g")):
            reasons.append("One or more core macronutrients (protein, carbs, fat) are missing.")

        # 5. Secondary Expected Nutrients
        for field_name in SECONDARY_EXPECTED_NUTRIENTS:
            val = get_nutrient_value(field_name)
            if val is not None:
                present.append(field_name)
            else:
                missing.append(field_name)

        # 6. Sodium or Salt
        sod = get_nutrient_value("sodium_mg") or get_nutrient_value("sodium_100g")
        salt = get_nutrient_value("salt_g") or get_nutrient_value("salt_100g")
        if sod is not None or salt is not None:
            present.append("sodium_or_salt")
        else:
            missing.append("sodium_or_salt")
            reasons.append("Sodium/salt declaration is missing.")

        # 7. Serving Basis
        basis = None
        if "nutrition" in product_record and isinstance(product_record["nutrition"], dict):
            basis = product_record["nutrition"].get("basis")
        elif "basis" in product_record:
            basis = product_record.get("basis")

        if basis and basis != "unspecified":
            present.append("basis")
        else:
            # If values are explicitly per 100g from database
            if "energy_100g" in product_record or "proteins_100g" in product_record:
                present.append("basis")
            else:
                missing.append("basis")
                reasons.append("Serving basis (per 100g or per serving) is unspecified.")

        # 8. Ingredients List
        ing_text = None
        if "ingredients" in product_record and isinstance(product_record["ingredients"], dict):
            ing_text = product_record["ingredients"].get("original_text")
        elif "ingredients_text" in product_record:
            ing_text = product_record.get("ingredients_text")

        if ing_text and str(ing_text).strip():
            present.append("ingredients")
        else:
            missing.append("ingredients")
            reasons.append("Full ingredients list is missing.")

        # Category-specific not applicable adjustments
        # E.g. Bottled water or mineral water has no macronutrients
        if category and any(w in category.lower() for w in ["water", "mineral water", "spring water"]):
            for f in ["protein_g", "carbohydrates_g", "total_fat_g", "sugars_g", "saturated_fat_g"]:
                if f in missing:
                    missing.remove(f)
                    not_applicable.append(f)

        # Compute Score
        all_required = ["product_name", "energy", "protein_g", "carbohydrates_g", "total_fat_g", "sodium_or_salt", "ingredients", "basis"]
        present_required = [f for f in all_required if f in present]
        score = round(len(present_required) / len(all_required), 3)

        # Decision
        is_complete = len(missing) == 0
        is_sufficient_for_basic_use = (
            "product_name" in present
            and "energy" in present
            and ("protein_g" in present or "carbohydrates_g" in present or "total_fat_g" in present)
        )
        label_scan_recommended = not is_complete or len(reasons) > 0

        return CompletenessAudit(
            is_complete=is_complete,
            is_sufficient_for_basic_use=is_sufficient_for_basic_use,
            completeness_score=score,
            present_fields=sorted(present),
            missing_fields=sorted(missing),
            not_applicable_fields=sorted(not_applicable),
            label_scan_recommended=label_scan_recommended,
            recommendation_reasons=reasons,
            can_continue_with_partial=is_sufficient_for_basic_use,
        )
