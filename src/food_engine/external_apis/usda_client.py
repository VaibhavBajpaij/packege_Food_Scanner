"""USDA FoodData Central API Client.

Enables searching the official USDA FoodData Central database for:
1. Foundation food reference profiles.
2. Verified micronutrients (Calcium, Iron, Potassium, Vitamin D, Magnesium, Zinc).
3. Ground-truth cross-referencing for branded packaged foods.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


class USDAFoodDataClient:
    """Client for USDA FoodData Central REST API."""

    BASE_URL = "https://api.nal.usda.gov/fdc/v1"

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        """Fetches API key from environment."""
        key = os.getenv("USDA_API_KEY") or os.getenv("FDC_API_KEY")
        if key and not key.startswith("PASTE_YOUR"):
            return key
        return None

    @classmethod
    def is_configured(cls) -> bool:
        return cls.get_api_key() is not None

    @classmethod
    def test_connection(cls) -> Tuple[bool, str]:
        """Tests connectivity to USDA FoodData Central."""
        key = cls.get_api_key()
        if not key:
            return False, "USDA_API_KEY not configured in .env"
        try:
            url = f"{cls.BASE_URL}/foods/search?query=biscuit&pageSize=1&api_key={key}"
            resp = requests.get(url, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("totalHits", 0)
                return True, f"Connected ({total:,} reference foods indexed)"
            return False, f"HTTP Error {resp.status_code}: {resp.text[:100]}"
        except Exception as exc:
            return False, f"Connection Failed: {type(exc).__name__}"

    @classmethod
    def search_foods(cls, query: str, page_size: int = 3) -> List[Dict[str, Any]]:
        """Searches USDA FoodData Central database for foods matching query."""
        key = cls.get_api_key()
        if not key or not query:
            return []

        try:
            url = f"{cls.BASE_URL}/foods/search"
            params = {
                "query": query,
                "pageSize": page_size,
                "api_key": key,
                "dataType": ["Branded", "Foundation", "SR Legacy"],
            }
            resp = requests.get(url, params=params, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("foods", [])
            else:
                logger.warning(f"USDA API error {resp.status_code}: {resp.text[:100]}")
                return []
        except Exception as exc:
            logger.error(f"USDA search exception: {exc}")
            return []
