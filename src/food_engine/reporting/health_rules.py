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

from typing import Any, Dict, List, Optional, Tuple


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

    # Minimum mandatory core nutrients required for compliance determination
    # (Energy/Calories, Added Sugars/Sugars, Saturated Fat/Total Fat, Sodium/Salt)
    CORE_NUTRIENT_REQUIREMENTS = ("energy", "sugars", "saturated_fat", "sodium_salt")

    @classmethod
    def check_data_sufficiency(
        cls,
        nutrients: Dict[str, Any],
        ocr_lines_detected: Optional[int] = None,
    ) -> Tuple[bool, str, List[str]]:
        """Validates that minimum mandatory core nutrients are present and not missing/None.

        Minimum required core nutrients for evaluation:
        - Energy/Calories (energy_kcal, energy_kj, energy, calories)
        - Sugars (sugars, added_sugars, sugars_g, added_sugars_g, total_sugars_g, sugar)
        - Saturated Fat (saturated_fat, saturated_fat_g, total_fat, total_fat_g, fat_g, fat)
        - Sodium/Salt (sodium, salt, sodium_mg, salt_g)

        Returns:
            Tuple of (is_sufficient, reason_message, missing_core_nutrients)
        """
        if ocr_lines_detected is not None and ocr_lines_detected == 0:
            return False, "0 OCR lines detected from package label.", ["energy", "sugars", "saturated_fat", "sodium"]

        if not nutrients:
            return False, "No nutrient data present.", ["energy", "sugars", "saturated_fat", "sodium"]

        def _is_valid_evaluated(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, dict):
                st = str(v.get("status", "")).upper()
                if st in ("MISSING", "UNCLEAR", "NONE", "NOT_DECLARED", "UNAVAILABLE"):
                    return False
                return v.get("value") is not None
            if hasattr(v, "status"):
                st = str(getattr(v, "status", "")).upper()
                if st in ("MISSING", "UNCLEAR", "NONE", "NOT_DECLARED", "UNAVAILABLE"):
                    return False
                return getattr(v, "value", None) is not None
            if isinstance(v, (int, float)):
                return True
            return False

        def _get_val(keys: List[str]):
            for k in keys:
                if k in nutrients and nutrients[k] is not None:
                    return nutrients[k]
            return None

        sugar_val = _get_val(["sugars", "added_sugars", "sugars_g", "added_sugars_g", "total_sugars_g", "sugar"])
        sat_fat_val = _get_val(["saturated_fat", "saturated_fat_g", "total_fat", "total_fat_g", "fat_g", "fat"])
        sodium_val = _get_val(["sodium", "salt", "sodium_mg", "salt_g"])
        energy_val = _get_val(["energy", "calories", "energy_kcal", "energy_kj"])

        evaluated_values = [
            v for v in [sugar_val, sat_fat_val, sodium_val, energy_val]
            if _is_valid_evaluated(v)
        ]

        missing_core: List[str] = []
        if not _is_valid_evaluated(energy_val):
            missing_core.append("energy")
        if not _is_valid_evaluated(sugar_val):
            missing_core.append("sugars")
        if not _is_valid_evaluated(sat_fat_val):
            missing_core.append("saturated_fat")
        if not _is_valid_evaluated(sodium_val):
            missing_core.append("sodium")

        if len(evaluated_values) < 2 or missing_core:
            return False, f"Missing required core nutrients: {', '.join(missing_core)}", missing_core

        return True, "Core nutrients sufficient for dietary compliance evaluation.", []

    @classmethod
    def evaluate(
        cls,
        nutrients: Dict[str, Dict[str, Any]],
        declared_allergens: List[str],
        potential_traces: List[str],
        basis: str = "per_100_g",
        ocr_lines_detected: Optional[int] = None,
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

    @classmethod
    def evaluate_compliance(
        cls,
        nutrients: Dict[str, Dict[str, Any]],
        declared_allergens: List[str],
        potential_traces: List[str],
        basis: str = "per_100_g",
        ocr_lines_detected: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Evaluates dietary compliance, strictly enforcing data sufficiency validation.

        1. Identify presence of core macronutrients:
           - Sugars (sugars or added_sugars)
           - Saturated Fat (saturated_fat)
           - Sodium (sodium or salt)
           - Energy (energy or calories)
        2. Guard: If core nutrients are completely missing or unextracted (less than 2 present)
           or 0 OCR lines detected, returns status='INCONCLUSIVE', badge='AMBER'.
        3. Normal threshold evaluations for sugar, sat_fat, sodium, trans_fat.
        4. Only if core nutrients WERE present and NO flags were triggered:
           returns status='COMPLIANT', badge='GREEN'.
        """
        def _get_val(keys: List[str]):
            for k in keys:
                if k in nutrients and nutrients[k] is not None:
                    return nutrients[k]
            return None

        def _is_valid_evaluated(v: Any) -> bool:
            if v is None:
                return False
            if isinstance(v, dict):
                st = str(v.get("status", "")).upper()
                if st in ("MISSING", "UNCLEAR", "NONE", "NOT_DECLARED", "UNAVAILABLE"):
                    return False
                return v.get("value") is not None
            if hasattr(v, "status"):
                st = str(getattr(v, "status", "")).upper()
                if st in ("MISSING", "UNCLEAR", "NONE", "NOT_DECLARED", "UNAVAILABLE"):
                    return False
                return getattr(v, "value", None) is not None
            if isinstance(v, (int, float)):
                return True
            return False

        # 1. Identify presence of core macronutrients
        sugar_val = _get_val(["sugars", "added_sugars", "sugars_g", "added_sugars_g", "total_sugars_g", "sugar"])
        sat_fat_val = _get_val(["saturated_fat", "saturated_fat_g", "total_fat", "total_fat_g", "fat_g", "fat"])
        sodium_val = _get_val(["sodium", "salt", "sodium_mg", "salt_g"])
        energy_val = _get_val(["energy", "calories", "energy_kcal", "energy_kj"])

        # Check how many core nutrients have valid, non-null, non-missing values
        evaluated_values = [
            v for v in [sugar_val, sat_fat_val, sodium_val, energy_val]
            if _is_valid_evaluated(v)
        ]

        missing_core: List[str] = []
        if not _is_valid_evaluated(energy_val):
            missing_core.append("energy")
        if not _is_valid_evaluated(sugar_val):
            missing_core.append("sugars")
        if not _is_valid_evaluated(sat_fat_val):
            missing_core.append("saturated_fat")
        if not _is_valid_evaluated(sodium_val):
            missing_core.append("sodium")

        # 2. Guard: If core nutrients are completely missing or unextracted (less than 2 present) or 0 OCR lines
        if (ocr_lines_detected is not None and ocr_lines_detected == 0) or len(evaluated_values) < 2 or missing_core:
            sufficiency_alert = {
                "category": "data_ambiguity",
                "severity": "warning",
                "badge": "AMBER",
                "title": "Inconclusive / Insufficient Data",
                "reason": "Key macronutrients (Sugars, Saturated Fat, Sodium) were not detected on the label. Compliance with FSSAI/WHO standards cannot be verified.",
                "authority_source": "FSSAI & WHO Dietary Standards Guidelines",
                "threshold_reference": "Mandatory core nutrients (Energy, Sugars, Saturated Fat, Sodium/Salt) required for compliance determination.",
            }
            return {
                "status": "INCONCLUSIVE",
                "badge": "AMBER",
                "title": "⚠️ Inconclusive / Insufficient Nutritional Data",
                "message": "Key macronutrients (Sugars, Saturated Fat, Sodium) were not detected on the label. Compliance with FSSAI/WHO standards cannot be verified.",
                "details": "Key macronutrients (Sugars, Saturated Fat, or Sodium) could not be extracted from the label. Cannot verify FSSAI or WHO dietary compliance.",
                "diagnosis_message": "⚠️ Inconclusive / Insufficient Data: Key macronutrients (Sugars, Saturated Fat, Sodium) were not detected on the label. Compliance with FSSAI/WHO standards cannot be verified.",
                "is_sufficient": False,
                "missing_core_nutrients": missing_core,
                "flags": [],
                "alerts": [sufficiency_alert],
            }

        # 3. Normal threshold evaluations
        alerts = cls.evaluate(
            nutrients=nutrients,
            declared_allergens=declared_allergens,
            potential_traces=potential_traces,
            basis=basis,
            ocr_lines_detected=ocr_lines_detected,
        )
        flags = [a for a in alerts if a.get("category") == "high_nutrient"]

        if len(flags) > 0:
            return {
                "status": "NON_COMPLIANT",
                "badge": "RED",
                "title": "🚨 FSSAI & WHO Threshold Alert",
                "message": "High levels of sugar, sodium, or saturated/trans fats detected.",
                "diagnosis_message": "🚨 FSSAI & WHO Threshold Alert: High levels of sugar, sodium, or saturated/trans fats detected.",
                "is_sufficient": True,
                "missing_core_nutrients": [],
                "flags": flags,
                "alerts": alerts,
            }

        # 4. Only if core nutrients WERE present and NO flags were triggered:
        return {
            "status": "COMPLIANT",
            "badge": "GREEN",
            "title": "✅ FSSAI & WHO Dietary Compliant",
            "message": "No excessive sugar, sodium, saturated fat, or industrial trans fat detected among evaluated nutrients.",
            "diagnosis_message": "✅ FSSAI & WHO Dietary Compliant: No excessive sugar, sodium, saturated fat, or industrial trans fat detected.",
            "is_sufficient": True,
            "missing_core_nutrients": [],
            "flags": [],
            "alerts": alerts,
        }
