"""Stage 6: Product and Nutrient Data Fusion.

Fuses OCR-extracted facts with database-matched nutrient facts.
Retains field-level provenance:
- 'declared': read directly from product packaging label.
- 'calculated': derived via deterministic mathematical relationships.
- 'reference_derived': derived from USDA FoodData Central or IFCT 2017.
- 'missing': absent from both label and database.

Detects conflicts between label claims and reference database baselines.
"""

from typing import Any, Dict, List, Optional, Tuple


class NutrientFusion:
    """Combines OCR label measurements with matched database records."""

    @classmethod
    def fuse_nutrients(
        cls,
        ocr_nutrients: Dict[str, Dict[str, Any]],
        matched_product: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Dict[str, Any]], List[str], List[str]]:
        """Merges label nutrients with product database record, auditing provenance and conflicts."""
        fused = {}
        missing_fields = []
        conflicting_fields = []

        db_nutrients = {}
        if matched_product and isinstance(matched_product.get("matched_data"), dict):
            matched_data = matched_product["matched_data"]
            db_nutrients = matched_data.get("nutrients") or {}

        for nut_name, item in ocr_nutrients.items():
            val = item.get("value")
            unit = item.get("unit", "g")
            status = item.get("status")
            conf = item.get("confidence")

            if status == "declared" and val is not None:
                # Retain declared value
                fused[nut_name] = {
                    "value": val,
                    "unit": unit,
                    "status": "declared",
                    "confidence": conf,
                    "source": "printed_package_label",
                }

                # Check conflict with DB if DB has this nutrient
                if nut_name in db_nutrients and db_nutrients[nut_name] is not None:
                    db_val = db_nutrients[nut_name]
                    # If relative difference exceeds 30%, flag conflict
                    if isinstance(db_val, (int, float)) and val > 0:
                        diff = abs(val - db_val) / val
                        if diff > 0.35:
                            conflicting_fields.append(
                                f"{nut_name}: declared on label={val}{unit}, reference db={db_val}{unit}"
                            )

            elif status in ("calculated", "declared"):
                fused[nut_name] = item

            else:
                # Field is missing on label; check if matched database can provide reference value
                if nut_name in db_nutrients and db_nutrients[nut_name] is not None:
                    db_val = db_nutrients[nut_name]
                    if isinstance(db_val, dict):
                        db_val = db_val.get("value")
                    if isinstance(db_val, (int, float)):
                        fused[nut_name] = {
                            "value": float(db_val),
                            "unit": unit,
                            "status": "reference_derived",
                            "confidence": 0.80,
                            "source": matched_product.get("source", "reference_database"),
                        }
                    else:
                        fused[nut_name] = {
                            "value": None,
                            "unit": unit,
                            "status": "missing",
                            "confidence": None,
                        }
                        missing_fields.append(nut_name)
                else:
                    fused[nut_name] = {
                        "value": None,
                        "unit": unit,
                        "status": "missing",
                        "confidence": None,
                    }
                    if nut_name in ["energy_kcal", "protein_g", "carbohydrates_g", "total_fat_g"]:
                        missing_fields.append(nut_name)

        return fused, missing_fields, conflicting_fields
