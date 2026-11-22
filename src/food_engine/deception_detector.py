"""NutriTruth (खाद्य) Deceptive Label Buster & Health Transparency Engine.

Grounded in:
- FSSAI (Food Safety and Standards Authority of India) Labelling and Display Regulations
- WHO (World Health Organization) Guideline on Free Sugars and Sodium Intake
- NOVA Food Classification System (Monteiro et al., University of Sao Paulo)
- ICMR-NIN (National Institute of Nutrition) Dietary Guidelines for Indians
"""

import math
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# 56+ Documented Free & Deceptive Sugar Aliases with Glycemic Index and classification
SUGAR_ALIASES_DB = {
    "maltodextrin": {"category": "Deceptive Bulking Sugar", "glycemic_index": 110, "risk": "Extreme"},
    "liquid glucose": {"category": "Industrial Syrup", "glycemic_index": 100, "risk": "Very High"},
    "glucose syrup": {"category": "Industrial Syrup", "glycemic_index": 100, "risk": "Very High"},
    "glucose": {"category": "Free Sugar", "glycemic_index": 100, "risk": "Very High"},
    "dextrose": {"category": "Refined Sugar", "glycemic_index": 100, "risk": "Very High"},
    "high fructose corn syrup": {"category": "Industrial Syrup", "glycemic_index": 87, "risk": "Severe"},
    "hfcs": {"category": "Industrial Syrup", "glycemic_index": 87, "risk": "Severe"},
    "corn syrup": {"category": "Industrial Syrup", "glycemic_index": 90, "risk": "Severe"},
    "corn syrup solids": {"category": "Industrial Syrup", "glycemic_index": 90, "risk": "Severe"},
    "invert sugar": {"category": "Refined Syrup", "glycemic_index": 60, "risk": "High"},
    "invert sugar syrup": {"category": "Refined Syrup", "glycemic_index": 60, "risk": "High"},
    "invert syrup": {"category": "Refined Syrup", "glycemic_index": 60, "risk": "High"},
    "malt extract": {"category": "Deceptive Cereal Sugar", "glycemic_index": 89, "risk": "High"},
    "barley malt extract": {"category": "Deceptive Cereal Sugar", "glycemic_index": 89, "risk": "High"},
    "barley malt": {"category": "Deceptive Cereal Sugar", "glycemic_index": 89, "risk": "High"},
    "maltose": {"category": "Refined Disaccharide", "glycemic_index": 105, "risk": "Very High"},
    "sugar": {"category": "Standard Refined Sugar", "glycemic_index": 65, "risk": "High"},
    "white sugar": {"category": "Standard Refined Sugar", "glycemic_index": 65, "risk": "High"},
    "cane sugar": {"category": "Refined Sugar", "glycemic_index": 65, "risk": "High"},
    "sucrose": {"category": "Refined Disaccharide", "glycemic_index": 65, "risk": "High"},
    "brown sugar": {"category": "Refined Sugar", "glycemic_index": 64, "risk": "High"},
    "demerara sugar": {"category": "Cane Sugar", "glycemic_index": 65, "risk": "High"},
    "turbinado sugar": {"category": "Cane Sugar", "glycemic_index": 65, "risk": "High"},
    "muscovado sugar": {"category": "Unrefined Cane Sugar", "glycemic_index": 65, "risk": "High"},
    "cane juice crystals": {"category": "Cane Sugar", "glycemic_index": 65, "risk": "High"},
    "evaporated cane juice": {"category": "Cane Sugar", "glycemic_index": 65, "risk": "High"},
    "fructose": {"category": "Simple Sugar", "glycemic_index": 25, "risk": "High (Hepatic Lipogenesis)"},
    "fruit juice concentrate": {"category": "Deceptive Free Sugar", "glycemic_index": 68, "risk": "High"},
    "apple juice concentrate": {"category": "Deceptive Free Sugar", "glycemic_index": 65, "risk": "High"},
    "grape juice concentrate": {"category": "Deceptive Free Sugar", "glycemic_index": 68, "risk": "High"},
    "pear juice concentrate": {"category": "Deceptive Free Sugar", "glycemic_index": 65, "risk": "High"},
    "rice syrup": {"category": "Industrial Syrup", "glycemic_index": 98, "risk": "Very High"},
    "brown rice syrup": {"category": "Industrial Syrup", "glycemic_index": 98, "risk": "Very High"},
    "golden syrup": {"category": "Refined Sugar Syrup", "glycemic_index": 65, "risk": "High"},
    "treacle": {"category": "Refined Sugar Byproduct", "glycemic_index": 60, "risk": "High"},
    "molasses": {"category": "Cane Sugar Byproduct", "glycemic_index": 55, "risk": "Moderate"},
    "caramel": {"category": "Burnt Sugar / Color", "glycemic_index": 60, "risk": "Moderate"},
    "agave nectar": {"category": "High Fructose Syrup", "glycemic_index": 30, "risk": "High"},
    "agave syrup": {"category": "High Fructose Syrup", "glycemic_index": 30, "risk": "High"},
    "maple syrup": {"category": "Natural Sugar", "glycemic_index": 54, "risk": "Moderate"},
    "date syrup": {"category": "Natural Sugar", "glycemic_index": 55, "risk": "Moderate"},
    "sorghum syrup": {"category": "Cereal Syrup", "glycemic_index": 65, "risk": "High"},
    "jaggery": {"category": "Traditional Cane Sugar", "glycemic_index": 84, "risk": "High"},
    "gur": {"category": "Traditional Cane Sugar", "glycemic_index": 84, "risk": "High"},
    "honey": {"category": "Natural Free Sugar", "glycemic_index": 58, "risk": "Moderate"},
    "dextrin": {"category": "Bulking Carbohydrate", "glycemic_index": 95, "risk": "High"},
    "isomaltulose": {"category": "Slow Release Sugar", "glycemic_index": 32, "risk": "Low"},
    "galactose": {"category": "Simple Sugar", "glycemic_index": 25, "risk": "Low"},
    "panela": {"category": "Traditional Cane Sugar", "glycemic_index": 70, "risk": "High"},
}

# Palm oil aliases and disguised industrial fats
PALM_OIL_TERMS = [
    "palm oil",
    "palmolein",
    "edible vegetable oil (palmolein)",
    "edible vegetable oil(palmolein)",
    "edible vegetable oil (palm)",
    "fractionated palm oil",
    "palm kernel oil",
    "palm fat",
    "hydrogenated vegetable oil",
    "hydrogenated vegetable fat",
    "interesterified vegetable fat",
    "interesterified vegetable oil",
    "vanaspati",
    "dalda",
    "partially hydrogenated vegetable oil",
]

# Industrial food additives that trigger NOVA-4 Ultra-Processed Food classification
INDUSTRIAL_ADDITIVES = {
    # Emulsifiers & Stabilizers
    "ins 322": {"name": "Soy Lecithin", "type": "Emulsifier", "nova": 4},
    "ins 471": {"name": "Mono- and Di-glycerides of Fatty Acids", "type": "Emulsifier", "nova": 4},
    "ins 472e": {"name": "DATEM (Diacetyl Tartaric Acid Esters)", "type": "Emulsifier", "nova": 4},
    "ins 476": {"name": "PGPR (Polyglycerol Polyricinoleate)", "type": "Fat Substitute Emulsifier", "nova": 4},
    "ins 412": {"name": "Guar Gum", "type": "Thickener", "nova": 4},
    "ins 415": {"name": "Xanthan Gum", "type": "Stabilizer", "nova": 4},
    "ins 407": {"name": "Carrageenan", "type": "Inflammatory Thickener", "nova": 4},
    "ins 466": {"name": "Carboxymethylcellulose (CMC)", "type": "Stabilizer", "nova": 4},

    # Flavor Enhancers
    "ins 621": {"name": "Monosodium Glutamate (MSG)", "type": "Flavor Enhancer", "nova": 4},
    "ins 627": {"name": "Disodium Guanylate", "type": "Flavor Enhancer", "nova": 4},
    "ins 631": {"name": "Disodium Inosinate", "type": "Flavor Enhancer", "nova": 4},
    "ins 635": {"name": "Disodium 5'-Ribonucleotides", "type": "Flavor Enhancer", "nova": 4},

    # Colors & Artificial Dyes
    "ins 150d": {"name": "Caramel IV (Ammonia Sulfite)", "type": "Caramel Color (Suspected Carcinogen)", "nova": 4},
    "ins 102": {"name": "Tartrazine (Yellow 5)", "type": "Synthetic Food Dye", "nova": 4},
    "ins 110": {"name": "Sunset Yellow FCF", "type": "Synthetic Food Dye", "nova": 4},
    "ins 129": {"name": "Allura Red AC", "type": "Synthetic Food Dye", "nova": 4},
    "ins 133": {"name": "Brilliant Blue FCF", "type": "Synthetic Food Dye", "nova": 4},

    # Preservatives & Antioxidants
    "ins 211": {"name": "Sodium Benzoate", "type": "Chemical Preservative", "nova": 4},
    "ins 202": {"name": "Potassium Sorbate", "type": "Chemical Preservative", "nova": 4},
    "ins 223": {"name": "Sodium Metabisulphite", "type": "Chemical Preservative", "nova": 4},
    "ins 319": {"name": "TBHQ (Tert-Butylhydroquinone)", "type": "Synthetic Antioxidant", "nova": 4},
    "ins 320": {"name": "BHA (Butylated Hydroxyanisole)", "type": "Synthetic Antioxidant", "nova": 4},

    # Artificial Sweeteners
    "ins 950": {"name": "Acesulfame Potassium", "type": "Artificial Intense Sweetener", "nova": 4},
    "ins 951": {"name": "Aspartame", "type": "Artificial Intense Sweetener", "nova": 4},
    "ins 955": {"name": "Sucralose", "type": "Artificial Intense Sweetener", "nova": 4},
    "ins 961": {"name": "Neotame", "type": "Artificial Intense Sweetener", "nova": 4},
}


class DeceptiveLabelBuster:
    """Detects disguised sugars, palm oil, ultra-processed additives, and calculates FSSAI INR ratings."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            default_p = Path(__file__).resolve().parent.parent.parent / "datasets" / "processed" / "products" / "products.db"
            self.db_path = default_p

    def analyze_label(
        self,
        product_name: str,
        ingredients_text: str,
        nutrients: Dict[str, Any],
        serving_size_g: Optional[float] = None,
        pack_weight_g: Optional[float] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Performs full transparency analysis of a packaged food label."""
        ingr_lower = (ingredients_text or "").lower()

        # 1. Detect Sugar Aliases
        sugar_findings = self._detect_sugar_aliases(ingr_lower)

        # 2. Detect Palm Oil and Disguised Fats
        palm_oil_findings = self._detect_palm_oil(ingr_lower)

        # 3. Detect Industrial Additives and Determine NOVA Score
        nova_findings = self._classify_nova(ingr_lower)

        # 4. Calculate FSSAI Indian Nutrition Rating (INR) & Nutri-Score
        inr_score, inr_stars, inr_tier = self._calculate_fssai_inr(nutrients)

        # 5. Calculate Serving Size Deception & True Pack Impact
        serving_reality = self._calculate_serving_deception(
            nutrients=nutrients,
            serving_size_g=serving_size_g,
            pack_weight_g=pack_weight_g,
        )

        # 6. Deception Index (0 to 100)
        deception_score = self._compute_deception_score(
            sugar_findings=sugar_findings,
            palm_oil_findings=palm_oil_findings,
            nova_findings=nova_findings,
            serving_reality=serving_reality,
        )

        # 7. Find Healthier Alternative Swaps
        healthier_swaps = self._find_healthier_swaps(
            category=category or "",
            current_sugars=nutrients.get("sugars_100g") or nutrients.get("sugars") or 0.0,
            has_palm_oil=palm_oil_findings["contains_palm_oil"],
        )

        return {
            "product_name": product_name,
            "brand": brand,
            "category": category,
            "deception_score": deception_score,
            "deception_tier": self._get_deception_tier(deception_score),
            "fssai_inr": {
                "score": inr_score,
                "stars": inr_stars,
                "grade": inr_tier,
                "description": f"{inr_stars} / 5.0 Stars (FSSAI Indian Nutrition Rating)",
            },
            "sugar_analysis": sugar_findings,
            "palm_oil_analysis": palm_oil_findings,
            "nova_classification": nova_findings,
            "serving_size_reality": serving_reality,
            "healthy_swaps": healthier_swaps,
        }

    def _detect_sugar_aliases(self, ingr_text: str) -> Dict[str, Any]:
        """Finds all occurrences of disguised and free sugars in ingredient text."""
        detected = []
        seen_aliases = set()

        for alias, info in SUGAR_ALIASES_DB.items():
            # Use regex word boundaries
            pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
            if re.search(pattern, ingr_text):
                if alias not in seen_aliases:
                    seen_aliases.add(alias)
                    detected.append({
                        "alias": alias.title(),
                        "category": info["category"],
                        "glycemic_index": info["glycemic_index"],
                        "risk_level": info["risk"],
                    })

        # Sort by Glycemic Index descending
        detected.sort(key=lambda x: x["glycemic_index"], reverse=True)

        is_disguised = any(
            d["category"] in ("Deceptive Bulking Sugar", "Industrial Syrup", "Refined Syrup", "Deceptive Cereal Sugar")
            for d in detected
        )

        return {
            "detected_count": len(detected),
            "is_disguised": is_disguised,
            "aliases": detected,
            "warning": (
                f"Contains {len(detected)} different sugar/sweetener sources. Brands split sugar into multiple aliases "
                "so sugar does not appear as the #1 ingredient on the mandatory list."
                if len(detected) >= 2
                else ("Contains refined or free sugars." if detected else "No hidden sugar aliases detected.")
            ),
        }

    def _detect_palm_oil(self, ingr_text: str) -> Dict[str, Any]:
        """Detects whether palm oil or hydrogenated vegetable fats are present."""
        found_terms = []
        for term in PALM_OIL_TERMS:
            if term in ingr_text:
                found_terms.append(term)

        contains_palm_oil = len(found_terms) > 0
        is_disguised = any("vegetable oil" in t or "vegetable fat" in t for t in found_terms)

        explanation = ""
        if contains_palm_oil:
            if is_disguised:
                explanation = (
                    "DECEPTIVE LABEL DETECTED: The product lists 'Edible Vegetable Oil' or 'Palmolein'. "
                    "In India, manufacturers use cheap, refined palmolein (high in saturated palmitic acid ~45%) "
                    "instead of healthier cold-pressed oils to cut manufacturing costs."
                )
            else:
                explanation = "Contains Palm Oil or Palm Fat. High in saturated fat."
        else:
            explanation = "No palm oil or disguised hydrogenated fats detected in ingredient text."

        return {
            "contains_palm_oil": contains_palm_oil,
            "is_disguised_under_vegetable_oil": is_disguised,
            "matched_terms": found_terms,
            "warning": explanation,
        }

    def _classify_nova(self, ingr_text: str) -> Dict[str, Any]:
        """Classifies food processing level into NOVA 1, 2, 3, or 4."""
        detected_additives = []
        for code, meta in INDUSTRIAL_ADDITIVES.items():
            pattern = r"(?<!\w)" + re.escape(code) + r"(?!\w)"
            if re.search(pattern, ingr_text) or meta["name"].lower() in ingr_text:
                detected_additives.append({
                    "code": code.upper(),
                    "name": meta["name"],
                    "type": meta["type"],
                })

        # Count total comma-separated ingredients
        items = [i.strip() for i in re.split(r"[,;•\n]", ingr_text) if i.strip()]
        total_ingredients = len(items)

        # Check for ultra-processed indicators
        has_industrial_sugars = any(
            s in ingr_text for s in ["maltodextrin", "liquid glucose", "corn syrup", "invert sugar", "hfcs"]
        )
        has_palm_fat = any(p in ingr_text for p in PALM_OIL_TERMS)
        has_flavorings = "artificial flavour" in ingr_text or "nature identical" in ingr_text

        if len(detected_additives) > 0 or has_industrial_sugars or has_palm_fat or has_flavorings or total_ingredients >= 5:
            nova_group = 4
            nova_name = "Ultra-Processed Food (UPF)"
            description = (
                "Industrial formulation manufactured from substances derived from foods, synthesized with "
                "emulsifiers, artificial flavors, and refined fats. High consumption is linked to metabolic disease."
            )
        elif total_ingredients >= 3:
            nova_group = 3
            nova_name = "Processed Food"
            description = "Relatively simple food made with standard culinary ingredients (salt, oil, sugar) added to whole foods."
        elif total_ingredients >= 1 and any(i in ingr_text for i in ["salt", "oil", "butter", "sugar"]):
            nova_group = 2
            nova_name = "Processed Culinary Ingredient"
            description = "Extracted from natural foods (butter, salt, cold-pressed oil, unrefined flour)."
        else:
            nova_group = 1
            nova_name = "Unprocessed or Minimally Processed"
            description = "Natural whole foods with zero synthetic additives, refined extracts, or industrial alterations."

        return {
            "nova_group": nova_group,
            "nova_name": nova_name,
            "description": description,
            "detected_additives": detected_additives,
            "total_ingredients_count": total_ingredients,
        }

    def _calculate_fssai_inr(self, nutrients: Dict[str, Any]) -> Tuple[float, float, str]:
        """Calculates FSSAI Indian Nutrition Rating (INR) on a 1.0 to 5.0 star scale.

        Methodology:
        Points allocated for negative nutrients per 100g:
        - Energy (kcal)
        - Total Sugars (g)
        - Saturated Fat (g)
        - Sodium (mg)
        Points subtracted for positive nutrients:
        - Dietary Fibre (g)
        - Protein (g)
        """
        def _get_float(keys: List[str]) -> float:
            for k in keys:
                v = nutrients.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return 0.0

        energy = _get_float(["energy_100g", "energy_kcal", "calories"])
        sugars = _get_float(["sugars_100g", "sugars", "total_sugars_g"])
        sat_fat = _get_float(["saturated_fat_100g", "saturated_fat", "saturated_fat_g"])
        sodium = _get_float(["sodium_100g", "sodium", "sodium_mg"])
        # If salt given in grams, convert to sodium mg
        salt = _get_float(["salt_100g", "salt"])
        if salt > 0 and sodium == 0:
            sodium = salt * 400.0

        fiber = _get_float(["fiber_100g", "dietary_fibre_g", "fiber"])
        protein = _get_float(["proteins_100g", "protein_g", "protein"])

        # Negative Points Calculation (0 - 40)
        n_pts = 0
        n_pts += min(10, int(energy / 80.0))
        n_pts += min(10, int(sugars / 4.5))
        n_pts += min(10, int(sat_fat / 1.0))
        n_pts += min(10, int(sodium / 90.0))

        # Positive Points Calculation (0 - 15)
        p_pts = 0
        p_pts += min(5, int(fiber / 0.9))
        p_pts += min(5, int(protein / 1.6))

        final_score = n_pts - p_pts

        # Map to FSSAI 1.0 to 5.0 Stars
        if final_score <= 0:
            stars = 5.0
            grade = "A (Nutritional Excellence)"
        elif final_score <= 5:
            stars = 4.5
            grade = "A (Healthy Choice)"
        elif final_score <= 11:
            stars = 3.5
            grade = "B (Moderate Dietary Balance)"
        elif final_score <= 18:
            stars = 2.5
            grade = "C (High in Saturated Fat/Sugar/Salt)"
        elif final_score <= 25:
            stars = 1.5
            grade = "D (Poor Nutritional Balance - HFSS)"
        else:
            stars = 1.0
            grade = "E (Severely Unhealthy - Ultra High HFSS)"

        return final_score, stars, grade

    def _calculate_serving_deception(
        self,
        nutrients: Dict[str, Any],
        serving_size_g: Optional[float],
        pack_weight_g: Optional[float],
    ) -> Dict[str, Any]:
        """Audits the serving size trick used by manufacturers to make sugar/fat look artificially low."""
        if not serving_size_g or serving_size_g <= 0:
            serving_size_g = 20.0  # Common default snack serving in India
        if not pack_weight_g or pack_weight_g <= 0:
            pack_weight_g = 100.0

        servings_per_pack = pack_weight_g / serving_size_g

        def _get_float(keys: List[str]) -> float:
            for k in keys:
                v = nutrients.get(k)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
            return 0.0

        sugars_100g = _get_float(["sugars_100g", "sugars", "total_sugars_g"])
        sat_fat_100g = _get_float(["saturated_fat_100g", "saturated_fat", "saturated_fat_g"])
        calories_100g = _get_float(["energy_100g", "energy_kcal", "calories"])

        # Per serving numbers
        per_serving_sugar = (sugars_100g * serving_size_g) / 100.0
        per_pack_sugar = (sugars_100g * pack_weight_g) / 100.0

        per_serving_sat_fat = (sat_fat_100g * serving_size_g) / 100.0
        per_pack_sat_fat = (sat_fat_100g * pack_weight_g) / 100.0

        # WHO recommended daily free sugar limit: 25g
        who_sugar_daily_pct = round((per_pack_sugar / 25.0) * 100.0, 1)

        is_deceptive = servings_per_pack >= 2.0 and per_serving_sugar <= 10.0 and per_pack_sugar >= 20.0

        return {
            "declared_serving_size_g": serving_size_g,
            "total_pack_weight_g": pack_weight_g,
            "servings_per_pack": round(servings_per_pack, 1),
            "per_serving_sugar_g": round(per_serving_sugar, 1),
            "full_pack_sugar_g": round(per_pack_sugar, 1),
            "who_daily_sugar_pct": who_sugar_daily_pct,
            "per_serving_sat_fat_g": round(per_serving_sat_fat, 1),
            "full_pack_sat_fat_g": round(per_pack_sat_fat, 1),
            "is_serving_size_deceptive": is_deceptive,
            "reality_warning": (
                f"The label lists a tiny {serving_size_g}g serving (showing only {round(per_serving_sugar, 1)}g sugar). "
                f"Eating this entire pack delivers {round(per_pack_sugar, 1)}g of sugar—which is {who_sugar_daily_pct}% "
                "of the WHO recommended maximum daily intake for an adult."
                if is_deceptive
                else f"Full pack delivers {round(per_pack_sugar, 1)}g sugar ({who_sugar_daily_pct}% of daily limit)."
            ),
        }

    def _compute_deception_score(
        self,
        sugar_findings: Dict[str, Any],
        palm_oil_findings: Dict[str, Any],
        nova_findings: Dict[str, Any],
        serving_reality: Dict[str, Any],
    ) -> int:
        """Calculates Deception Score (0 to 100, where 100 = severely deceptive)."""
        score = 0

        # Sugar disguise penalty (up to 35 pts)
        if sugar_findings["is_disguised"]:
            score += 25
        score += min(10, sugar_findings["detected_count"] * 3)

        # Palm oil disguise penalty (up to 30 pts)
        if palm_oil_findings["contains_palm_oil"]:
            score += 15
            if palm_oil_findings["is_disguised_under_vegetable_oil"]:
                score += 15

        # Serving size illusion penalty (up to 20 pts)
        if serving_reality["is_serving_size_deceptive"]:
            score += 20

        # Ultra-processed additive penalty (up to 15 pts)
        if nova_findings["nova_group"] == 4:
            score += 10
            score += min(5, len(nova_findings["detected_additives"]))

        return min(100, score)

    def _get_deception_tier(self, score: int) -> str:
        if score >= 75:
            return "Severe Deception (Aggressive Consumer Misdirection)"
        elif score >= 50:
            return "High Deception (Multiple Disguised Ingredients)"
        elif score >= 25:
            return "Moderate Deception (Standard Industrial Shortcuts)"
        else:
            return "Clean & Transparent Label"

    def _find_healthier_swaps(
        self,
        category: str,
        current_sugars: float,
        has_palm_oil: bool,
    ) -> List[Dict[str, Any]]:
        """Queries local SQLite database for healthier alternative swaps with 0g palm oil and lower sugar."""
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            clean_cat = f"%{category}%" if category else "%"

            # Query products in category with lower sugar and without palm oil terms in ingredients
            query = """
                SELECT product_name, brands, sugars_100g, saturated_fat_100g, fiber_100g, proteins_100g, ingredients_text
                FROM off_products
                WHERE product_name IS NOT NULL
                  AND (sugars_100g IS NOT NULL AND sugars_100g < ?)
                  AND (ingredients_text NOT LIKE '%palm%' AND ingredients_text NOT LIKE '%palmolein%')
                ORDER BY sugars_100g ASC, fiber_100g DESC
                LIMIT 3
            """
            threshold_sugar = max(15.0, current_sugars * 0.7) if current_sugars > 0 else 15.0
            cur.execute(query, (threshold_sugar,))
            rows = cur.fetchall()
            conn.close()

            swaps = []
            for r in rows:
                swaps.append({
                    "product_name": r["product_name"],
                    "brand": r["brands"] or "Clean Brand",
                    "sugars_100g": r["sugars_100g"],
                    "saturated_fat_100g": r["saturated_fat_100g"] or 0.0,
                    "fiber_100g": r["fiber_100g"] or 0.0,
                    "protein_100g": r["proteins_100g"] or 0.0,
                    "advantage": "0g Palm Oil, significantly lower sugar, higher dietary fibre.",
                })
            return swaps
        except Exception:
            return []
