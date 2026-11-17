"""Google Gemini AI Clinical Nutritionist & Multimodal Label Intelligence.

Utilizes Google Gemini (gemini-1.5-flash) for:
1. Translating chemical additives (E-numbers, INS numbers) into clinical risk assessments.
2. Analyzing nutritional profiles for specific health conditions (Diabetes, Hypertension, Celiac).
3. Providing plain-English health conclusions grounded in WHO and FSSAI standards.
"""

from functools import lru_cache
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

def _safe_load_env():
    try:
        from dotenv import load_dotenv
        _CUR_DIR = Path(__file__).resolve().parent
        for _p in [_CUR_DIR, _CUR_DIR.parent, _CUR_DIR.parent.parent, _CUR_DIR.parent.parent.parent]:
            _env_candidate = _p / ".env"
            if _env_candidate.exists():
                load_dotenv(_env_candidate)
                break
    except ImportError:
        _CUR_DIR = Path(__file__).resolve().parent
        for _p in [_CUR_DIR, _CUR_DIR.parent, _CUR_DIR.parent.parent, _CUR_DIR.parent.parent.parent]:
            _env_candidate = _p / ".env"
            if _env_candidate.exists():
                with open(_env_candidate, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k not in os.environ:
                                os.environ[k] = v
                break

_safe_load_env()

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


class GeminiNutritionAssistant:
    """Interface to Google Gemini for advanced clinical food intelligence."""

    @classmethod
    def is_configured(cls) -> bool:
        """Checks if a valid Gemini API key is configured."""
        key = os.getenv("GEMINI_API_KEY", "")
        return bool(key and not key.startswith("PASTE_YOUR"))

    @classmethod
    def test_connection(cls) -> Tuple[bool, str]:
        """Tests the Gemini API connection."""
        if not cls.is_configured():
            return False, "GEMINI_API_KEY not configured in .env"
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={os.getenv('GEMINI_API_KEY')}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                return True, f"Active ({GEMINI_MODEL})"
            return False, f"HTTP Error {res.status_code}: {res.text[:100]}"
        except Exception as exc:
            return False, f"Connection Failed: {type(exc).__name__}"

    @classmethod
    def analyze_food_package(
        cls,
        product_name: str,
        nutrients: Dict[str, Any],
        ingredients_text: str,
        declared_allergens: List[str],
    ) -> Dict[str, Any]:
        """Generates an evidence-backed clinical nutrition assessment from Gemini."""
        if not cls.is_configured():
            return {
                "available": False,
                "error": "Gemini API key is not configured in .env",
            }

        # Build clean nutrient summary
        nut_lines = []
        for k, v in nutrients.items():
            if isinstance(v, dict) and v.get("value") is not None:
                nut_lines.append(f"- {k.replace('_', ' ').title()}: {v['value']} {v.get('unit', '')}")

        nut_summary = "\n".join(nut_lines) if nut_lines else "No nutrients declared."
        allergens_str = ", ".join(declared_allergens) if declared_allergens else "None declared"

        prompt = f"""
You are an expert clinical dietitian and food safety compliance auditor specializing in FSSAI, US FDA, and WHO nutritional guidelines.
Analyze the following packaged food item:

Product Name: {product_name}
Nutritional Facts (per 100g):
{nut_summary}

Declared Allergens: {allergens_str}
Ingredients List: {ingredients_text or "Not stated"}

Provide a structured, evidence-backed clinical summary answering:
1. **Additive & Preservative Screening**: Identify any INS / E-number chemical additives, emulsifiers, or preservatives (e.g. INS 503, E319, INS 322). State their safety profile and purpose.
2. **Clinical Risk Highlights**: Evaluate suitability for individuals with Type-2 Diabetes, Hypertension (High Blood Pressure), Cardiovascular conditions, or Celiac Disease.
3. **Ultra-Processing Level (NOVA estimation)**: Is this minimally processed, processed culinary ingredient, or ultra-processed (UPF)?
4. **Bottom-Line Dietitian Verdict**: 1-2 sentence recommendation for consumers.

Be concise, authoritative, and medically grounded. Use clean markdown.
"""

        try:
            payload = {
                "contents": [
                    {
                        "parts": [
                            {"text": prompt}
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 800,
                }
            }

            key = os.getenv("GEMINI_API_KEY")
            candidate_models = [GEMINI_MODEL, "gemini-1.5-flash", "gemini-2.0-flash"]
            # Deduplicate preserving order
            candidate_models = list(dict.fromkeys(candidate_models))

            last_err = ""
            for model_name in candidate_models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
                try:
                    resp = requests.post(
                        url,
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=12.0,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates:
                            analysis_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            return {
                                "available": True,
                                "model": model_name,
                                "analysis": analysis_text,
                            }
                    last_err = f"Gemini ({model_name}) status {resp.status_code}: {resp.text[:120]}"
                except Exception as req_exc:
                    last_err = f"Gemini ({model_name}) exception: {req_exc}"

            return {
                "available": False,
                "error": last_err or "Gemini API unavailable",
            }
        except Exception as exc:
            logger.error(f"Gemini API execution error: {exc}")
            return {
                "available": False,
                "error": f"Gemini request exception: {type(exc).__name__}: {str(exc)}",
            }
