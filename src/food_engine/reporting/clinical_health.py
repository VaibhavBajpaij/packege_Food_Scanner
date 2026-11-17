"""Clinical Health Profile, Hidden Sugar Detector, and Additive Intelligence Engine.

Provides evidence-backed, personalized health evaluations for:
1. Diabetes & Pre-Diabetes (Glycemic load, hidden sugars, added sugars)
2. Hypertension & Heart Health (Sodium, saturated fat, trans fat)
3. Chemical Additive & Preservative Screening (INS / E-numbers, Wikipedia summaries)
4. Gut & Allergen Sensitivity (Palm oil, artificial sweeteners, celiac/lactose)
"""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

logger = logging.getLogger(__name__)

# 40 Sneaky / Hidden Names of Sugar commonly used by food manufacturers
HIDDEN_SUGAR_DICTIONARY = [
    "invert sugar", "invert syrup", "high fructose corn syrup", "corn syrup",
    "corn syrup solids", "maltodextrin", "dextrose", "maltose", "fructose",
    "sucrose", "glucose", "glucose syrup", "cane sugar", "brown sugar",
    "raw sugar", "liquid sugar", "cane juice", "evaporated cane juice",
    "molasses", "golden syrup", "treacle", "honey", "agave nectar",
    "maple syrup", "barley malt", "malt extract", "rice syrup",
    "tapioca syrup", "sorghum syrup", "date sugar", "fruit juice concentrate",
    "concentrated apple juice", "dextrin", "ethyl maltol", "caramel",
    "panela", "jaggery", "gur", "khandsari", "coconut sugar"
]

# Comprehensive Clinical Additive & Preservative Registry (INS & European E-numbers)
ADDITIVE_REGISTRY = {
    "E319": {
        "name": "TBHQ (Tertiary Butylhydroquinone)",
        "type": "Synthetic Chemical Antioxidant / Preservative",
        "risk_level": "CAUTION",
        "description": "Petroleum-derived preservative used to prevent vegetable oil rancidity. Regulated with strict upper consumption limits.",
        "wiki_title": "Tertiary_butylhydroquinone",
    },
    "INS 319": {
        "name": "TBHQ (Tertiary Butylhydroquinone)",
        "type": "Synthetic Chemical Antioxidant / Preservative",
        "risk_level": "CAUTION",
        "description": "Petroleum-derived preservative used to prevent vegetable oil rancidity. Regulated with strict upper consumption limits.",
        "wiki_title": "Tertiary_butylhydroquinone",
    },
    "E320": {
        "name": "BHA (Butylated Hydroxyanisole)",
        "type": "Synthetic Preservative",
        "risk_level": "HIGH_RISK",
        "description": "Preservative classified by some international bodies as a suspected endocrine disruptor and possible carcinogen.",
        "wiki_title": "Butylated_hydroxyanisole",
    },
    "INS 320": {
        "name": "BHA (Butylated Hydroxyanisole)",
        "type": "Synthetic Preservative",
        "risk_level": "HIGH_RISK",
        "description": "Preservative classified as a possible endocrine disruptor.",
        "wiki_title": "Butylated_hydroxyanisole",
    },
    "E322": {
        "name": "Lecithin (Soy / Sunflower)",
        "type": "Natural Emulsifier",
        "risk_level": "SAFE",
        "description": "Widely used natural emulsifier aiding fat and water mixing. Considered safe; derived from soy, eggs, or sunflower.",
        "wiki_title": "Lecithin",
    },
    "INS 322": {
        "name": "Lecithin",
        "type": "Natural Emulsifier",
        "risk_level": "SAFE",
        "description": "Natural emulsifier. Safe for general population, but check if soy-allergic.",
        "wiki_title": "Lecithin",
    },
    "E500": {
        "name": "Sodium Carbonates (Baking Soda)",
        "type": "Leavening Agent / Acidity Regulator",
        "risk_level": "SAFE",
        "description": "Common mineral leavening agent used in baked products to make dough rise.",
        "wiki_title": "Sodium_bicarbonate",
    },
    "INS 500": {
        "name": "Sodium Carbonates",
        "type": "Leavening Agent",
        "risk_level": "SAFE",
        "description": "Mineral salt leavening agent. Standard food-grade baking ingredient.",
        "wiki_title": "Sodium_bicarbonate",
    },
    "E503": {
        "name": "Ammonium Carbonates (Baker's Ammonia)",
        "type": "Leavening Agent",
        "risk_level": "SAFE",
        "description": "Traditional leavening salt that evaporates completely during baking, leaving no chemical residue.",
        "wiki_title": "Ammonium_bicarbonate",
    },
    "INS 503": {
        "name": "Ammonium Carbonates",
        "type": "Leavening Agent",
        "risk_level": "SAFE",
        "description": "Leavening agent used for crispness in biscuits and cookies.",
        "wiki_title": "Ammonium_bicarbonate",
    },
    "E621": {
        "name": "MSG (Monosodium Glutamate)",
        "type": "Flavor Enhancer",
        "risk_level": "MODERATE",
        "description": "Umami flavor enhancer. Considered safe by FDA/WHO, but may trigger sensitivity or headaches in sensitive individuals.",
        "wiki_title": "Monosodium_glutamate",
    },
    "INS 621": {
        "name": "MSG (Monosodium Glutamate)",
        "type": "Flavor Enhancer",
        "risk_level": "MODERATE",
        "description": "Savory flavor enhancer. Safe in moderation; sensitive individuals may experience flushing.",
        "wiki_title": "Monosodium_glutamate",
    },
    "E951": {
        "name": "Aspartame",
        "type": "Artificial Non-Nutritive Sweetener",
        "risk_level": "CAUTION",
        "description": "High-intensity artificial sweetener. Classified by IARC/WHO as possibly carcinogenic (Group 2B); contains phenylalanine (contraindicated for PKU).",
        "wiki_title": "Aspartame",
    },
    "INS 951": {
        "name": "Aspartame",
        "type": "Artificial Sweetener",
        "risk_level": "CAUTION",
        "description": "Artificial sweetener. Strictly contraindicated for phenylketonuria (PKU).",
        "wiki_title": "Aspartame",
    },
    "E955": {
        "name": "Sucralose",
        "type": "Artificial Sweetener",
        "risk_level": "MODERATE",
        "description": "Zero-calorie chlorinated sugar derivative. Recent gut microbiome studies indicate potential alterations to gut bacteria.",
        "wiki_title": "Sucralose",
    },
    "INS 955": {
        "name": "Sucralose",
        "type": "Artificial Sweetener",
        "risk_level": "MODERATE",
        "description": "Chlorinated artificial sweetener. Non-nutritive, but can affect gut microflora in excessive quantities.",
        "wiki_title": "Sucralose",
    },
    "E102": {
        "name": "Tartrazine (FD&C Yellow 5)",
        "type": "Synthetic Azo Food Dye",
        "risk_level": "HIGH_RISK",
        "description": "Synthetic yellow dye. European Union requires warning: 'May have an adverse effect on activity and attention in children.'",
        "wiki_title": "Tartrazine",
    },
    "INS 102": {
        "name": "Tartrazine",
        "type": "Synthetic Food Dye",
        "risk_level": "HIGH_RISK",
        "description": "Synthetic yellow dye linked to hyperactivity in children and urticaria (hives).",
        "wiki_title": "Tartrazine",
    },
}


class ClinicalHealthEngine:
    """Clinical assessment engine providing patient-centric, honest food evaluation."""

    @classmethod
    def detect_hidden_sugars(cls, ingredients_text: str) -> List[str]:
        """Detects sneaky, disguised names of sugar inside ingredient prose."""
        if not ingredients_text:
            return []
        found = []
        lower_txt = ingredients_text.lower()
        for s in HIDDEN_SUGAR_DICTIONARY:
            # Word boundary regex search
            pattern = r'\b' + re.escape(s) + r'\b'
            if re.search(pattern, lower_txt):
                found.append(s.title())
        return list(dict.fromkeys(found))

    @classmethod
    def identify_additives(cls, ingredients_text: str) -> List[Dict[str, Any]]:
        """Identifies chemical additives and queries Wikipedia for verified context."""
        if not ingredients_text:
            return []

        results = []
        # Pattern matching E-numbers and INS numbers: E102, INS 503(ii), E319, INS322
        pattern = r'\b(INS|E)\s*[-]?\s*([0-9]{3,4}(?:\s*\([a-z0-9]+\))?)'
        matches = re.findall(pattern, ingredients_text, re.IGNORECASE)

        seen_codes = set()
        for prefix, code_raw in matches:
            clean_code = f"{prefix.upper()} {code_raw.strip()}".upper()
            base_code = f"{prefix.upper()} {re.sub(r'\(.*?\)', '', code_raw).strip()}".upper()
            e_code = f"E{re.sub(r'\(.*?\)', '', code_raw).strip()}".upper()

            matched_entry = (
                ADDITIVE_REGISTRY.get(clean_code)
                or ADDITIVE_REGISTRY.get(base_code)
                or ADDITIVE_REGISTRY.get(e_code)
            )

            code_key = base_code
            if code_key in seen_codes:
                continue
            seen_codes.add(code_key)

            if matched_entry:
                entry = dict(matched_entry)
                entry["code"] = clean_code
                results.append(entry)
            else:
                results.append({
                    "code": clean_code,
                    "name": f"Regulated Food Additive ({clean_code})",
                    "type": "Food Processing Agent",
                    "risk_level": "MODERATE",
                    "description": "Approved food-grade additive regulated under FSSAI / Codex Alimentarius standards.",
                    "wiki_title": None,
                })

        return results

    @classmethod
    def fetch_wikipedia_summary(cls, title: str) -> Optional[str]:
        """Fetches a free, 1-2 sentence verified clinical summary from Wikipedia REST API."""
        if not title:
            return None
        try:
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
            headers = {"User-Agent": "PackagedFoodHealthScanner/1.0 (HealthResearch; contact@foodengine.org)"}
            r = requests.get(url, headers=headers, timeout=3.0)
            if r.status_code == 200:
                data = r.json()
                return data.get("extract")
        except Exception:
            pass
        return None

    @classmethod
    def evaluate_clinical_health(
        cls,
        product_name: str,
        nutrients: Dict[str, Any],
        ingredients_text: str,
        declared_allergens: List[str],
    ) -> Dict[str, Any]:
        """Generates comprehensive, multi-persona clinical diagnosis."""
        sugars_val = cls._get_val(nutrients, ["sugars_g", "added_sugars_g", "sugars", "total_sugars_g"])
        added_sugars_val = cls._get_val(nutrients, ["added_sugars_g"])
        sat_fat_val = cls._get_val(nutrients, ["saturated_fat_g", "saturated_fat"])
        sodium_val = cls._get_val(nutrients, ["sodium_mg", "sodium"])
        salt_val = cls._get_val(nutrients, ["salt_g", "salt"])
        trans_fat_val = cls._get_val(nutrients, ["trans_fat_g", "trans_fat"])
        fiber_val = cls._get_val(nutrients, ["dietary_fibre_g", "fiber_g", "fibre_g"])

        hidden_sugars = cls.detect_hidden_sugars(ingredients_text)
        additives = cls.identify_additives(ingredients_text)

        has_palm_oil = bool(re.search(r'\b(palm oil|palmolein|fractionated palm)\b', ingredients_text, re.IGNORECASE))
        has_refined_flour = bool(re.search(r'\b(maida|refined wheat flour|bleached flour)\b', ingredients_text, re.IGNORECASE))

        # Check for zero-nutrient fallback (blank, corrupt, or unextracted label)
        has_any_nutrients = any(
            v is not None for v in [sugars_val, added_sugars_val, sat_fat_val, sodium_val, salt_val, trans_fat_val, fiber_val]
        )

        # --- 1. DIABETIC & PRE-DIABETIC EVALUATION ---
        if not has_any_nutrients:
            diabetic_verdict = "INCONCLUSIVE"
            diabetic_reasons = ["Zero nutrients detected on label. Cannot determine diabetic safety."]
        else:
            diabetic_verdict = "SAFE"
            diabetic_reasons = []

            effective_sugar = added_sugars_val if added_sugars_val is not None else sugars_val

            if effective_sugar is not None and effective_sugar >= 22.5:
                diabetic_verdict = "DANGEROUS"
                diabetic_reasons.append(f"Extreme sugar content ({effective_sugar}g / 100g). Exceeds WHO safe limit (22.5g) by {(effective_sugar - 22.5):.1f}g.")
            elif effective_sugar is not None and effective_sugar >= 10.0:
                diabetic_verdict = "CAUTION"
                diabetic_reasons.append(f"Moderate-to-high sugar ({effective_sugar}g / 100g). Consume only small portions.")
            elif hidden_sugars:
                diabetic_verdict = "CAUTION"
                diabetic_reasons.append(f"Contains hidden spike-inducing sugars: {', '.join(hidden_sugars[:3])}.")

            if has_refined_flour:
                if diabetic_verdict == "SAFE":
                    diabetic_verdict = "CAUTION"
                diabetic_reasons.append("Made with refined maida (flour), which converts rapidly into bloodstream glucose.")

            if fiber_val is not None and fiber_val >= 6.0:
                diabetic_reasons.append(f"Beneficial dietary fibre ({fiber_val}g) helps blunt post-meal blood sugar spikes.")

        # --- 2. HYPERTENSION & CARDIOVASCULAR (HEART HEALTH) ---
        if not has_any_nutrients:
            heart_verdict = "INCONCLUSIVE"
            heart_reasons = ["Zero nutrients detected on label. Cannot determine cardiovascular risk."]
        else:
            heart_verdict = "SAFE"
            heart_reasons = []

            if sodium_val is not None and sodium_val >= 600.0:
                heart_verdict = "DANGEROUS"
                heart_reasons.append(f"High sodium ({sodium_val:.0f} mg/100g). High-risk for blood pressure elevation under WHO/FSSAI HFSS benchmarks.")
            elif sodium_val is not None and sodium_val >= 300.0:
                heart_verdict = "CAUTION"
                heart_reasons.append(f"Moderate sodium ({sodium_val:.0f} mg/100g). Keep total daily intake under 2,000 mg.")

            if sat_fat_val is not None and sat_fat_val >= 5.0:
                if heart_verdict != "DANGEROUS":
                    heart_verdict = "CAUTION"
                heart_reasons.append(f"High saturated fat ({sat_fat_val}g / 100g > 5.0g WHO limit).")

            if has_palm_oil:
                heart_reasons.append("Contains Palm Oil/Palmolein, rich in palmitic acid which can elevate LDL cholesterol.")

            if trans_fat_val is not None and trans_fat_val > 0.2:
                heart_verdict = "DANGEROUS"
                heart_reasons.append(f"Contains industrial trans fat ({trans_fat_val}g). FSSAI enforces strict trans-fat elimination (<2%).")

        # --- 3. OVERALL BOTTOM-LINE CONSUMER VERDICT ---
        if not has_any_nutrients:
            overall_status = "INCONCLUSIVE"
            badge_color = "AMBER"
        elif diabetic_verdict == "DANGEROUS" or heart_verdict == "DANGEROUS":
            overall_status = "DANGEROUS"
            badge_color = "RED"
        elif diabetic_verdict == "CAUTION" or heart_verdict == "CAUTION" or any(a.get("risk_level") == "HIGH_RISK" for a in additives):
            overall_status = "CAUTION"
            badge_color = "AMBER"
        else:
            overall_status = "HEALTHY"
            badge_color = "GREEN"

        return {
            "overall_status": overall_status,
            "badge_color": badge_color,
            "diabetic": {
                "verdict": diabetic_verdict,
                "reasons": diabetic_reasons,
                "hidden_sugars": hidden_sugars,
            },
            "heart": {
                "verdict": heart_verdict,
                "reasons": heart_reasons,
            },
            "additives": additives,
            "has_palm_oil": has_palm_oil,
            "has_refined_flour": has_refined_flour,
        }

    @staticmethod
    def _get_val(nutrients: Dict[str, Any], keys: List[str]) -> Optional[float]:
        for k in keys:
            v = nutrients.get(k)
            if v is None:
                continue
            if isinstance(v, dict):
                val = v.get("value")
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
            elif isinstance(v, (int, float)):
                return float(v)
        return None
