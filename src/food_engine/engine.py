"""Food Intelligence Engine - Unified End-to-End Orchestrator.

Orchestrates all 8 stages of the Barcode-First Food Intelligence Workflow:
- Step 1: Scan Barcode First (Format check, checksum verification, leading-zero normalization, OFF lookup)
- Step 2: Completeness Audit & Label Scan Decision (Evaluate identity, energy, macros, ingredients, basis)
- Step 3: Ingestion of Back-of-Package Label (Single image or separate nutrition and ingredients panels)
- Step 4: Genuine Pretrained OCR Inference (PaddleOCR PP-OCRv4 with deskewing and MKLDNN patch)
- Step 5: Nutrition Table Extraction with Structured Missing-Value Status and Inequality Bounds (<1g)
- Step 6: Provenance-Aware Nutrient Fusion and Non-Overwriting Precedence
- Step 7: Deterministic Nutrition Calculations (Package Totals, Unit Normalization)
- Step 8: Evidence-Based Health Rules and Structured JSON Schema Validation
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from PIL import Image

from food_engine.ocr.image_ingestion import ImageIngestion
from food_engine.ocr.layout_assembly import row_group_lines
from food_engine.ocr.ocr_engine import OCREngine
from food_engine.product_matching.matcher import ProductMatcher
from food_engine.product_matching.nutrient_fusion import NutrientFusion
from food_engine.ingredient_parser.parser import IngredientParser
from food_engine.nutrition_extraction.extractor import NutritionExtractor
from food_engine.nutrition_calculation.calculator import NutritionCalculator
from food_engine.reporting.health_rules import EvidenceBasedHealthRules
from food_engine.reporting.output_builder import OutputBuilder
from food_engine.validation.barcode_validator import BarcodeValidator
from food_engine.validation.completeness import CompletenessPolicy


CORE_FIELDS = (
    "energy_kcal", "total_fat_g", "carbohydrates_g", "protein_g",
)


def _core_score(nutrition: Dict[str, Any]) -> int:
    nuts = nutrition.get("nutrients", {})
    score = sum(1 for field in CORE_FIELDS if nuts.get(field, {}).get("value") is not None)
    if (
        nuts.get("sodium_mg", {}).get("value") is not None
        or nuts.get("salt_g", {}).get("value") is not None
    ):
        score += 1
    return score


class FoodIntelligenceEngine:
    """Complete, standalone, offline food intelligence engine."""

    def __init__(self, repo_root: Optional[Path] = None, use_gpu: bool = False):
        if repo_root is None:
            self.repo_root = Path(__file__).resolve().parent.parent.parent
        else:
            self.repo_root = Path(repo_root)

        self.ocr_engine = OCREngine(repo_root=self.repo_root, use_gpu=use_gpu)
        self.product_matcher = ProductMatcher(repo_root=self.repo_root)
        self.output_builder = OutputBuilder(repo_root=self.repo_root)

    def scan_barcode(
        self,
        barcode: Optional[str],
        allow_online: bool = False,
        force_label_scan: bool = False,
    ) -> Dict[str, Any]:
        """Step 1 & 2: Scans a packaged food barcode first and assesses completeness.

        Returns:
            Structured dictionary detailing:
            - Barcode normalization & validation verdict
            - Product database match (if found in Open Food Facts local subset or live API)
            - Completeness audit across energy, macronutrients, ingredients, and basis
            - Action required: 'proceed' if complete, or 'scan_label_recommended' / 'scan_label_required'
            - Transparent recommendation reasons and prompt message
        """
        val_res = BarcodeValidator.validate(barcode)

        if not val_res.is_valid:
            return {
                "workflow_step": "barcode_scan",
                "barcode_input": str(barcode) if barcode is not None else None,
                "barcode_validation": {
                    "is_valid": False,
                    "format": val_res.format,
                    "normalized_code": val_res.normalized_code,
                    "status": val_res.status,
                    "error_message": val_res.error_message,
                },
                "product_match": {
                    "status": "unmatched",
                    "match_type": "invalid_barcode" if val_res.status != "absent" else "none",
                    "product_name": None,
                    "barcode": val_res.normalized_code or (str(barcode) if barcode else None),
                    "brand": None,
                    "source": "none",
                    "confidence": 0.0,
                    "matched_data": None,
                },
                "completeness_audit": {
                    "is_complete": False,
                    "is_sufficient_for_basic_use": False,
                    "completeness_score": 0.0,
                    "present_fields": [],
                    "missing_fields": [
                        "product_name", "energy", "protein_g", "carbohydrates_g",
                        "total_fat_g", "sodium_or_salt", "ingredients", "basis",
                    ],
                    "not_applicable_fields": [],
                    "label_scan_recommended": True,
                    "recommendation_reasons": [
                        val_res.error_message or "Barcode is invalid or absent."
                    ],
                    "can_continue_with_partial": False,
                },
                "action_required": "scan_label_required",
                "prompt_message": f"Barcode is {val_res.status} ({val_res.error_message or 'No barcode provided'}). Please capture the back-of-package label.",
                "product_data": None,
            }

        # Valid barcode: lookup product
        matched_product = self.product_matcher.match(
            barcode=val_res.normalized_code,
            allow_online=allow_online,
        )

        is_matched = matched_product.get("status") == "exact_barcode_match"
        matched_data = matched_product.get("matched_data") if is_matched else None

        audit = CompletenessPolicy.audit_record(matched_data or matched_product)

        if is_matched:
            if audit.is_complete and not force_label_scan:
                action_required = "proceed"
                prompt_message = (
                    f"Product '{matched_product.get('product_name')}' found with complete nutrition facts "
                    f"and ingredients ({matched_product.get('source', 'database')}). You may proceed, "
                    f"or capture the back of package to verify physical packaging."
                )
            else:
                action_required = "scan_label_recommended"
                prompt_message = (
                    f"Product '{matched_product.get('product_name')}' found, but nutrition information is incomplete "
                    f"(missing: {', '.join(audit.missing_fields[:4])}). Back-of-package label scan is recommended."
                )
        else:
            action_required = "scan_label_required"
            prompt_message = (
                f"Barcode '{val_res.normalized_code}' ({val_res.format}) is valid, but the product was not found in the "
                f"database. Please capture the back-of-package label to extract nutrition facts and ingredients."
            )

        # Build normalized product_data for quick display
        product_data = None
        if is_matched and matched_data:
            product_data = {
                "product_name": matched_product.get("product_name"),
                "brand": matched_product.get("brand"),
                "barcode": matched_product.get("barcode"),
                "source": matched_product.get("source"),
                "serving_size": matched_data.get("serving_size"),
                "ingredients_text": matched_data.get("ingredients_text"),
                "nutrients": matched_data.get("nutrients") or {},
            }

        return {
            "workflow_step": "barcode_scan",
            "barcode_input": str(barcode),
            "barcode_validation": {
                "is_valid": True,
                "format": val_res.format,
                "normalized_code": val_res.normalized_code,
                "status": "valid",
                "error_message": None,
            },
            "product_match": matched_product,
            "completeness_audit": {
                "is_complete": audit.is_complete,
                "is_sufficient_for_basic_use": audit.is_sufficient_for_basic_use,
                "completeness_score": audit.completeness_score,
                "present_fields": audit.present_fields,
                "missing_fields": audit.missing_fields,
                "not_applicable_fields": audit.not_applicable_fields,
                "label_scan_recommended": audit.label_scan_recommended,
                "recommendation_reasons": audit.recommendation_reasons,
                "can_continue_with_partial": audit.can_continue_with_partial,
            },
            "action_required": action_required,
            "prompt_message": prompt_message,
            "product_data": product_data,
        }

    def scan_package_label(
        self,
        label_image: Optional[Union[str, Path, bytes, Image.Image]] = None,
        nutrition_image: Optional[Union[str, Path, bytes, Image.Image]] = None,
        ingredients_image: Optional[Union[str, Path, bytes, Image.Image]] = None,
        barcode: Optional[str] = None,
        package_weight_g: Optional[float] = None,
        package_volume_ml: Optional[float] = None,
        product_name_hint: Optional[str] = None,
        brand_hint: Optional[str] = None,
        override_ocr_lines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Step 3 to 8: Captures back-of-package label, supporting single or separate images."""
        if nutrition_image is not None and ingredients_image is not None:
            # Separate images supplied: nutrition table + ingredients list
            return self._process_dual_images(
                nutrition_image=nutrition_image,
                ingredients_image=ingredients_image,
                barcode=barcode,
                package_weight_g=package_weight_g,
                package_volume_ml=package_volume_ml,
                product_name_hint=product_name_hint,
                brand_hint=brand_hint,
            )

        target_img = label_image if label_image is not None else nutrition_image
        if target_img is None:
            raise ValueError("Must provide either 'label_image' or 'nutrition_image'.")

        return self.process_image(
            image_input=target_img,
            barcode=barcode,
            package_weight_g=package_weight_g,
            package_volume_ml=package_volume_ml,
            product_name_hint=product_name_hint,
            brand_hint=brand_hint,
            override_ocr_lines=override_ocr_lines,
        )

    def _process_dual_images(
        self,
        nutrition_image: Union[str, Path, bytes, Image.Image],
        ingredients_image: Union[str, Path, bytes, Image.Image],
        barcode: Optional[str] = None,
        package_weight_g: Optional[float] = None,
        package_volume_ml: Optional[float] = None,
        product_name_hint: Optional[str] = None,
        brand_hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Processes separate photographs for nutrition table and ingredient panel."""
        _, meta_nut = ImageIngestion.load_image(nutrition_image)
        ocr_nut = self.ocr_engine.run_ocr(nutrition_image)
        assembled_nut = row_group_lines(ocr_nut["lines"])
        extracted_nutrition = NutritionExtractor.extract_from_ocr(ocr_nut["lines"])

        _, meta_ing = ImageIngestion.load_image(ingredients_image)
        ocr_ing = self.ocr_engine.run_ocr(ingredients_image)
        assembled_ing = row_group_lines(ocr_ing["lines"])
        ing_text_lines = [item["text"] for item in assembled_ing]
        ingredients = IngredientParser.parse_from_ocr_lines(ing_text_lines)

        combined_lines = [item["text"] for item in assembled_nut] + ing_text_lines
        combined_ocr_res = {
            "engine": ocr_nut.get("engine", "paddleocr"),
            "model_version": ocr_nut.get("model_version", "PP-OCRv4"),
            "execution_time_sec": round(ocr_nut.get("execution_time_sec", 0.0) + ocr_ing.get("execution_time_sec", 0.0), 3),
            "line_count": len(ocr_nut.get("lines", [])) + len(ocr_ing.get("lines", [])),
            "lines": ocr_nut.get("lines", []) + ocr_ing.get("lines", []),
        }

        # Stage 3: Product Matching
        matched_product = self.product_matcher.match(
            barcode=barcode,
            product_name=product_name_hint,
            brand=brand_hint,
            ocr_lines=combined_lines,
        )

        # Stage 6: Nutrient Fusion & Provenance Tracking
        fused_nutrients, missing_fields, conflicting_fields = NutrientFusion.fuse_nutrients(
            ocr_nutrients=extracted_nutrition["nutrients"],
            matched_product=matched_product,
        )
        nutrition_payload = {
            "basis": extracted_nutrition["basis"],
            "serving_size_raw": extracted_nutrition["serving_size_raw"],
            "serving_size_g": extracted_nutrition["serving_size_g"],
            "serving_size_ml": extracted_nutrition["serving_size_ml"],
            "nutrients": fused_nutrients,
        }

        # Stage 7: Deterministic Nutrition Calculation (Package Totals)
        package_totals = NutritionCalculator.calculate_package_totals(
            nutrients_per_100=fused_nutrients,
            package_weight_g=package_weight_g,
            package_volume_ml=package_volume_ml,
            basis=extracted_nutrition["basis"],
        )

        # Stage 8: Evidence-Based Health Rules
        alerts = EvidenceBasedHealthRules.evaluate(
            nutrients=fused_nutrients,
            declared_allergens=ingredients["declared_allergens"],
            potential_traces=ingredients["potential_traces"],
            basis=extracted_nutrition["basis"],
        )

        source_verified = matched_product.get("status") in ("exact_barcode_match", "fuzzy_name_match")

        image_desc = f"dual_images(nutrition={Path(str(nutrition_image)).name if isinstance(nutrition_image, (str, Path)) else 'in_memory'}, ingredients={Path(str(ingredients_image)).name if isinstance(ingredients_image, (str, Path)) else 'in_memory'})"

        return self.output_builder.build_payload(
            input_image=image_desc,
            image_metadata=meta_nut,
            ocr_result=combined_ocr_res,
            product_match=matched_product,
            ingredients=ingredients,
            nutrition=nutrition_payload,
            calculated_package_totals=package_totals,
            evidence_based_alerts=alerts,
            missing_fields=missing_fields,
            conflicting_fields=conflicting_fields,
            source_verified=source_verified,
        )

    def process_image(
        self,
        image_input: Union[str, Path, bytes, Image.Image],
        barcode: Optional[str] = None,
        package_weight_g: Optional[float] = None,
        package_volume_ml: Optional[float] = None,
        product_name_hint: Optional[str] = None,
        brand_hint: Optional[str] = None,
        override_ocr_lines: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Runs the complete 8-stage food intelligence pipeline on an input image."""

        # Stage 1 & 2: Ingestion & OCR
        if isinstance(image_input, Image.Image):
            _, meta = ImageIngestion.load_image(image_input)
            ocr_res = self.ocr_engine.run_ocr(image_input)
            image_name = getattr(image_input, "filename", "pil_image_in_memory")
        else:
            image_path = str(image_input)
            _, meta = ImageIngestion.load_image(image_input)
            ocr_res = self.ocr_engine.run_ocr(image_input)
            image_name = Path(image_path).name if isinstance(image_input, (str, Path)) else "in_memory_bytes"

        # If explicit OCR lines provided (for testing or pipeline chaining)
        if override_ocr_lines is not None:
            ocr_res["lines"] = [
                {"text": l, "confidence": 0.95, "bounding_box": []} for l in override_ocr_lines
            ]
            ocr_res["line_count"] = len(override_ocr_lines)

        # Merge OCR fragments sharing a print row (recovered from bounding
        # boxes) so nutrition-table rows arrive whole rather than split.
        assembled_lines = row_group_lines(ocr_res["lines"])
        ocr_res["assembled_lines"] = assembled_lines
        ocr_text_lines = [item["text"] for item in assembled_lines]

        # Pre-check nutrition extraction so OCR can be rescued before stages 3-5.
        extracted_nutrition = NutritionExtractor.extract_from_ocr(ocr_res["lines"])

        # Small print and high-resolution panels are frequently under-detected
        # at native scale. If core nutrients are missing, retry once upscaled
        # and keep the result only when it recovers more core fields.
        if override_ocr_lines is None and _core_score(extracted_nutrition) <= 3:
            upscaled = self.ocr_engine.run_ocr(image_input, scale=1.5)
            if upscaled.get("lines"):
                alt_nutrition = NutritionExtractor.extract_from_ocr(upscaled["lines"])
                if _core_score(alt_nutrition) > _core_score(extracted_nutrition):
                    # Keep fields that only the native-scale pass recovered.
                    for field_name, native in extracted_nutrition["nutrients"].items():
                        alt = alt_nutrition["nutrients"].get(field_name, {})
                        if alt.get("value") is None and native.get("value") is not None:
                            alt_nutrition["nutrients"][field_name] = native
                    ocr_res = upscaled
                    assembled_lines = row_group_lines(ocr_res["lines"])
                    ocr_res["assembled_lines"] = assembled_lines
                    ocr_text_lines = [item["text"] for item in assembled_lines]
                    extracted_nutrition = alt_nutrition

        # Stage 3: Product Matching
        matched_product = self.product_matcher.match(
            barcode=barcode,
            product_name=product_name_hint,
            brand=brand_hint,
            ocr_lines=ocr_text_lines,
        )

        # Stage 4: Ingredient and Allergen Parsing
        ingredients = IngredientParser.parse_from_ocr_lines(ocr_text_lines)

        # Stage 5: Nutrition Table Extraction result selected above.

        # Stage 6: Nutrient Fusion & Provenance Tracking
        fused_nutrients, missing_fields, conflicting_fields = NutrientFusion.fuse_nutrients(
            ocr_nutrients=extracted_nutrition["nutrients"],
            matched_product=matched_product,
        )
        nutrition_payload = {
            "basis": extracted_nutrition["basis"],
            "serving_size_raw": extracted_nutrition["serving_size_raw"],
            "serving_size_g": extracted_nutrition["serving_size_g"],
            "serving_size_ml": extracted_nutrition["serving_size_ml"],
            "nutrients": fused_nutrients,
        }

        # Stage 7: Deterministic Nutrition Calculation (Package Totals)
        package_totals = NutritionCalculator.calculate_package_totals(
            nutrients_per_100=fused_nutrients,
            package_weight_g=package_weight_g,
            package_volume_ml=package_volume_ml,
            basis=extracted_nutrition["basis"],
        )

        # Stage 8: Evidence-Based Health Rules
        alerts = EvidenceBasedHealthRules.evaluate(
            nutrients=fused_nutrients,
            declared_allergens=ingredients["declared_allergens"],
            potential_traces=ingredients["potential_traces"],
            basis=extracted_nutrition["basis"],
        )

        source_verified = matched_product.get("status") in ("exact_barcode_match", "fuzzy_name_match")

        # Stage 8: Output Construction and Schema Validation
        final_payload = self.output_builder.build_payload(
            input_image=str(image_name),
            image_metadata=meta,
            ocr_result=ocr_res,
            product_match=matched_product,
            ingredients=ingredients,
            nutrition=nutrition_payload,
            calculated_package_totals=package_totals,
            evidence_based_alerts=alerts,
            missing_fields=missing_fields,
            conflicting_fields=conflicting_fields,
            source_verified=source_verified,
        )

        return final_payload
