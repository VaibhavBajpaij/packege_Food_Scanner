"""Bounding-box row reassembly for fragmented OCR outputs.

Text detection frequently splits one printed label row into fragments, e.g.
"Information" / "nutritionnelle" / "100g" or "Energy" / "1962 kJ / 467 kcal".
Downstream regex-based nutrition parsing then fails on name/value separation.
This module merges detected line boxes that share (approximately) the same
print row, ordered left-to-right, into single "rows" of text.

The merge is purely geometric (vertical overlap of boxes); it does not infer
missing values or reorder column semantics.
"""

from typing import Any, Dict, List, Sequence


def _bbox_extent(box: Sequence[Sequence[float]]) -> Dict[str, float]:
    """Computes the axis-aligned extent (ymin/ymax/xmin/xmax) of a 4-point polygon."""
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    high = float(max(ys))
    low = float(min(ys))
    return {"xmin": float(min(xs)), "xmax": float(max(xs)), "ymin": low, "ymax": high, "yc": (low + high) / 2.0}


def row_group_lines(ocr_lines: Sequence[Dict[str, Any]], overlap_fraction: float = 0.4) -> List[Dict[str, Any]]:
    """Groups OCR line dicts (with 'text' and 'bounding_box') into print rows.

    Two boxes belong to the same row when their vertical ranges overlap by at
    least `overlap_fraction` of the *smaller* box height (anchor overlap).
    Returns rows joined left-to-right. Boxes without bounding boxes are passed
    through as single-line rows, preserving order.
    """
    items: List[Dict[str, Any]] = []
    for idx, line in enumerate(ocr_lines):
        text = str(line.get("text", "")).strip()
        if not text:
            continue
        box = line.get("bounding_box") or []
        if len(box) >= 3 and all(p and len(p) >= 2 for p in box):
            items.append({"idx": idx, "text": text, **_bbox_extent(box)})
        else:
            items.append({"idx": idx, "text": text, "no_box": True})

    boxed = [it for it in items if not it.get("no_box")]
    boxed.sort(key=lambda it: (it["ymin"], it["xmin"]))

    groups: List[List[Dict[str, Any]]] = []
    for it in boxed:
        if not groups or not _overlaps(groups[-1], it, overlap_fraction):
            groups.append([it])
        else:
            groups[-1].append(it)

    rows: List[Dict[str, Any]] = []
    for g in groups:
        g.sort(key=lambda it: it["xmin"])
        ymin = min(it["ymin"] for it in g)
        ymax = max(it["ymax"] for it in g)
        rows.append({
            "text": " ".join(it["text"] for it in g),
            "x_min": min(it["xmin"] for it in g),
            "x_max": max(it["xmax"] for it in g),
            "y_min": ymin,
            "y_max": ymax,
            "member_indices": [it["idx"] for it in g],
        })

    unboxed_rows = [
        {"text": it["text"], "member_indices": [it["idx"]]}
        for it in items
        if it.get("no_box")
    ]
    # Unboxed lines cannot be placed geometrically and are appended in source
    # order after the assembled boxed rows (documented limitation).
    return rows + unboxed_rows


def _overlaps(current_group: List[Dict[str, Any]], candidate: Dict[str, Any], overlap_fraction: float) -> bool:
    """Checks the candidate against the group's combined vertical range."""
    g_ymin = min(it["ymin"] for it in current_group)
    g_ymax = max(it["ymax"] for it in current_group)
    c = candidate
    inter = min(g_ymax, c["ymax"]) - max(g_ymin, c["ymin"])
    if inter <= 0:
        return False
    smaller_height = max(0.0, c["ymax"] - c["ymin"])
    if smaller_height <= 0:
        return False
    return inter >= overlap_fraction * smaller_height
