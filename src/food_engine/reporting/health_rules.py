"""Stage 8: Evidence-Based Nutritional and Allergen Health Rules.

Applies deterministic threshold evaluations grounded in official dietary guidelines:
- WHO (World Health Organization) Guideline: Sugars intake for adults and children
- WHO Sodium intake guidelines for adults and children
- FSSAI (Food Safety and Standards Authority of India) Labelling and Display Regulations
- US FDA Guidance for Industry: Nutrition and Nutrient Content Claims

Enforces:
- Strictly no diagnostic claims or hallucinated health outcomes.
- Measures and thresholds are cited with authoritative public sources.
- Measured nutrient data is kept strictly distinct from dietary interpretation.
"""

from typing import Any, Dict, List


class EvidenceBasedHealthRules:
    """Evaluates nutritional content and allergens against authoritative dietary benchmarks."""

    # Official Dietary Thresholds (per 100g for solid food items)
    # Source: UK Department of Health / WHO European Region / FSSAI High in Fat, Sugar, Salt (HFSS) benchmarks
    THRESHOLDS = {
        "high_sodium_mg_per_100g": 600.0,       # Equivalent to 1.5g salt per 100g
        "high_sugar_g_per_100g": 22.5,          # >22.5g total sugars per 100g
        "high_saturated_fat_g_per_100g": 5.0,    # >5.0g saturated fat per 100g
        "trans_fat_warning_g_per_100g": 0.2,     # FSSAI threshold: industrial trans fatty acids limitation
    }

    @classmethod
    def evaluate(
        cls,
        nutrients: Dict[str, Dict[str, Any]],
        declared_allergens: List[str],
        potential_traces: List[str],
        basis: str = "per_100_g",
    ) -> List[Dict[str, Any]]:
        """Evaluates extracted nutrient facts and allergens, generating structured alerts."""
        alerts: List[Dict[str, Any]] = []

        # 1. Allergen Alerts
        for allergen in declared_allergens:
            alerts.append({
                "category": "allergen",
                "severity": "critical",
                "title": f"Declared Allergen: {allergen}",
                "reason": f"Packaging label explicitly declares presence of {allergen}.",
                "authority_source": "FSSAI (Labelling & Display Regulations 2020) & US FDA Allergen Labeling (FALCPA)",
                "threshold_reference": "Zero-tolerance declaration for major food allergens.",
            })

        for trace in potential_traces:
            alerts.append({
                "category": "allergen",
                "severity": "warning",
                "title": f"Potential Allergen Trace: {trace}",
                "reason": f"Packaging indicates cross-contact risk or trace presence: {trace}.",
                "authority_source": "FSSAI Allergen Advisory Guidelines",
                "threshold_reference": "Precautionary allergen cross-contact declaration.",
            })

        # 2. Nutrient Thresholds (applicable when basis is per 100g)
        if basis == "per_100_g":
            # High Sodium Check
            sod_info = nutrients.get("sodium_mg", {})
            sod_val = sod_info.get("value")
            if sod_val is not None and sod_val >= cls.THRESHOLDS["high_sodium_mg_per_100g"]:
                salt_equiv = round((sod_val / 1000.0) * 2.5, 2)
                alerts.append({
                    "category": "high_nutrient",
                    "severity": "warning",
                    "title": "High Sodium Content",
                    "reason": f"Sodium content is {sod_val} mg/100g (approx {salt_equiv} g salt/100g), exceeding benchmark.",
                    "authority_source": "WHO Guideline: Sodium intake for adults and children (2012) & FSSAI HFSS Guidelines",
                    "threshold_reference": "High threshold defined as >600 mg sodium (1.5g salt) per 100g.",
                })

            # High Sugar Check
            sugar_info = nutrients.get("sugars_g", {})
            sugar_val = sugar_info.get("value")
            if sugar_val is not None and sugar_val >= cls.THRESHOLDS["high_sugar_g_per_100g"]:
                alerts.append({
                    "category": "high_nutrient",
                    "severity": "warning",
                    "title": "High Sugar Content",
                    "reason": f"Sugar content is {sugar_val} g/100g, exceeding high-sugar benchmark.",
                    "authority_source": "WHO Guideline: Sugars intake for adults and children (2015)",
                    "threshold_reference": "High threshold defined as >22.5g total sugars per 100g for solid food.",
                })

            # High Saturated Fat Check
            sat_info = nutrients.get("saturated_fat_g", {})
            sat_val = sat_info.get("value")
            if sat_val is not None and sat_val >= cls.THRESHOLDS["high_saturated_fat_g_per_100g"]:
                alerts.append({
                    "category": "high_nutrient",
                    "severity": "warning",
                    "title": "High Saturated Fat Content",
                    "reason": f"Saturated fat content is {sat_val} g/100g, exceeding threshold.",
                    "authority_source": "WHO / FAO Dietary recommendations on fatty acids (2010)",
                    "threshold_reference": "High threshold defined as >5g saturated fat per 100g for solid food.",
                })

            # Trans Fat Check
            trans_info = nutrients.get("trans_fat_g", {})
            trans_val = trans_info.get("value")
            if trans_val is not None and trans_val >= cls.THRESHOLDS["trans_fat_warning_g_per_100g"]:
                alerts.append({
                    "category": "high_nutrient",
                    "severity": "warning",
                    "title": "Declared Trans Fatty Acids",
                    "reason": f"Product declares {trans_val} g/100g trans fatty acids.",
                    "authority_source": "FSSAI Food Safety and Standards (Prohibition and Restrictions on Sales) Second Amendment Regulations 2021",
                    "threshold_reference": "Limit of industrial trans fat to not more than 2% by weight.",
                })

        return alerts
