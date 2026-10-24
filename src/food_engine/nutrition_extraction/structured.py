"""Bounding-box aware nutrition-table extraction.

The historical string-only extractor had to guess which of several numbers on a
line belonged to a nutrient.  Food labels routinely put two columns (per
serving / per 100 g), a %DV column, and several nutrient rows at almost the same
vertical position on the page.  This module keeps the OCR geometry so each
number can be tied to a nutrient label, a table column, and a nearby row.

Design rules:
- One OCR line is one *cell*.  Cells are never merged into synthetic rows; that
  avoids the over-merging that the old line-grouping experiment produced on
  labels with text beside the nutrition table.
- A nutrient name and its value may live in the same cell ("Total Fat 7 g") or
  in separate cells ("Total Fat" beside "7 g").  The latter is resolved by
  vertical proximity plus the detected value-column.
- Columns are detected from header cells ("per 100 g", "per serving", "/51 g",
  "Amount/Serving", "%DV").  When both per-serving and per-100 columns exist,
  the column matching the declared basis is used.
- Percent values are never nutrient amounts.  Unit families are enforced, and
  a g/mg mismatch is converted only when the field's own unit family allows it.
- No full-page regex fallback: a value must be geometrically attributable to a
  nutrient label.  This prevents prose such as "2,000 calorie diet" being read
  as an energy declaration.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple
import re
import unicodedata

from food_engine.nutrition_extraction.extractor import DEFAULT_UNITS, parse_number


# Values above these limits cannot be real declarations for one serving or
# 100 g/ml of a food, so they indicate an OCR/column-association error.
FIELD_MAX_VALUES = {
    "vitamin_d_mcg": 1000.0,
    "sodium_mg": 40000.0,
    "salt_g": 100.0,
    "cholesterol_mg": 5000.0,
}


# ---------------------------------------------------------------------------
# Text normalisation (OCR-tolerant, nutrition-context only)
# ---------------------------------------------------------------------------

# Corrections are deliberately limited to errors repeatedly observed on
# photographed labels.  Raw OCR text is never modified; only the copy used for
# parsing is normalised.
_WORD_CORRECTIONS = [
    (r"\bkcal\|", "kcal"),
    (r"\bkca(?:l)?\|", "kcal"),
    (r"\bkca\b", "kcal"),
    (r"\bproteln\b", "protein"),
    (r"\bprotern\b", "protein"),
    (r"\bsodlum\b", "sodium"),
    (r"\bodium\b", "sodium"),
    (r"\batieres\b", "matieres"),
    (r"\biont\b", "dont"),
    (r"\bdudides\b", "glucides"),
    (r"\bbres\b", "fibres"),
    (r"\bsatuzated\b", "saturated"),
    (r"\bsaturatedf\b", "saturated fat"),
    (r"\bsaturatedfat\b", "saturated fat"),
    (r"\btotalcarbohydrate\b", "total carbohydrate"),
    (r"\bcholestelol\b", "cholesterol"),
    (r"\bor\s+which\b", "of which"),
    (r"\botal\s+fat\b", "total fat"),
    (r"\bnergie\b", "energie"),
    (r"\bcal\s+es\b", "calories"),
    (r"^es\s+(?=\d)", "calories "),
    (r"\b100\s*ml+\b", "100 ml"),
    (r"\bomg\b", "0mg"),
    (r"\bog\b", "0g"),
    (r"\bgr(?:ams?)?\b", "g"),
]


def normalize_ocr_text(text: str) -> str:
    """NFKC + casefold + conservative OCR fixes used only by the parser."""
    s = unicodedata.normalize("NFKC", str(text))
    s = s.replace("\u00a0", " ").replace("\u2013", "-").replace("\u2014", "-")
    s = s.casefold()
    s = re.sub(r"\s+", " ", s).strip()
    for pat, repl in _WORD_CORRECTIONS:
        s = re.sub(pat, repl, s)
    # Fused label/value cells ("Protein4g", "Sodium290mg", "kcal492").
    s = re.sub(r"(?<=[a-z])(?=\d)", " ", s)
    # OCR confuses a trailing 9 with g ("51.89" -> "51.8 g").
    s = re.sub(r"(\d+[.,]\d+)9\b", r"\1 g", s)
    # "43.7.q" / "43.7q" -> "43.7 g"
    s = re.sub(r"(\d+[.,]\d+)\.?[q]\b", r"\1 g", s)
    # A trailing zero on two-decimal values ("0.630" -> "0.63 g").
    s = re.sub(r"(\d+[.,]\d{2})0\b", r"\1 g", s)
    # O-for-zero inside numeric tokens ("O.03g").
    s = re.sub(r"(?<=\d)[oO](?=[.,]\d)", "0", s)
    s = re.sub(r"\bo(?=\s*(?:g|mg|kj|kcal)\b)", "0", s)
    return s


# ---------------------------------------------------------------------------
# Data records
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    value: float
    unit: Optional[str]
    raw: str
    pos_start: int
    pos_end: int
    x_center: float
    y_center: float
    has_percent: bool = False
    upper_bound: bool = False


@dataclass
class FieldHit:
    field: str
    start: int
    end: int
    x_start: float
    x_end: float


@dataclass
class Cell:
    text: str
    raw_text: str
    confidence: float
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    candidates: List[Candidate] = field(default_factory=list)
    hits: List[FieldHit] = field(default_factory=list)
    is_header: bool = False

    @property
    def y_center(self) -> float:
        return (self.y_min + self.y_max) / 2.0

    @property
    def height(self) -> float:
        return max(1.0, self.y_max - self.y_min)

    @property
    def width(self) -> float:
        return max(1.0, self.x_max - self.x_min)

    def x_at(self, pos: int) -> float:
        frac = max(0.0, min(1.0, pos / max(1, len(self.text))))
        return self.x_min + frac * (self.x_max - self.x_min)


@dataclass
class Column:
    kind: str  # hundred | serving | percent
    x_min: float
    x_max: float
    y_center: float = 0.0

    @property
    def center(self) -> float:
        return (self.x_min + self.x_max) / 2.0


# ---------------------------------------------------------------------------
# Field vocabulary (multilingual, ordered most-specific first)
# ---------------------------------------------------------------------------

FIELD_DEFS: List[Tuple[str, List[str]]] = [
    ("added_sugars_g", [
        r"\badded\s+sugars?\b",
        r"\bincl(?:udes|\.)?\.?\s*\d+(?:[.,]\d+)?\s*g\s+added\s+sugars?\b",
    ]),
    ("saturated_fat_g", [
        r"\bsaturated\s*fat\b", r"\bsaturated\b", r"\bsat\.?\s*fat\b",
        r"\bsaturates?\b",
        r"\bdont\s+(?:acides\s+gras\s+)?satur", r"\bdavon\s+ges",
        r"\bges(?:ä|a)ttigte", r"\btel(?:í|i)tett", r"\bmattat\s+fett",
        r"\bmaettede", r"\bnasycone", r"\bverzadigde\s+vetzuren",
        r"\bvarav\s+mattat", r"\bsatur[ée]s?\b",
    ]),
    ("trans_fat_g", [r"\btrans\s*fat\b"]),
    ("sugars_g", [
        r"\btotal\s+sugars?\b", r"\bsugars?\b", r"\bdont\s+sucres\b",
        r"\bof\s+which\s+sugars?\b", r"\bdavon\s+zucker\b",
        r"\bvarav\s+socker", r"\bjosta\s+sokereita\b", r"\bheraf\s+sukker",
        r"\bhvorav\s+sukker", r"\bw\s+tym\s+cukry\b", r"\bsucres\b",
        r"\bwaarvan\s+suikers\b", r"\bcukor\b", r"\bsukkerarter\b",
    ]),
    ("dietary_fibre_g", [
        r"\bdietary\s*fib(?:re|er)\b", r"\bfib(?:re|er)\b",
        r"\bfibres?\s+alimentaires?\b", r"\bballaststoffe\b",
        r"\bvlaknina\b", r"\bkostfibre\b", r"\bkuitu\b", r"\bvezels\b",
    ]),
    ("protein_g", [
        r"\bproteins?\b", r"\bprot[ée]ines?\b", r"\beiwei",
        r"\beiwitten\b", r"\bbia(?:ł|l)ko\b", r"\bvalkuaiset\b",
        r"\bbilkoviny\b",
    ]),
    ("carbohydrates_g", [
        r"\btotal\s+carbohydrate\b", r"\bcarbohydrates?\b", r"\bcarbs?\b",
        r"\bglucides?\b", r"\bkohlenhydrate\b", r"\bkolhydrater\b",
        r"\bhiilihydraattia\b", r"\bkulhydrater\b", r"\bkarbohydrater\b",
        r"\bwe(?:g|ę)lowodany\b", r"\bsacharidy\b", r"\bsacharid\b",
    ]),
    ("total_fat_g", [
        r"\btotal\s*fat\b", r"\bfat\b", r"\bmati[èe]res?\s+grasses?\b",
        r"\bfett\b", r"\bgraisses?\b", r"\btuk\b", r"\bzs[íi]r\b",
        r"\blipides\b", r"\bt(?:ł|l)uszcz\b", r"\brasvaa\b", r"\bfedt\b",
        r"\bvetten\b",
    ]),
    ("cholesterol_mg", [r"\bcholesterol\b"]),
    ("sodium_mg", [
        r"\bsodium\b", r"\bnatrium\b", r"\bs[oó]d\b", r"\bsód\b",
    ]),
    ("salt_g", [
        r"\bsalt\b", r"\bsel\b", r"\bsalz\b", r"\bsó\b", r"\bsuolaa\b",
        r"\bsol\b", r"\bzout\b",
    ]),
    ("iron_mg", [r"\biron\b", r"\bfer\b", r"\beisen\b", r"\b(?:ż|z)elazo\b"]),
    ("calcium_mg", [r"\bcalcium\b", r"\bcalcio\b", r"\bkalzium\b", r"\bwapn\b"]),
    ("potassium_mg", [r"\bpotassium\b", r"\bkalium\b", r"\bpotas\b"]),
    ("magnesium_mg", [r"\bmagnesium\b"]),
    ("zinc_mg", [r"\bzinc\b"]),
    ("vitamin_c_mg", [r"\bvitamin\s*c\b", r"\bvit\.?\s*c\b"]),
    ("vitamin_d_mcg", [r"\bvitamin\s*d\b", r"\bvit\.?\s*d\b"]),
    ("energy_kcal", [
        r"\benergy\b", r"\benergie\b", r"\bcalories?\b",
        r"\benergetic\s+value\b", r"\bbrennwert\b", r"\benergi\b",
    ]),
]

ENERGY_FIELDS = {"energy_kcal", "energy_kj"}

# Fields whose label is a generic word that also appears inside another
# nutrient's name.  Specific fields are matched first and their spans are
# protected, so "saturated fat" can never become "total fat".
_GENERIC_FIELD_GUARDS = {
    "total_fat_g": ("saturated", "saturates", "trans fat", "polyunsaturated",
                    "monounsaturated", "calories from fat"),
    "sugars_g": ("added sugars", "added sugar"),
    "carbohydrates_g": ("other carbohydrate", "other carbohydrates", "other carbs"),
    "dietary_fibre_g": ("soluble fiber", "insoluble fiber", "soluble fibre",
                        "insoluble fibre"),
    "energy_kcal": ("daily diet", "general nutrition advice", "calories a day"),
}


# ---------------------------------------------------------------------------
# Candidate / field parsing
# ---------------------------------------------------------------------------

_UNIT_ALIASES = {
    "kcal": "kcal", "cal": "kcal", "calorie": "kcal", "calories": "kcal",
    "kj": "kj", "g": "g", "mg": "mg", "mcg": "mcg", "µg": "mcg", "ug": "mcg",
    "ml": "ml", "l": "l",
}
_POST_UNIT_RE = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>kcal|calories?|cal|kj|mg|mcg|µg|ug|ml|g)(?![a-z])",
    re.IGNORECASE,
)
_PRE_UNIT_RE = re.compile(
    r"(?P<unit>kcal|calories?|cal|kj|mg|mcg|µg|ug|ml|g)\s*(?P<num>\d+(?:[.,]\d+)?)(?![a-z])",
    re.IGNORECASE,
)
_BARE_RE = re.compile(r"(?<![\w.])(?P<num>\d+(?:[.,]\d+)?)(?![\w.])")


def _x_for_span(cell: "Cell", start: int, end: int) -> Tuple[float, float]:
    return cell.x_at(start), cell.x_at(end)


def _inside_parentheses(text: str, pos: int) -> bool:
    return text.rfind("(", 0, pos) > text.rfind(")", 0, pos)


def _has_percent_after(text: str, end: int) -> bool:
    return re.match(r"\s*%", text[end:]) is not None


def _looks_upper_bound(text: str, start: int) -> bool:
    before = text[max(0, start - 14):start]
    return bool(re.search(r"(?:<|less\s+than|max(?:imum)?|up\s+to|trace)\s*$", before))


def extract_candidates(cell: Cell) -> List[Candidate]:
    text = cell.text
    found: List[Candidate] = []
    occupied: List[Tuple[int, int]] = []

    def add(match: re.Match, unit: Optional[str], num_pos: int, num_end: int,
            span_start: int, span_end: int) -> None:
        if any(not (span_end <= a or span_start >= b) for a, b in occupied):
            return
        if _inside_parentheses(text, span_start):
            return
        if _has_percent_after(text, span_end):
            return
        raw = match.group("num")
        value = parse_number(raw)
        if value is None:
            return
        x0, x1 = _x_for_span(cell, span_start, span_end)
        found.append(Candidate(
            value=value,
            unit=_UNIT_ALIASES.get(unit.casefold()) if unit else None,
            raw=raw,
            pos_start=span_start,
            pos_end=span_end,
            x_center=(x0 + x1) / 2.0,
            y_center=cell.y_center,
            has_percent=_has_percent_after(text, span_end),
            upper_bound=_looks_upper_bound(text, span_start),
        ))
        occupied.append((span_start, span_end))

    for m in _POST_UNIT_RE.finditer(text):
        add(m, m.group("unit"), m.start("num"), m.end("num"), m.start(), m.end())
    for m in _PRE_UNIT_RE.finditer(text):
        add(m, m.group("unit"), m.start("num"), m.end("num"), m.start(), m.end())
    for m in _BARE_RE.finditer(text):
        add(m, None, m.start("num"), m.end("num"), m.start(), m.end())

    # Preserve reading order; downstream proximity chooses among them.
    found.sort(key=lambda c: c.pos_start)
    return found


def find_field_hits(cell: Cell) -> List[FieldHit]:
    text = cell.text
    hits: List[FieldHit] = []
    protected: List[Tuple[int, int]] = []

    # Short salt labels ("Se", "So") survive OCR on multilingual panels but
    # are too short for the normal word patterns.
    if text.strip() in {"se", "so"}:
        x0, x1 = _x_for_span(cell, 0, len(text))
        hits.append(FieldHit("salt_g", 0, len(text), x0, x1))
        return hits
    # "Cal" is the standard US abbreviation for Calories, but matching it as a
    # generic word would also catch "calcium" fragments.
    if text.strip() == "cal":
        x0, x1 = _x_for_span(cell, 0, len(text))
        hits.append(FieldHit("energy_kcal", 0, len(text), x0, x1))
        return hits

    for field_name, patterns in FIELD_DEFS:
        guard = _GENERIC_FIELD_GUARDS.get(field_name, ())
        if any(g in text for g in guard):
            continue
        for pat in patterns:
            m = re.search(pat, text)
            if not m:
                continue
            if any(not (m.end() <= a or m.start() >= b) for a, b in protected):
                continue
            x0, x1 = _x_for_span(cell, m.start(), m.end())
            hits.append(FieldHit(field_name, m.start(), m.end(), x0, x1))
            protected.append((m.start(), m.end()))
            break
    hits.sort(key=lambda h: h.start)
    return hits


# ---------------------------------------------------------------------------
# Column detection
# ---------------------------------------------------------------------------

_HUNDRED_RE = re.compile(
    r"(?:\bper\b|\bpour\b|\bpar\b|\bna\b|\bpro\b|/)?\s*"
    r"(?:100\s*(?:g|ml)\b|(?:g|ml)\s*100\b|\bper\s+100\b)",
    re.IGNORECASE,
)
_SERVING_RE = re.compile(
    r"(?:\bper\b|\bpar\b|\bpour\b|\bna\b|\bpro\b|/)\s*"
    r"(?:serving|portion|piece|biscuit|can|cup|package|pack|"
    r"\d+(?:[.,]\d+)?\s*(?:g|ml))\b",
    re.IGNORECASE,
)
_PAREN_SERVING_RE = re.compile(
    r"\(\s*\d+(?:[.,]\d+)?\s*(?:g|ml)\s*\)", re.IGNORECASE
)
_PURE_SIZE_RE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*(?:g|ml)\s*$", re.IGNORECASE
)
_PERCENT_RE = re.compile(r"%\s*/?\s*$|%daily\s*value|%dv", re.IGNORECASE)
_PERCENT_HEADER_RE = re.compile(
    r"%\s*(?:da|daily|dv|value)|\bdaily\s*value|\(\s*%\s*\)|^\s*%\s*$",
    re.IGNORECASE,
)


def _header_like(cell: Cell) -> bool:
    t = cell.text
    if len(t) > 48:
        return False
    if "size" in t or "ingredient" in t:
        return False
    return True


def detect_columns(cells: Sequence[Cell]) -> List[Column]:
    marks: List[Column] = []

    def add(kind: str, start: int, end: int, cell: Cell) -> None:
        x0, x1 = _x_for_span(cell, start, end)
        cell.is_header = True
        marks.append(Column(kind, x0, x1, cell.y_center))

    for cell in cells:
        t = cell.text
        hundred_spans: List[Tuple[int, int]] = []
        for m in _HUNDRED_RE.finditer(t):
            add("hundred", m.start(), m.end(), cell)
            hundred_spans.append((m.start(), m.end()))
        if t.strip() in {"serving", "amount", "amount per serving"}:
            add("serving", 0, len(t), cell)
            continue
        if not _header_like(cell):
            continue
        for m in _SERVING_RE.finditer(t):
            if any(not (m.end() <= a or m.start() >= b) for a, b in hundred_spans):
                continue
            add("serving", m.start(), m.end(), cell)
        for m in _PAREN_SERVING_RE.finditer(t):
            add("serving", m.start(), m.end(), cell)
        if _PERCENT_HEADER_RE.search(t) and len(t) <= 32:
            add("percent", 0, len(t), cell)

    # Merge duplicate marks of the same kind whose x ranges overlap or nearly
    # touch (e.g. "(20g)" and "(20 g)").
    marks.sort(key=lambda c: (c.kind, c.x_min))
    merged: List[Column] = []
    for m in marks:
        if merged and merged[-1].kind == m.kind:
            prev = merged[-1]
            if m.x_min <= prev.x_max + 80:
                prev.x_max = max(prev.x_max, m.x_max)
                continue
        merged.append(Column(m.kind, m.x_min, m.x_max))

    # Keep only value-bearing columns; percent is useful for exclusion.
    merged.sort(key=lambda c: c.x_min)
    return merged


def _desired_kind(basis: str) -> str:
    if basis in ("per_100_g", "per_100_ml"):
        return "hundred"
    return "serving"


def _column_for(candidate: Candidate, columns: Sequence[Column],
                desired: str) -> Optional[str]:
    """Returns the column kind a candidate belongs to, or None if outside table."""
    if not columns:
        return None
    percent = [c for c in columns if c.kind == "percent"]
    for col in percent:
        if (col.x_min <= candidate.x_center <= col.x_max
                and candidate.y_center >= col.y_center - 60.0):
            return "percent"
    non_percent = [c for c in columns if c.kind != "percent"]
    if not non_percent:
        return None
    matching = [c for c in non_percent if c.kind == desired]
    # If the panel has only one value column, allow values to its right (US
    # Nutrition Facts headers sit above the left-aligned label, values right).
    if len(non_percent) == 1:
        col = non_percent[0]
        if candidate.x_center < col.x_min - 0.35 * (col.x_max - col.x_min):
            return None
        return col.kind
    pool = matching or non_percent
    # Prefer a strictly containing column; overlapping headers are common, so
    # break ties by the nearest column centre before allowing any padding.
    containing = [c for c in pool if c.x_min <= candidate.x_center <= c.x_max]
    if containing:
        return min(containing, key=lambda c: abs(c.center - candidate.x_center)).kind
    padded = [
        c for c in pool
        if c.x_min - 0.15 * (c.x_max - c.x_min) <= candidate.x_center
        <= c.x_max + 0.15 * (c.x_max - c.x_min)
    ]
    if padded:
        return min(padded, key=lambda c: abs(c.center - candidate.x_center)).kind
    nearest = min(pool, key=lambda c: abs(c.center - candidate.x_center))
    if abs(nearest.center - candidate.x_center) <= max(1.0, nearest.x_max - nearest.x_min):
        return nearest.kind
    return None


# ---------------------------------------------------------------------------
# Value selection
# ---------------------------------------------------------------------------

def _unit_ok(field_name: str, unit: Optional[str]) -> bool:
    if unit is None:
        return True
    if field_name in ENERGY_FIELDS:
        return unit in ({"kcal"} if field_name == "energy_kcal" else {"kj"})
    expected = DEFAULT_UNITS.get(field_name, "g")
    if expected == "g":
        return unit == "g"
    if expected == "mg":
        return unit in {"mg", "g"}
    if expected == "mcg":
        return unit in {"mcg", "mg"}
    return unit == expected


def _convert_value(field_name: str, value: float, unit: Optional[str]) -> Tuple[float, Optional[str]]:
    expected = DEFAULT_UNITS.get(field_name)
    if field_name in ENERGY_FIELDS or unit is None or expected is None:
        return value, unit
    if expected == "mg" and unit == "g":
        return value * 1000.0, "mg"
    if expected == "g" and unit == "mg":
        return value / 1000.0, "g"
    if expected == "mcg" and unit == "mg":
        return value * 1000.0, "mcg"
    return value, unit


def _nearest(cands: Sequence[Candidate], cell: Cell) -> Optional[Candidate]:
    if not cands:
        return None
    return min(
        cands,
        key=lambda c: (
            abs(c.y_center - cell.y_center),
            abs(c.x_center - cell.x_max),
            c.pos_start,
        ),
    )


def _cands_after_hit(cell: Cell, hit: FieldHit) -> List[Candidate]:
    later_hits = [h.start for h in cell.hits if h.start > hit.end]
    limit = min(later_hits) if later_hits else len(cell.text)
    return [
        c for c in cell.candidates
        if c.pos_start >= hit.end and c.pos_end <= limit and not c.has_percent
    ]


def _cands_before_hit(cell: Cell, hit: FieldHit) -> List[Candidate]:
    earlier_ends = [h.end for h in cell.hits if h.end <= hit.start]
    low = max(earlier_ends) if earlier_ends else 0
    return [
        c for c in cell.candidates
        if c.pos_start >= low and c.pos_end <= hit.start and not c.has_percent
    ]


def _nearby_cells(cell: Cell, cells: Sequence[Cell]) -> List[Cell]:
    out = []
    for other in cells:
        if other is cell or other.is_header:
            continue
        vertical_gap = abs(other.y_center - cell.y_center)
        overlap = min(cell.y_max, other.y_max) - max(cell.y_min, other.y_min)
        if vertical_gap <= 1.5 * max(cell.height, other.height) or (
            overlap > 0 and overlap >= 0.15 * min(cell.height, other.height)
        ):
            out.append(other)
    return out


def _select_from_hit(
    field_name: str,
    hit: FieldHit,
    cell: Cell,
    cells: Sequence[Cell],
    columns: Sequence[Column],
    desired: str,
    used: set,
) -> Optional[Tuple[Candidate, Cell, str]]:
    """Finds one value for a hit, preferring same-cell then nearby cells."""
    same = _cands_after_hit(cell, hit)
    if not same:
        same = _cands_before_hit(cell, hit)
    same = [c for c in same if _unit_ok(field_name, c.unit)]
    if columns and len(same) > 1:
        in_column = [c for c in same if _column_for(c, columns, desired) == desired]
        if in_column:
            same = in_column
    chosen = _nearest(same, cell)
    if chosen is not None:
        return chosen, cell, "cell"

    pool: List[Tuple[Candidate, Cell]] = []
    for other in _nearby_cells(cell, cells):
        if other.is_header:
            continue
        for cand in other.candidates:
            if cand.has_percent:
                continue
            if cand.x_center < hit.x_end - 0.20 * cell.width:
                continue
            if not _unit_ok(field_name, cand.unit):
                continue
            if columns and _column_for(cand, columns, desired) != desired:
                continue
            pool.append((cand, other))

    if not pool:
        return None
    # Prefer candidates carrying an explicit unit over bare numbers.
    with_unit = [(c, o) for c, o in pool if c.unit is not None]
    if with_unit:
        pool = with_unit
    chosen, owner = min(
        pool,
        key=lambda pair: (
            abs(pair[0].y_center - cell.y_center),
            abs(pair[0].x_center - hit.x_end),
        ),
    )
    return chosen, owner, "nearby_cell"


def _energy_values(
    hits: Sequence[FieldHit],
    cells: Sequence[Cell],
    columns: Sequence[Column],
    desired: str,
) -> Dict[str, Candidate]:
    value_columns = [c for c in columns if c.kind != "percent"]
    pool: List[Tuple[Candidate, Cell]] = []
    for hit_cell in cells:
        hit = next((h for h in hit_cell.hits if h.field == "energy_kcal"), None)
        if hit is None:
            continue
        candidates = [
            c for c in hit_cell.candidates if not c.has_percent
        ]
        for cand in candidates:
            if cand.pos_start < hit.start and cand.pos_end > hit.start:
                continue
            pool.append((cand, hit_cell))
        for other in _nearby_cells(hit_cell, cells):
            if other.is_header:
                continue
            for cand in other.candidates:
                if cand.has_percent:
                    continue
                if cand.x_center < hit.x_end - 0.25 * hit_cell.width:
                    continue
                if value_columns and _column_for(cand, value_columns, desired) != desired:
                    continue
                pool.append((cand, other))

    if not pool:
        return {}

    # Deduplicate identical value/unit pairs (same OCR cell may be visited twice).
    unique: Dict[Tuple[float, Optional[str]], Tuple[Candidate, Cell]] = {}
    for cand, owner in pool:
        key = (round(cand.value, 4), cand.unit)
        if key not in unique:
            unique[key] = (cand, owner)

    with_unit = [v for v in unique.values() if v[0].unit is not None]
    bare = [v for v in unique.values() if v[0].unit is None]
    source = with_unit or bare

    by_field: Dict[str, Candidate] = {}

    wanted = [c for c in value_columns if c.kind == desired]

    def inside_declared_column(cand: Candidate) -> int:
        if not wanted:
            return 0 if not value_columns else 1
        return 0 if any(c.x_min <= cand.x_center <= c.x_max for c in wanted) else 1

    def choose(field_name: str, allowed_units: Tuple[Optional[str], ...]) -> None:
        choices = [(c, o) for c, o in source if c.unit in allowed_units]
        if not choices:
            return
        # Prefer a value strictly inside the declared column, then the number
        # closest vertically to an energy label.
        labels = [c for c in cells if any(h.field == "energy_kcal" for h in c.hits)]
        chosen = min(
            choices,
            key=lambda pair: (
                inside_declared_column(pair[0]),
                min((abs(pair[0].y_center - a.y_center) for a in labels), default=0),
                pair[0].x_center,
            ),
        )[0]
        by_field[field_name] = chosen

    choose("energy_kj", ("kj",))
    choose("energy_kcal", ("kcal",))
    if "energy_kcal" not in by_field and bare:
        # A single bare energy number is allocated by magnitude.  This is a
        # documented heuristic: <= 900 is far more likely kcal than kJ.
        cand = min(bare, key=lambda p: p[0].x_center)[0]
        if cand.value <= 900:
            by_field["energy_kcal"] = cand
        else:
            by_field["energy_kj"] = cand
    return by_field


def _energy_without_label(
    cells: Sequence[Cell],
    columns: Sequence[Column],
    desired: str,
) -> Dict[str, Tuple[Candidate, Cell]]:
    """Last-resort energy recovery when the "Energy" label itself was lost.

    Only unit-bearing kcal/kJ values inside the declared basis column are
    eligible; bare numbers are never promoted to energy.
    """
    value_columns = [c for c in columns if c.kind != "percent"]
    wanted = [c for c in value_columns if c.kind == desired]
    pool: List[Tuple[Candidate, Cell]] = []
    for cell in cells:
        if cell.is_header:
            continue
        for cand in cell.candidates:
            if cand.has_percent or cand.unit not in {"kcal", "kj"}:
                continue
            if value_columns and _column_for(cand, value_columns, desired) != desired:
                continue
            pool.append((cand, cell))
    if not pool:
        return {}

    def inside(cand: Candidate) -> int:
        if not wanted:
            return 0 if not value_columns else 1
        return 0 if any(c.x_min <= cand.x_center <= c.x_max for c in wanted) else 1

    out: Dict[str, Tuple[Candidate, Cell]] = {}
    for field_name, unit in (("energy_kcal", "kcal"), ("energy_kj", "kj")):
        choices = [(c, o) for c, o in pool if c.unit == unit]
        if choices:
            out[field_name] = min(
                choices,
                key=lambda p: (inside(p[0]), p[0].y_center, p[0].x_center),
            )
    return out


def _row_align(
    cells: Sequence[Cell],
    columns: Sequence[Column],
    desired: str,
) -> Dict[str, Tuple[Candidate, Cell, float]]:
    """Monotonic row alignment of nutrient labels to numeric value cells.

    Sorting labels and values by their vertical position and aligning them in
    order is far more robust than choosing the nearest number independently:
    OCR often drops one label (or one value), and independent nearest-neighbour
    selection then shifts every following row by one.  The dynamic program
    allows either sequence to skip an item, but penalises skips so that a close
    in-order match wins.
    """
    footnote_y: Optional[float] = None
    table_top_y: Optional[float] = None
    for cell in cells:
        if any(marker in cell.text for marker in (
            "calorie diet", "daily values may be higher",
            "percent daily values are based",
        )):
            footnote_y = cell.y_min if footnote_y is None else min(footnote_y, cell.y_min)
        if any(marker in cell.text for marker in (
            "nutrition", "nutritional", "nahrwert", "næring",
            "informations nutritionnelles",
        )):
            table_top_y = cell.y_min if table_top_y is None else min(table_top_y, cell.y_min)

    def in_footnote(cell: Cell) -> bool:
        return footnote_y is not None and cell.y_min >= footnote_y

    def in_prose(cell: Cell) -> bool:
        t = cell.text
        if any(marker in t for marker in (
            "ingredient", "allergen", "may contain", "contains wheat",
        )):
            return True
        return table_top_y is not None and cell.y_max < table_top_y - 5.0

    mass_units = {"g", "mg", "mcg"}
    non_percent_columns = [c for c in columns if c.kind != "percent"]
    value_columns = [c for c in columns if c.kind != "percent"]
    column_support: Dict[int, int] = {id(c): 0 for c in value_columns}
    hit_support: Dict[int, int] = {id(c): 0 for c in value_columns}
    for cell in cells:
        for cand in cell.candidates:
            if cand.unit not in {"g", "mg", "mcg", "kcal", "kj"}:
                continue
            for col in value_columns:
                if col.x_min <= cand.x_center <= col.x_max:
                    column_support[id(col)] += 1
        cell_center = (cell.x_min + cell.x_max) / 2.0
        for hit in cell.hits:
            for col in value_columns:
                if col.x_min <= cell_center <= col.x_max:
                    hit_support[id(col)] += 1
    supported_columns = [c for c in value_columns if hit_support[id(c)] > 0]
    if not supported_columns:
        supported_columns = [c for c in value_columns if column_support[id(c)] > 0]
    label_zone_max = (
        max(c.x_max for c in supported_columns)
        if supported_columns
        else max((c.x_max for c in value_columns), default=max((c.x_max for c in cells), default=0.0))
    )

    def in_sidebar(cell: Cell) -> bool:
        return bool(columns) and cell.x_min > label_zone_max + 5.0

    candidates: List[Tuple[Candidate, Cell]] = []
    for cell in cells:
        if cell.is_header or in_footnote(cell) or in_sidebar(cell) or in_prose(cell):
            continue
        for cand in cell.candidates:
            if cand.has_percent:
                continue
            if cand.unit is not None and cand.unit not in mass_units:
                continue
            limit = {"g": 300.0, "mg": 100000.0, "mcg": 1000000.0}.get(
                cand.unit or "bare", 5000.0
            )
            if cand.value > limit:
                continue
            if columns and _column_for(cand, columns, desired) != desired:
                # A label and its value in one wide OCR cell can sit outside
                # a column detected from a separate header cell.
                if not cell.hits:
                    continue
            # Bare numbers are only used when the candidate is geometrically
            # inside the declared value column; prose numbers are not.
            if cand.unit is None and not columns:
                continue
            candidates.append((cand, cell))
    candidates.sort(key=lambda p: (p[0].y_center, p[0].x_center))

    hits: List[Tuple[Cell, FieldHit]] = []
    for cell in cells:
        if cell.is_header or in_footnote(cell) or in_sidebar(cell) or in_prose(cell):
            continue
        for hit in cell.hits:
            if hit.field in ENERGY_FIELDS:
                continue
            hits.append((cell, hit))
    hits.sort(key=lambda p: (p[0].y_center, p[1].start))

    n, m = len(hits), len(candidates)
    if not n or not m:
        return {}

    skip_hit = 3.0
    skip_cand = 0.45
    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    back = [[0] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(1, n + 1):
        dp[i][0] = dp[i - 1][0] + skip_hit
        back[i][0] = 2
    for j in range(1, m + 1):
        dp[0][j] = dp[0][j - 1] + skip_cand
        back[0][j] = 3

    for i in range(1, n + 1):
        cell, hit = hits[i - 1]
        for j in range(1, m + 1):
            cand, cand_cell = candidates[j - 1]
            best = dp[i - 1][j] + skip_hit
            op = 2
            if dp[i][j - 1] + skip_cand < best:
                best = dp[i][j - 1] + skip_cand
                op = 3
            dy = abs(cell.y_center - cand_cell.y_center)
            field_limit = FIELD_MAX_VALUES.get(hit.field, float("inf"))
            if dy <= 320.0 and cand.value <= field_limit:
                penalty = 0.0 if _unit_ok(hit.field, cand.unit) else 2.5
                if cand.unit is None:
                    penalty += 0.35
                match = dp[i - 1][j - 1] + (dy / 100.0) ** 2 + penalty
                if match < best:
                    best = match
                    op = 1
            dp[i][j] = best
            back[i][j] = op

    matches: List[Tuple[float, str, Candidate, Cell]] = []
    i, j = n, m
    while i > 0 or j > 0:
        op = back[i][j]
        if op == 1:
            cell, hit = hits[i - 1]
            cand, cand_cell = candidates[j - 1]
            cost = (abs(cell.y_center - cand_cell.y_center) / 100.0) ** 2
            matches.append((cost, hit.field, cand, cand_cell))
            i -= 1
            j -= 1
        elif op == 2:
            i -= 1
        else:
            j -= 1

    out: Dict[str, Tuple[Candidate, Cell, float]] = {}
    # Backtrace is bottom-to-top; prefer the topmost row when a label appears
    # twice (for example a "Total Fat" row and a footnote reference row).
    for cost, field_name, cand, owner in reversed(matches):
        if cost > 3.0 or field_name in out:
            continue
        out[field_name] = (cand, owner, cost)
    return out


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def _bbox_extent(box: Sequence[Sequence[float]]) -> Optional[Tuple[float, float, float, float]]:
    if not box or len(box) < 3:
        return None
    try:
        xs = [float(p[0]) for p in box]
        ys = [float(p[1]) for p in box]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _make_cells(ocr_records: Sequence[Dict[str, Any]]) -> List[Cell]:
    cells: List[Cell] = []
    for rec in ocr_records:
        raw = str(rec.get("text", "")).strip()
        if not raw:
            continue
        box = rec.get("bounding_box") or rec.get("box") or []
        ext = _bbox_extent(box)
        if ext is None:
            continue
        x0, x1, y0, y1 = ext
        normalized = normalize_ocr_text(raw)
        cell = Cell(
            text=normalized,
            raw_text=raw,
            confidence=float(rec.get("confidence") or 0.0),
            x_min=x0, x_max=x1, y_min=y0, y_max=y1,
        )
        cell.candidates = extract_candidates(cell)
        cell.hits = find_field_hits(cell)
        cells.append(cell)
    return cells


def extract_structured(ocr_records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Extracts nutrition fields from OCR records carrying bounding boxes."""
    cells = _make_cells(ocr_records)
    text_all = " ".join(c.text for c in cells)

    # Reuse the settled basis/serving-size detector.
    from food_engine.nutrition_extraction.extractor import NutritionExtractor
    basis, serving_raw, serving_g, serving_ml = NutritionExtractor._detect_basis_and_serving(text_all)
    columns = detect_columns(cells)
    desired = _desired_kind(basis)

    chosen: Dict[str, Tuple[Candidate, Cell, str]] = {}
    used_positions: set = set()

    # Energy is resolved as a unit (kJ/kcal) rather than a generic number.
    energy = _energy_values(
        [h for c in cells for h in c.hits if h.field == "energy_kcal"],
        cells, columns, desired,
    )
    if "energy_kcal" not in energy and "energy_kj" not in energy:
        for field_name, (cand, owner) in _energy_without_label(
            cells, columns, desired
        ).items():
            energy[field_name] = cand
            chosen[field_name] = (cand, owner, "energy_unit")
    for field_name, cand in energy.items():
        owner = next((c for c in cells if cand in c.candidates), cells[0] if cells else None)
        if owner is not None:
            chosen[field_name] = (cand, owner, "energy_row")
            used_positions.add((id(owner), cand.pos_start))

    aligned = _row_align(cells, columns, desired)
    for field_name, (cand, owner, _cost) in aligned.items():
        chosen[field_name] = (cand, owner, "row_alignment")

    nutrients: Dict[str, Dict[str, Any]] = {}
    missing_fields: List[str] = []
    conflicting_fields: List[str] = []

    for field_name in list(DEFAULT_UNITS):
        unit = DEFAULT_UNITS[field_name]
        chosen_value = None
        if field_name in chosen:
            cand, owner, method = chosen[field_name]
            value, actual_unit = _convert_value(field_name, cand.value, cand.unit)
            if value <= FIELD_MAX_VALUES.get(field_name, float("inf")):
                chosen_value = {
                    "value": round(value, 6),
                    "unit": unit,
                    "status": "declared",
                    "confidence": round(owner.confidence, 4) if owner.confidence else None,
                    "match_method": method,
                    "source_unit": actual_unit,
                    "upper_bound": cand.upper_bound,
                }
        if chosen_value is not None:
            nutrients[field_name] = chosen_value
        else:
            nutrients[field_name] = {
                "value": None,
                "unit": unit,
                "status": "missing",
                "confidence": None,
            }
            if field_name in {
                "energy_kcal", "protein_g", "carbohydrates_g", "total_fat_g",
                "sodium_mg", "salt_g",
            }:
                missing_fields.append(field_name)

    # Sodium <-> salt consistency, identical to the string extractor.
    if nutrients["sodium_mg"]["status"] == "missing" and nutrients["salt_g"]["status"] == "declared":
        salt_val = nutrients["salt_g"]["value"]
        if salt_val is not None:
            nutrients["sodium_mg"] = {
                "value": round(salt_val * 400.0, 2),
                "unit": "mg",
                "status": "calculated",
                "confidence": 0.90,
            }
            if "sodium_mg" in missing_fields:
                missing_fields.remove("sodium_mg")
    elif nutrients["salt_g"]["status"] == "missing" and nutrients["sodium_mg"]["status"] == "declared":
        sod_val = nutrients["sodium_mg"]["value"]
        if sod_val is not None:
            nutrients["salt_g"] = {
                "value": round((sod_val / 1000.0) * 2.5, 3),
                "unit": "g",
                "status": "calculated",
                "confidence": 0.90,
            }
            if "salt_g" in missing_fields:
                missing_fields.remove("salt_g")

    # Report ambiguity when several distinct values were available in the
    # declared column for the same field.
    for field_name, (cand, owner, method) in chosen.items():
        if method == "energy_row":
            continue
        same_column = []
        for c in cells:
            for other in c.candidates:
                if other.has_percent:
                    continue
                if not _unit_ok(field_name, other.unit):
                    continue
                kind = _column_for(other, columns, desired)
                if columns and kind is not None and kind != desired:
                    continue
                same_column.append(other.value)
        distinct = {round(v, 4) for v in same_column}
        if len(distinct) > 1:
            conflicting_fields.append(field_name)

    return {
        "basis": basis,
        "serving_size_raw": serving_raw,
        "serving_size_g": serving_g,
        "serving_size_ml": serving_ml,
        "nutrients": nutrients,
        "missing_fields": missing_fields,
        "conflicting_fields": sorted(set(conflicting_fields)),
        "column_layout": [
            {"kind": c.kind, "x_min": round(c.x_min, 1), "x_max": round(c.x_max, 1)}
            for c in columns
        ],
        "normalized_cells": [
            {"text": c.text, "confidence": c.confidence,
             "x_min": round(c.x_min, 1), "x_max": round(c.x_max, 1),
             "y_min": round(c.y_min, 1), "y_max": round(c.y_max, 1)}
            for c in cells
        ],
    }
