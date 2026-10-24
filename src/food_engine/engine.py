"""Food Intelligence Engine - Unified End-to-End Orchestrator.

Orchestrates all 8 stages:
- Stage 1: Image Ingestion
- Stage 2: Pretrained OCR Inference
- Stage 3: Hierarchical Product Matching (Barcode -> Brand/Name -> Reference DB -> OCR)
- Stage 4: Ingredient and Declared Allergen Extraction
- Stage 5: Nutrition Table Extraction with Structured Missing-Value Status
- Stage 6: Provenance-Aware Nutrient Fusion and Conflict Detection
- Stage 7: Deterministic Nutrition Calculations (Package Totals, Unit Normalization)
- Stage 8: Evidence-Based Health Rules and Strict JSON Schema Validation
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
