"""Stage 4: Ingredient and Declared Allergen Extraction.

Extracts printed ingredient declarations, parses nested parenthetical ingredients,
identifies declared allergens and trace warnings, and flags uncertainty.

Enforces:
- Never declare a product 'allergen-free' merely because an allergen was not detected.
- Distinguishes explicitly declared allergens from uncertain inference.
- Retains original language and raw printed text.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple


COMMON_ALLERGEN_KEYWORDS = {
    "wheat": "Wheat",
    "gluten": "Gluten",
    "milk": "Milk / Dairy",
    "dairy": "Milk / Dairy",
    "cheese": "Milk / Dairy",
    "butter": "Milk / Dairy",
    "whey": "Milk / Dairy",
    "casein": "Milk / Dairy",
    "soy": "Soybeans / Soy",
    "soya": "Soybeans / Soy",
    "soybean": "Soybeans / Soy",
    "peanut": "Peanuts",
    "peanuts": "Peanuts",
    "almond": "Tree Nuts (Almond)",
    "cashew": "Tree Nuts (Cashew)",
    "walnut": "Tree Nuts (Walnut)",
    "pistachio": "Tree Nuts (Pistachio)",
    "hazelnut": "Tree Nuts (Hazelnut)",
    "egg": "Eggs",
    "eggs": "Eggs",
    "albumin": "Eggs",
    "sesame": "Sesame Seeds",
    "mustard": "Mustard",
    "fish": "Fish",
    "crustacean": "Crustaceans / Shellfish",
    "shellfish": "Crustaceans / Shellfish",
    "shrimp": "Crustaceans / Shellfish",
    "prawn": "Crustaceans / Shellfish",
    "crab": "Crustaceans / Shellfish",
    "sulphite": "Sulphites / Sulfur Dioxide",
    "sulfite": "Sulphites / Sulfur Dioxide",
    "lupin": "Lupin",
    "mollusc": "Molluscs",
}


class IngredientParser:
    """Parses ingredient text, separates items, and audits declared allergens."""

    @classmethod
    def parse_from_text(cls, raw_text: str) -> Dict[str, Any]:
        """Extracts ingredients block and analyzes items and allergens."""
        cleaned_text = raw_text.strip()
        ingredient_block, trace_block = cls._extract_blocks(cleaned_text)

        parsed_items = cls._split_ingredients(ingredient_block) if ingredient_block else []
        declared_allergens, potential_traces = cls._detect_allergens(ingredient_block, trace_block)

        # Review is always required for critical health safety unless verified by authoritative registry
        review_required = True

        return {
            "original_text": ingredient_block if ingredient_block else cleaned_text,
            "parsed_ingredients": parsed_items,
            "declared_allergens": sorted(list(declared_allergens)),
            "potential_traces": sorted(list(potential_traces)),
            "review_required": review_required,
        }

    @classmethod
    def parse_from_ocr_lines(cls, ocr_lines: List[str]) -> Dict[str, Any]:
        """Identifies ingredients lines from an OCR lines list and parses them."""
        full_text = " ".join(ocr_lines)
        return cls.parse_from_text(full_text)

    @classmethod
    def _extract_blocks(cls, text: str) -> Tuple[Optional[str], Optional[str]]:
        ing_block = None
        trace_block = None

        # Search for Ingredients start
        ing_pattern = re.compile(
            r"(?:INGREDIENTS?|CONTAINS|SAMAGRI)\s*[:\-]\s*(.*?)(?=(?:NUTRITION|ALLERGEN|MAY CONTAIN|CONTAINS|MFD|EXP|BATCH|NET WT|\Z))",
            re.IGNORECASE | re.DOTALL,
        )
        m = ing_pattern.search(text)
        if m:
            ing_block = m.group(1).strip()
        else:
            # Fallback: if 'ingredients' is mentioned
            lower_text = text.lower()
            if "ingredient" in lower_text:
                idx = lower_text.find("ingredient")
                ing_block = text[idx: idx + 400].strip()

        # Search for Contains / May Contain allergen declaration
        trace_pattern = re.compile(
            r"(?:MAY CONTAIN|PRODUCED IN A FACILITY THAT ALSO PROCESSES|ALLERGEN INFORMATION|ALLERGENS?)\s*[:\-]?\s*(.*?)(?=(?:NUTRITION|MFD|EXP|BATCH|NET WT|\Z))",
            re.IGNORECASE | re.DOTALL,
        )
        tm = trace_pattern.search(text)
        if tm:
            trace_block = tm.group(1).strip()

        return ing_block, trace_block

    @classmethod
    def _split_ingredients(cls, block: str) -> List[str]:
        """Splits ingredient list while respecting parenthetical nesting."""
        items = []
        current = []
        depth = 0

        for char in block:
            if char in "([{":
                depth += 1
                current.append(char)
            elif char in ")]}":
                depth = max(0, depth - 1)
                current.append(char)
            elif char in ",;." and depth == 0:
                item = "".join(current).strip()
                if item and len(item) > 1 and not item.isnumeric():
                    items.append(item)
                current = []
            else:
                current.append(char)

        if current:
            tail = "".join(current).strip()
            if tail and len(tail) > 1 and not tail.isnumeric():
                items.append(tail)

        # Cleanup trailing punctuation
        cleaned = [re.sub(r"^[\s\-•*]+", "", it).strip() for it in items if it]
        return [c for c in cleaned if len(c) > 1]

    @classmethod
    def _detect_allergens(cls, ing_block: Optional[str], trace_block: Optional[str]) -> Tuple[Set[str], Set[str]]:
        declared = set()
        traces = set()

        if ing_block:
            lower_ing = ing_block.lower()
            for kw, allergen_name in COMMON_ALLERGEN_KEYWORDS.items():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, lower_ing):
                    declared.add(allergen_name)

        if trace_block:
            lower_trace = trace_block.lower()
            for kw, allergen_name in COMMON_ALLERGEN_KEYWORDS.items():
                pattern = rf"\b{re.escape(kw)}\b"
                if re.search(pattern, lower_trace):
                    traces.add(allergen_name)

        return declared, traces
