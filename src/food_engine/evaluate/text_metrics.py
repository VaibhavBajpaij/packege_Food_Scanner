"""Trusted, dependency-free character/word error-rate metrics.

Implemented from the reference definitions (Levenshtein edit distance using the
standard two-row dynamic-programming recurrence) and covered by unit tests with
hand-verified distances in tests/unit/test_text_metrics.py. Used for the
independent recomputation of benchmark CER/WER in Phase 3.
"""

from typing import List, Sequence


def levenshtein(
    a: Sequence,
    b: Sequence,
    insertion_cost: int = 1,
    deletion_cost: int = 1,
) -> int:
    """Levenshtein edit distance with configurable insert/delete costs.

    ``deletion_cost`` applies to skipping a character of the first sequence
    (the reference when called as ``(ref, hyp)``); ``insertion_cost`` applies
    to skipping a character of the second sequence (extra hypothesis
    material). With ``insertion_cost=0`` this yields a *coverage* distance:
    only reference characters that were missed (deletions) or mis-recognised
    (substitutions) count; unrelated extra hypothesis text is free. This is
    used to measure recognition recall on whole-package OCR where the
    hypothesis legitimately contains text far outside the transcribed panel.
    """
    if not b:
        return len(a) * deletion_cost
    prev = [j * insertion_cost for j in range(len(b) + 1)]
    for i, x in enumerate(a):
        # D[i+1][0] = cost of deleting the first i+1 characters of a
        curr = [(i + 1) * deletion_cost]
        for j, y in enumerate(b):
            curr.append(
                min(
                    prev[j + 1] + deletion_cost,
                    curr[j] + insertion_cost,
                    prev[j] + (x != y),
                )
            )
        prev = curr
    return prev[-1]


def normalise_for_cer(s: str) -> str:
    """NFKC-normalise, casefold, collapse whitespace, keep punctuation/units.

    Unicode-aware: e.g. typographic apostrophes and accented letters are
    normalised so that identical handwriting/print differences are not
    counted as errors.
    """
    import unicodedata

    s = unicodedata.normalize("NFKC", s)
    # NFKC does not fold typographic quotes; map the common ones explicitly
    for wrong, right in (("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"')):
        s = s.replace(wrong, right)
    s = s.casefold()
    s = " ".join(s.split())
    return s.strip()


def cer(reference: str, hypothesis: str) -> float:
    """Character error rate = edits(ref, hyp) / len(reference). Empty ref -> 0."""
    ref = normalise_for_cer(reference)
    hyp = normalise_for_cer(hypothesis)
    if not ref:
        return 0.0
    return levenshtein(ref, hyp) / len(ref)


def coverage_cer(reference: str, hypothesis: str) -> float:
    """CER with insertion edits free (misses + substitutions only).

    Measures how much of the reference the OCR actually recovered, ignoring
    spurious text outside the transcribed panel (whole-photo OCR output).
    """
    ref = normalise_for_cer(reference)
    hyp = normalise_for_cer(hypothesis)
    if not ref:
        return 0.0
    return levenshtein(ref, hyp, insertion_cost=0) / len(ref)


def word_tokens(s: str) -> List[str]:
    """Casefolded whitespace tokens after NFKC normalisation."""
    return normalise_for_cer(s).split()


def wer(reference: str, hypothesis: str) -> float:
    """Word error rate = token-level Levenshtein / number of reference tokens."""
    ref_tokens = word_tokens(reference)
    hyp_tokens = word_tokens(hypothesis)
    if not ref_tokens:
        return 0.0
    return levenshtein(ref_tokens, hyp_tokens) / len(ref_tokens)


def coverage_wer(reference: str, hypothesis: str) -> float:
    """WER with insertion edits free (missed + substituted words only)."""
    ref_tokens = word_tokens(reference)
    hyp_tokens = word_tokens(hypothesis)
    if not ref_tokens:
        return 0.0
    return levenshtein(ref_tokens, hyp_tokens, insertion_cost=0) / len(ref_tokens)


def panel_only_ocr_text(ocr_lines: Sequence[str], y_min: float = 0.0) -> str:
    """Joins OCR lines the way the reference is transcribed (line-joined)."""
    import re

    cleaned = []
    for line in ocr_lines:
        t = re.sub(r"\s+", " ", str(line)).strip()
        if t:
            cleaned.append(t)
    return "\n".join(cleaned)
