"""Stage 8: Output Construction and Schema Validation.

Assembles the full structured output across all pipeline stages
and enforces strict compliance against config/nutrient_schema.yaml.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import jsonschema
import yaml


class OutputBuilder:
    """Builds and validates the structured food intelligence output JSON."""

    def __init__(self, repo_root: Optional[Path] = None):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent.parent.parent
        else:
            self.repo_root = Path(repo_root)

        schema_file = self.repo_root / "config" / "nutrient_schema.yaml"
        if not schema_file.exists():
            raise FileNotFoundError(f"Schema definition not found at {schema_file}")
        self.schema = yaml.safe_load(schema_file.read_text(encoding="utf-8"))

    def build_payload(
        self,
        input_image: str,
        image_metadata: Dict[str, Any],
        ocr_result: Dict[str, Any],
        product_match: Dict[str, Any],
        ingredients: Dict[str, Any],
        nutrition: Dict[str, Any],
        calculated_package_totals: Dict[str, Any],
        evidence_based_alerts: List[Dict[str, Any]],
        missing_fields: List[str],
        conflicting_fields: List[str],
        source_verified: bool = False,
    ) -> Dict[str, Any]:
        """Assembles and validates payload."""

        # Determine review reasons
        review_reasons = []
        if ingredients.get("declared_allergens"):
            review_reasons.append("Declared allergens present on packaging.")
        if conflicting_fields:
            review_reasons.append(f"Conflicting nutrient baselines: {len(conflicting_fields)} discrepancies.")
        if len(missing_fields) > 2:
            review_reasons.append(f"Incomplete nutritional table: {len(missing_fields)} core fields missing.")

        manual_review_required = len(review_reasons) > 0 or not source_verified

        payload = {
            "input_image": str(input_image),
            "timestamp": datetime.now().isoformat(),
            "engine_version": "0.1.0",
            "image_metadata": {
                "width": image_metadata.get("width", 0),
                "height": image_metadata.get("height", 0),
                "format": image_metadata.get("format", "JPEG"),
                "preprocessing_applied": image_metadata.get("preprocessing_applied", []),
            },
            "ocr_result": {
                "engine": ocr_result.get("engine", "paddleocr"),
                "model_version": ocr_result.get("model_version", "PP-OCRv4"),
                "execution_time_sec": ocr_result.get("execution_time_sec", 0.0),
                "line_count": ocr_result.get("line_count", 0),
                "lines": ocr_result.get("lines", []),
            },
            "product_match": {
                "status": product_match.get("status", "unmatched"),
                "match_type": product_match.get("match_type", "none"),
                "product_name": product_match.get("product_name"),
                "barcode": product_match.get("barcode"),
                "brand": product_match.get("brand"),
                "source": product_match.get("source", "none"),
                "source_id": product_match.get("source_id"),
                "source_dataset_version": product_match.get("source_dataset_version"),
                "confidence": product_match.get("confidence"),
            },
            "ingredients": {
                "original_text": ingredients.get("original_text"),
                "parsed_ingredients": ingredients.get("parsed_ingredients", []),
                "declared_allergens": ingredients.get("declared_allergens", []),
                "potential_traces": ingredients.get("potential_traces", []),
                "review_required": ingredients.get("review_required", True),
            },
            "nutrition": {
                "basis": nutrition.get("basis", "per_100_g"),
                "serving_size_raw": nutrition.get("serving_size_raw"),
                "serving_size_g": nutrition.get("serving_size_g"),
                "serving_size_ml": nutrition.get("serving_size_ml"),
                "nutrients": nutrition.get("nutrients", {}),
            },
            "calculated_package_totals": {
                "package_weight_g": calculated_package_totals.get("package_weight_g"),
                "package_volume_ml": calculated_package_totals.get("package_volume_ml"),
                "calculation_method": calculated_package_totals.get("calculation_method", "none"),
                "calculated_nutrients": calculated_package_totals.get("calculated_nutrients", {}),
            },
            "evidence_based_alerts": evidence_based_alerts,
            "data_quality": {
                "missing_fields": missing_fields,
                "conflicting_fields": conflicting_fields,
                "source_verified": source_verified,
                "manual_review_required": manual_review_required,
                "review_reasons": review_reasons,
            },
        }

        # Strict JSON Schema validation
        jsonschema.validate(instance=payload, schema=self.schema)
        return payload
