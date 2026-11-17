"""External API integrations (Google Gemini AI, USDA FoodData Central)."""
from food_engine.external_apis.gemini_assistant import GeminiNutritionAssistant
from food_engine.external_apis.usda_client import USDAFoodDataClient

__all__ = ["GeminiNutritionAssistant", "USDAFoodDataClient"]
