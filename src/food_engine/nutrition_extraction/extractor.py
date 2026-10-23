"""Stage 5: Nutrition Table Facts Extraction.

Parses OCR lines to extract nutrition facts declarations, identifies serving basis,
extracts all standard macronutrients and micronutrients with explicit units,
and uses a structured missing-value status.

Enforces:
- Never assign 0 to an absent nutrient field. Absent fields are strictly marked 'missing'.
- Retains distinction between Sodium (mg) and Salt (g).
- Detects basis: per 100g, per 100ml, per serving, per piece, per package.
"""

import re
from typing import Any, Dict, List, Optional, Tuple


NUTRIENT_REGEX_MAP = {
    "energy_kcal": [
        r"(?:energy|calories|calorie|energetic\s*value|energie)\b(?:(?!\bfrom\b)[^\d\n])*?(\d+(?:[.,]\d+)?)\s*(?:kcal|calories)?",
        r"(\d+(?:[.,]\d+)?)\s*kcal",
    ],
    "energy_kj": [
        r"(?:energy|energetic\s*value|energie)\b(?:(?!\bfrom\b)[^\d\n])*?(\d+(?:[.,]\d+)?)\s*kj",
        r"(\d+(?:[.,]\d+)?)\s*kj",
    ],
    "protein_g": [
        r"(?:protein|proteins|prot[ée]ines?|eiwei[ßs])\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "carbohydrates_g": [
        r"(?:total\s*carbohydrate|carbohydrates?|carbs?|glucides|kohlenhydrate)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "sugars_g": [
        r"(?:total\s*sugars?|sugars?|dont\s*sucres|davon\s*zucker|sucres)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
        r"(?:of\s*which\s*sugars?|dont\s*sucres)\b\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "added_sugars_g": [
        r"(?:added\s*sugars?|of\s*which\s*added\s*sugars?)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
        r"(?:incl(?:udes|\.)?\s*)(\d+(?:[.,]\d+)?)\s*g\s*added\s*sugars?",
    ],
    "dietary_fibre_g": [
        r"(?:dietary\s*fib(?:re|er)|fib(?:re|er)|fibres?\s*alimentaires?|ballaststoffe|vlaknina)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "total_fat_g": [
        r"(?:total\s*fat|fat|mati[èe]res?\s*grasses?|fett|graisses?|tuk|zs[íi]r|lipides)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "saturated_fat_g": [
        r"(?:saturated\s*fat(?:ty\s*acids?)?|saturates?|dont\s*(?:acides\s*gras\s*)?satur[ée]s?|davon\s*ges[äa]ttigte|tel[íi]tett?\s*)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "trans_fat_g": [
        r"(?:trans\s*fat(?:ty\s*acids?)?|trans\s*fat)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "cholesterol_mg": [
        r"cholesterol\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "sodium_mg": [
        r"(?:sodium|natrium|sodiu?)\s*(?:mg\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "salt_g": [
        r"(?:salt|sel|salz|só)\s*(?:g\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*g?",
    ],
    "iron_mg": [
        r"iron\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "calcium_mg": [
        r"calcium\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "potassium_mg": [
        r"(?:potassium|potass\b|kalis?\b)\s*(?:mg\b)?\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "zinc_mg": [
        r"zinc\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "magnesium_mg": [
        r"magnesium\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "vitamin_c_mg": [
        r"vitamin\s*c\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*mg?",
    ],
    "vitamin_d_mcg": [
        r"vitamin\s*d\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(?:mcg|µg|ug)?",
    ],
}

DEFAULT_UNITS = {
    "energy_kcal": "kcal",
    "energy_kj": "kJ",
    "protein_g": "g",
    "carbohydrates_g": "g",
    "sugars_g": "g",
    "added_sugars_g": "g",
    "dietary_fibre_g": "g",
    "total_fat_g": "g",
    "saturated_fat_g": "g",
    "trans_fat_g": "g",
    "cholesterol_mg": "mg",
    "sodium_mg": "mg",
    "salt_g": "g",
    "iron_mg": "mg",
    "calcium_mg": "mg",
    "potassium_mg": "mg",
    "zinc_mg": "mg",
    "magnesium_mg": "mg",
    "vitamin_c_mg": "mg",
    "vitamin_d_mcg": "mcg",
}

# Units that, when attached to a candidate number on the same row, make that
# candidate trustworthy for a field (energy rows commonly carry both kJ and
# kcal numbers; unit evidence picks the right one).
PREFERRED_UNITS = {
    "energy_kcal": {"kcal", "cal", "calories", "calorie"},
    "energy_kj": {"kj", "kjs"},
    "protein_g": {"g"},
    "carbohydrates_g": {"g"},
    "sugars_g": {"g"},
    "added_sugars_g": {"g"},
    "dietary_fibre_g": {"g"},
    "total_fat_g": {"g"},
    "saturated_fat_g": {"g"},
    "trans_fat_g": {"g"},
    "cholesterol_mg": {"mg"},
    "sodium_mg": {"mg"},
    "salt_g": {"g"},
    "iron_mg": {"mg"},
    "calcium_mg": {"mg"},
    "potassium_mg": {"mg"},
    "zinc_mg": {"mg"},
    "magnesium_mg": {"mg"},
    "vitamin_c_mg": {"mg"},
    "vitamin_d_mcg": {"mcg", "µg", "ug"},
}


def parse_number(tok: str) -> Optional[float]:
    """Parses a numeric token with European/Indian locale awareness.

    Rule (documented heuristic): a comma followed by exactly three digits is
    treated as a thousands separator (Indian/EU style, e.g. '1,098 mg'); a
    comma followed by one or two digits is a decimal point (e.g. '4,1 g').
    Multiple separators: the right-most is the decimal point, earlier ones
    are thousands separators.
    """
    tok = tok.strip()
    if not tok:
        return None
    s = tok
    # Split on both separators; decide decimal from the right-most group length
    groups = re.split(r"[.,]", s)
    if len(groups) == 1:
        try:
            return float(s)
        except ValueError:
            return None
    last = groups[-1]
    head = "".join(groups[:-1])
    if len(last) == 3 and len(groups) == 2:
        # Ambiguous '1,098' style: treat comma-with-3-digits as thousands when
        # the separator is a comma, decimal when it is a dot.
        sep = tok[len(groups[0])]
        if sep == ",":
            return float(groups[0] + last)
        return float(groups[0] + "." + last)
    # Otherwise: separators thousand-joined, right-most group (<3 digits) decimal
    try:
        return float(head + "." + last) if last else float(head)
    except ValueError:
        return None


class NutritionExtractor:
    """Extracts nutrition facts from OCR lines with explicit basis and missing field audit."""

    @classmethod
    def extract(cls, ocr_lines: List[str]) -> Dict[str, Any]:
        full_text = "\n".join(ocr_lines)
        basis, serving_raw, serving_g, serving_ml = cls._detect_basis_and_serving(full_text)

        nutrients: Dict[str, Dict[str, Any]] = {}
        missing_fields: List[str] = []
        conflicting_fields: List[str] = []

        # Header-based column order detection (two-column panels: per serving | per 100g/100ml)
        column_layout = cls._detect_column_layout(ocr_lines)  # None | "serving_first" | "hundred_first"

        for field_name, patterns in NUTRIENT_REGEX_MAP.items():
            unit = DEFAULT_UNITS.get(field_name, "g")
            val, conf, diag = cls._search_patterns(ocr_lines, patterns, field_name, basis, column_layout)

            if val is not None:
                status = "declared"
                if diag.get("selected_from_multiple"):
                    status = "declared"
                    if field_name not in conflicting_fields:
                        conflicting_fields.append(field_name)
                nutrients[field_name] = {
                    "value": val,
                    "unit": unit,
                    "status": status,
                    "confidence": conf,
                    "match_method": diag.get("match_method"),
                }
            else:
                nutrients[field_name] = {
                    "value": None,
                    "unit": unit,
                    "status": "missing",
                    "confidence": None,
                }
                # Track important missing fields
                if field_name in ["energy_kcal", "protein_g", "carbohydrates_g", "total_fat_g", "sodium_mg", "salt_g"]:
                    missing_fields.append(field_name)

        # Internal consistency check: If sodium is missing but salt is declared, calculate sodium
        if nutrients["sodium_mg"]["status"] == "missing" and nutrients["salt_g"]["status"] == "declared":
            salt_val = nutrients["salt_g"]["value"]
            if salt_val is not None:
                # 1g salt ~ 400mg sodium
                calc_sodium = round(salt_val * 400.0, 2)
                nutrients["sodium_mg"] = {
                    "value": calc_sodium,
                    "unit": "mg",
                    "status": "calculated",
                    "confidence": 0.90,
                }
                if "sodium_mg" in missing_fields:
                    missing_fields.remove("sodium_mg")

        # Vice-versa: If salt is missing but sodium is declared
        elif nutrients["salt_g"]["status"] == "missing" and nutrients["sodium_mg"]["status"] == "declared":
            sod_val = nutrients["sodium_mg"]["value"]
            if sod_val is not None:
                calc_salt = round((sod_val / 1000.0) * 2.5, 3)
                nutrients["salt_g"] = {
                    "value": calc_salt,
                    "unit": "g",
                    "status": "calculated",
                    "confidence": 0.90,
                }
                if "salt_g" in missing_fields:
                    missing_fields.remove("salt_g")

        return {
            "basis": basis,
            "serving_size_raw": serving_raw,
            "serving_size_g": serving_g,
            "serving_size_ml": serving_ml,
            "nutrients": nutrients,
            "missing_fields": missing_fields,
            "conflicting_fields": conflicting_fields,
        }

    @classmethod
    def _detect_column_layout(cls, lines: List[str]) -> Optional[str]:
        """Detects a two-column header (e.g. 'Per serving | Per 100g').

        Matches multilingual markers (per/par/pour/na/pro) for a per-100
        column and per-serving/mass/portion columns. Returns
        'serving_first' | 'hundred_first' | None.
        """
        marker_re = re.compile(
            r"(?:\b(?:per|par|pour|na|pro)\s*)?"
            r"(\b100\s*(?:g|ml)\b|\b\d+(?:[.,]\d+)?\s*(?:g|ml)\b|\bserving\b|\bportion\b(?:\s*de)?(?:\s*\d+(?:[.,]\d+)?\s*(?:g|ml))?|\bbiscuit\b|\bpiece\b|\bcan\b|\bcup\b|\bkit\b)",
            re.IGNORECASE,
        )
        for line in lines:
            low = line.lower()
            marks: List[Tuple[int, str]] = []
            for m in marker_re.finditer(low):
                tok = m.group(1).lower()
                is_100 = bool(re.match(r"100\s*(g|ml)", tok))
                marks.append((m.start(1), "hundred" if is_100 else "other"))
            kinds = [k for _, k in marks]
            if "hundred" in kinds and "other" in kinds:
                return "serving_first" if kinds.index("other") < kinds.index("hundred") else "hundred_first"
        return None

    @classmethod
    def _pick_candidate(
        cls,
        cands: List[Tuple[float, Any, Optional[str]]],
        field_name: str,
        basis: str,
        column_layout: Optional[str],
    ) -> Tuple[Optional[float], bool]:
        """Chooses among candidate values found on the same text scope.

        Selection rules (in order):
        1. If several candidates and an attached-unit preference exists, prefer
           candidates whose immediately-following unit matches the field family
           (kJ vs kcal disambiguation on energy rows).
        2. Two-column panels: pick the column matching the detected basis.
        3. Otherwise the first non-percent value (left-to-right order).
        Returns (value, selected_from_multiple).
        """
        if not cands:
            return None, False

        pref = PREFERRED_UNITS.get(field_name)
        pool = cands
        if pref:
            # Drop candidates whose attached unit contradicts the field family
            # (kJ numbers can never be kcal values; g can never be mg, etc.).
            budget = set(pref) | {None}
            filtered = [c for c in pool if c[2] in budget]
            if not filtered:
                # Every candidate on this scope contradicts the field's unit
                # family -> the scope contains no value for this field.
                return None, False
            pool = filtered
            with_unit = [c for c in pool if c[2]]
            if with_unit:
                pool = with_unit

        if len(pool) == 1:
            return pool[0][1], False

        if len(pool) > 1 and basis in ("per_100_g", "per_100_ml") and column_layout == "serving_first":
            return pool[-1][1], True
        if len(pool) > 1 and basis in ("per_100_g", "per_100_ml") and column_layout == "hundred_first":
            return pool[0][1], True
        if len(pool) > 1 and basis == "per_serving" and column_layout is not None:
            return pool[0][1], True
        return pool[0][1], len(cands) > 1

    @classmethod
    def _search_patterns(
        cls,
        lines: List[str],
        patterns: List[str],
        field_name: str | None = None,
        basis: str = "per_100_g",
        column_layout: Optional[str] = None,
    ) -> Tuple[Optional[float], Optional[float], Dict[str, Any]]:
        """Searches for the field's value across lines, adjacent pairs, full text.

        Candidate numbers are parsed with locale awareness, DV-percent captures
        are excluded, and unit evidence / column layout drive the final pick.
        """
        def _scan(text: str, extend: bool = False) -> List[Tuple[float, Any, Optional[str]]]:
            cands: List[Tuple[float, Any, Optional[str]]] = []
            seen_positions: set = set()

            def add_candidate(pos: int, raw: str, text: str, after: int) -> None:
                val = parse_number(raw)
                if val is None:
                    return
                tail = text[after: after + 2]
                if tail.startswith("%"):
                    return  # % DV capture, not a nutrient amount
                if pos in seen_positions:
                    return
                seen_positions.add(pos)
                um = re.match(
                    r"\s*(kcal|calories?|cal|kj|g|mg|mcg|µg|ug|ml|l)\b",
                    text[after:],
                    re.IGNORECASE,
                )
                unit = um.group(1).lower() if um else None
                cands.append((pos, val, unit))

            for pat in patterns:
                for m in re.finditer(pat, text, re.IGNORECASE):
                    add_candidate(m.start(1), m.group(1), text, m.end(1))
                    if extend:
                        # Same-print-row extension: values further right on the
                        # same OCR line (second table column) also count, so a
                        # shared row can be resolved column-wise downstream.
                        num_re = re.compile(r"\d+(?:[.,]\d+)?")
                        rest = text[m.end(1):]
                        for nm in list(num_re.finditer(rest))[:4]:
                            add_candidate(m.end(1) + nm.start(), nm.group(0), text, m.end(1) + nm.end())
            cands.sort(key=lambda c: c[0])
            return cands

        scopes = []
        for line in lines:
            scopes.append((line.strip().lower(), 0.90, True))
        for i in range(len(lines) - 1):
            scopes.append((f"{lines[i].strip()} {lines[i+1].strip()}".lower(), 0.85, False))
        scopes.append((" ".join(lines).lower(), 0.80, False))

        for text, conf, extend in scopes:
            cands = _scan(text, extend=extend)
            if not cands:
                continue
            val, multiple = cls._pick_candidate(cands, field_name or "", basis, column_layout)
            if val is None:
                continue
            method = "line" if conf == 0.90 else ("adjacent_pair" if conf == 0.85 else "full_text")
            return val, conf, {
                "match_method": method,
                "selected_from_multiple": multiple,
                "candidates": [(round(c[1], 4), c[2]) for c in cands],
            }
            return val, conf, {
                "match_method": method,
                "selected_from_multiple": multiple,
                "candidates": [(round(c[1], 4), c[2]) for c in cands],
            }
        return None, None, {}

    @classmethod
    def _detect_basis_and_serving(cls, text: str) -> Tuple[str, Optional[str], Optional[float], Optional[float]]:
        lower = text.lower()
        basis = "per_100_g"
        serving_raw = None
        serving_g = None
        serving_ml = None

        # Check explicit serving size declaration
        m_srv = re.search(r"serving\s*size\s*[:\-]?\s*([^\n,;]+)", lower)
        if m_srv:
            serving_raw = m_srv.group(1).strip()
            # Extract grams or ml from serving text
            mg = re.search(r"(\d+(?:\.\d+)?)\s*g\b", serving_raw)
            if mg:
                serving_g = float(mg.group(1))
            mml = re.search(r"(\d+(?:\.\d+)?)\s*ml\b", serving_raw)
            if mml:
                serving_ml = float(mml.group(1))

        # Check basis
        if "per 100 ml" in lower or "per 100ml" in lower or "/100 ml" in lower or "/100ml" in lower:
            basis = "per_100_ml"
        elif "per 100 g" in lower or "per 100g" in lower or "/100 g" in lower or "/100g" in lower:
            basis = "per_100_g"
        elif "per serving" in lower or "/serving" in lower:
            basis = "per_serving"
        elif "per piece" in lower or "per biscuit" in lower:
            basis = "per_piece"
        elif "per package" in lower or "per pack" in lower:
            basis = "per_package"

        return basis, serving_raw, serving_g, serving_ml

