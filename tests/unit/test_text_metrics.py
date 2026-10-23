"""Tests for the trusted text-metrics module (hand-verified distances)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from food_engine.evaluate.text_metrics import (  # noqa: E402
    cer,
    coverage_cer,
    coverage_wer,
    levenshtein,
    normalise_for_cer,
    wer,
    word_tokens,
)


class TestLevenshtein:
    def test_identical(self):
        assert levenshtein("kitten", "kitten") == 0

    def test_generalised_costs_match_default(self):
        # Default costs reproduce the classic hand-verified values
        assert levenshtein("kitten", "sitting", 1, 1) == 3
        assert levenshtein("flaw", "lawn", 1, 1) == 2

    def test_kitten_sitting(self):
        # Classic hand-verified example: 3 substitutions
        assert levenshtein("kitten", "sitting") == 3

    def test_flaw_lawn(self):
        # Classic hand-verified example: 2 edits
        assert levenshtein("flaw", "lawn") == 2

    def test_empty_vs_nonempty(self):
        assert levenshtein("", "abc") == 3
        assert levenshtein("abc", "") == 3
        assert levenshtein("", "") == 0

    def test_symmetry(self):
        a, b = "nutrition", "nutritionnnal"
        assert levenshtein(a, b) == levenshtein(b, a)

    def test_numeric_garbage(self):
        # Hand-check: sodium 1620mn vs sodium 160mg
        d = levenshtein("sodium 1620mn", "sodium 160mg")
        assert d == 2  # delete '2'; y->g substitution

    def test_token_level(self):
        # Words: reference [a, b, c] vs hypothesis [a, x, c] = 1 substitution
        assert levenshtein(["a", "b", "c"], ["a", "x", "c"]) == 1


class TestCER:
    def test_zero_when_identical(self):
        assert cer("Energy 180 kJ / 42 kcal", "Energy 180 kJ / 42 kcal") == 0.0

    def test_empty_reference_is_zero(self):
        assert cer("", "anything") == 0.0

    def test_known_fraction(self):
        # 1 edit out of 6 reference chars
        assert abs(cer("energy", "energe") - 1 / 6) < 1e-9

    def test_casefold_and_whitespace_collapsing(self):
        assert cer("Energy  180 kJ", "ENERGY 180 kJ") == 0.0


class TestWER:
    def test_zero_when_identical(self):
        assert wer("Energy 180 kJ / 42 kcal", "Energy 180 kJ / 42 kcal") == 0.0

    def test_single_substitution(self):
        # 5 ref words, 1 wrong -> 0.2
        assert abs(wer("Total Fat 10g Sodium 140mg", "Total Fate 10g Sodium 140mg") - 0.2) < 1e-9

    def test_empty_reference_is_zero(self):
        assert wer("", "words here") == 0.0

    def test_tokenisation_collapses_case(self):
        assert word_tokens("Nutrition Facts") == ["nutrition", "facts"]
        assert wer("Nutrition Facts", "NUTRITION  facts") == 0.0


class TestCoverageMetrics:
    def test_extra_hypothesis_text_is_free(self):
        # Standard CER punishes unrelated extra text; coverage does not
        ref = "Sodium 400 mg"
        hyp = "Marketing paragraph Sodium 400 mg"
        assert coverage_cer(ref, hyp) == 0.0
        assert coverage_wer(ref, hyp) == 0.0
        assert cer(ref, hyp) > 0

    def test_misses_still_count(self):
        ref = "Sodium 400 mg"
        hyp = "Sodium 400"  # missing ' mg': 3 deletions (space, m, g)
        assert abs(coverage_cer(ref, hyp) - 3 / len(normalise_for_cer(ref))) < 1e-9

    def test_substitutions_still_count(self):
        ref = "Sodium 400 mg"
        hyp = "Sodlum 7900 mg"
        assert coverage_cer(ref, hyp) > 0


class TestNormalisation:
    def test_nfkc_folds_accents_and_fullwidth(self):
        # Full-width digits normalize to ASCII; accented e folds via casefold
        assert normalise_for_cer("Ｅｎｅｒｇｙ") == normalise_for_cer("Energy").replace("é", "e")

    def test_typographic_apostrophe(self):
        assert normalise_for_cer("l’avoine") == normalise_for_cer("l'avoine")
