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

    @classmethod
    def format_text_report(cls, payload: Dict[str, Any]) -> str:
        """Formats the structured output dictionary into a human-readable report."""
        pm = payload.get("product_match", {})
        nut = payload.get("nutrition", {})
        nutrients = nut.get("nutrients", {})
        ing = payload.get("ingredients", {})
        alerts = payload.get("evidence_based_alerts", [])
        dq = payload.get("data_quality", {})
        ocr_res = payload.get("ocr_result", {})

        p_name = pm.get("product_name") or "Packaged Food Item"
        brand = pm.get("brand") or "Brand Not Stated"
        barcode_str = pm.get("barcode") or "None"
        match_status = pm.get("status", "unmatched").upper()
        basis = nut.get("basis", "per_100_g").replace("_", " ")

        lines = [
            "=" * 78,
            "                   FOOD INTELLIGENCE NUTRITION REPORT",
            "=" * 78,
            f"PRODUCT:     {p_name} ({brand})",
            f"BARCODE:     {barcode_str} [{match_status}]",
            f"SOURCE:      {pm.get('source', 'Packaging Label OCR')}",
            f"BASIS:       {basis}",
        ]
        if nut.get("serving_size_raw"):
            lines.append(f"SERVING:     {nut.get('serving_size_raw')}")
        if ocr_res.get("engine"):
            lines.append(f"OCR ENGINE:  {ocr_res.get('engine')} ({ocr_res.get('model_version')}) - {ocr_res.get('line_count', 0)} lines extracted")

        lines.append("-" * 78)
        lines.append(f"{'NUTRIENT':<24} | {'AMOUNT':<16} | {'PROVENANCE / STATUS':<30}")
        lines.append("-" * 78)

        # Standard nutrient display order
        display_order = [
            ("energy_kcal", "Energy (Calories)"),
            ("energy_kj", "Energy (kJ)"),
            ("protein_g", "Protein"),
            ("carbohydrates_g", "Total Carbohydrate"),
            ("sugars_g", "  of which Sugars"),
            ("added_sugars_g", "  of which Added Sugars"),
            ("dietary_fibre_g", "Dietary Fibre"),
            ("total_fat_g", "Total Fat"),
            ("saturated_fat_g", "  of which Saturated Fat"),
            ("trans_fat_g", "  of which Trans Fat"),
            ("cholesterol_mg", "Cholesterol"),
            ("sodium_mg", "Sodium"),
            ("salt_g", "Salt (NaCl)"),
            ("calcium_mg", "Calcium"),
            ("iron_mg", "Iron"),
            ("potassium_mg", "Potassium"),
            ("vitamin_c_mg", "Vitamin C"),
            ("vitamin_d_mcg", "Vitamin D"),
        ]

        for key, label in display_order:
            item = nutrients.get(key)
            if not item:
                continue
            val = item.get("value")
            unit = item.get("unit", "")
            status = item.get("status", "missing")
            ub = item.get("upper_bound", False)
            comp = item.get("comparator", "<") if ub else ""

            if val is not None:
                amt_str = f"{comp} {val} {unit}".strip()
                if status == "declared":
                    badge = "[DECLARED]"
                elif status == "calculated":
                    badge = "[CALCULATED]"
                elif status == "reference_derived":
                    badge = "[REFERENCE_DB]"
                else:
                    badge = f"[{status.upper()}]"
            else:
                amt_str = "Not Declared"
                badge = "[MISSING]"

            lines.append(f"{label:<24} | {amt_str:<16} | {badge:<30}")

        lines.append("-" * 78)
        lines.append("ALLERGENS & INGREDIENTS")
        lines.append("-" * 78)
        decl_allergens = ing.get("declared_allergens", [])
        lines.append(f"Declared Allergens: {', '.join(decl_allergens) if decl_allergens else 'None declared on packaging'}")
        traces = ing.get("potential_traces", [])
        if traces:
            lines.append(f"Potential Traces:   {', '.join(traces)}")
        ing_text = ing.get("original_text")
        if ing_text:
            lines.append(f"Ingredients List:   {ing_text[:200]}{'...' if len(ing_text) > 200 else ''}")

        if alerts:
            lines.append("-" * 78)
            lines.append("EVIDENCE-BASED HEALTH ALERTS (WHO / FSSAI Guidelines)")
            lines.append("-" * 78)
            for a in alerts:
                sev = a.get("severity", "info").upper()
                lines.append(f"[{sev}] {a.get('title')}: {a.get('reason')}")

        if dq.get("conflicting_fields"):
            lines.append("-" * 78)
            lines.append("SOURCE DISCREPANCIES AUDIT")
            lines.append("-" * 78)
            for c in dq.get("conflicting_fields", []):
                lines.append(f"* {c}")

        lines.append("=" * 78)
        return "\n".join(lines)


format_text_report = OutputBuilder.format_text_report

