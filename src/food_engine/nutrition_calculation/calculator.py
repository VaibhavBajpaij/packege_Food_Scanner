"""Stage 7: Deterministic Nutrition Calculations and Unit Conversions.

Implements exact Python arithmetic:
- Full package scaling:
  full_package_value = value_per_100g * package_weight_g / 100.0
- Liquid volume scaling:
  full_package_value = value_per_100ml * package_volume_ml / 100.0 (density aware)
- Salt to Sodium:
  sodium_mg = salt_g * 1000.0 * 0.4
- Sodium to Salt:
  salt_g = (sodium_mg / 1000.0) * 2.5
- Energy conversion:
  energy_kj = energy_kcal * 4.184

Enforces:
- Never convert between mass and volume without an explicit density value.
- Retains original value and unit alongside every normalized value.
- Never estimate unknown micronutrients using generative models.
"""

from typing import Any, Dict, Optional, Tuple


class NutritionCalculator:
    """Performs deterministic unit normalization and package nutrient scaling."""

    SALT_TO_SODIUM_FACTOR = 0.4   # 1 g NaCl ~ 0.4 g (400 mg) Na
    SODIUM_TO_SALT_FACTOR = 2.5   # 1 g Na ~ 2.5 g NaCl
    KCAL_TO_KJ_FACTOR = 4.184

    @classmethod
    def calculate_package_totals(
        cls,
        nutrients_per_100: Dict[str, Dict[str, Any]],
        package_weight_g: Optional[float] = None,
        package_volume_ml: Optional[float] = None,
        liquid_density_g_per_ml: Optional[float] = None,
        basis: str = "per_100_g",
    ) -> Dict[str, Any]:
        """Calculates total nutrient content for the full package."""
        calculated_nutrients = {}
        method = "none"

        # Determine scaling factor
        scale_factor = None
        if basis == "per_100_g" and package_weight_g is not None and package_weight_g > 0:
            scale_factor = package_weight_g / 100.0
            method = f"weight_scaling ({package_weight_g}g / 100g)"
        elif basis == "per_100_ml" and package_volume_ml is not None and package_volume_ml > 0:
            scale_factor = package_volume_ml / 100.0
            method = f"volume_scaling ({package_volume_ml}ml / 100ml)"
        elif basis == "per_100_ml" and package_weight_g is not None and liquid_density_g_per_ml is not None:
            # Volume = weight / density
            volume_ml = package_weight_g / liquid_density_g_per_ml
            scale_factor = volume_ml / 100.0
            method = f"density_derived_volume_scaling ({package_weight_g}g / {liquid_density_g_per_ml}g/ml = {round(volume_ml, 1)}ml)"

        if scale_factor is not None:
            for nut_name, item in nutrients_per_100.items():
                val = item.get("value")
                unit = item.get("unit", "g")
                status = item.get("status")

                if val is not None and status in ("declared", "calculated", "reference_derived"):
                    scaled_val = round(val * scale_factor, 2)
                    calculated_nutrients[nut_name] = {
                        "value": scaled_val,
                        "unit": unit,
                        "status": "calculated",
                        "basis": "per_package",
                        "original_per_100_value": val,
                    }
                else:
                    calculated_nutrients[nut_name] = {
                        "value": None,
                        "unit": unit,
                        "status": "missing",
                        "basis": "per_package",
                    }

        return {
            "package_weight_g": package_weight_g,
            "package_volume_ml": package_volume_ml,
            "calculation_method": method,
            "calculated_nutrients": calculated_nutrients,
        }

    @classmethod
    def convert_sodium_and_salt(
        cls, sodium_mg: Optional[float] = None, salt_g: Optional[float] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """Calculates complementary salt or sodium if one is absent."""
        if sodium_mg is not None and salt_g is None:
            derived_salt = round((sodium_mg / 1000.0) * cls.SODIUM_TO_SALT_FACTOR, 3)
            return sodium_mg, derived_salt
        elif salt_g is not None and sodium_mg is None:
            derived_sodium = round(salt_g * 1000.0 * cls.SALT_TO_SODIUM_FACTOR, 2)
            return derived_sodium, salt_g
        return sodium_mg, salt_g

    @classmethod
    def convert_energy(
        cls, kcal: Optional[float] = None, kj: Optional[float] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """Converts between kcal and kJ."""
        if kcal is not None and kj is None:
            derived_kj = round(kcal * cls.KCAL_TO_KJ_FACTOR, 1)
            return kcal, derived_kj
        elif kj is not None and kcal is None:
            derived_kcal = round(kj / cls.KCAL_TO_KJ_FACTOR, 1)
            return derived_kcal, kj
        return kcal, kj
