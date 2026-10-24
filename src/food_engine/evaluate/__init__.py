"""Evaluation and benchmark scoring package for Food Intelligence Engine."""

from food_engine.evaluate.benchmark_scorer import (
    CANONICAL_NUTRIENT_MAP,
    CORE_NUTRIENTS,
    aggregate_benchmark,
    check_value_match,
    normalize_basis,
    partition_predicted_nutrients,
    score_sample,
)
from food_engine.evaluate.text_metrics import (
    cer,
    coverage_cer,
    coverage_wer,
    levenshtein,
    normalise_for_cer,
    panel_only_ocr_text,
    wer,
    word_tokens,
)

__all__ = [
    "CANONICAL_NUTRIENT_MAP",
    "CORE_NUTRIENTS",
    "normalize_basis",
    "check_value_match",
    "partition_predicted_nutrients",
    "score_sample",
    "aggregate_benchmark",
    "levenshtein",
    "normalise_for_cer",
    "cer",
    "coverage_cer",
    "word_tokens",
    "wer",
    "coverage_wer",
    "panel_only_ocr_text",
]
