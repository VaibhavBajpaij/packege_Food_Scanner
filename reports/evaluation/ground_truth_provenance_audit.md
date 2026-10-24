# Ground-Truth Provenance and Integrity Audit

- **Audit Date**: 2026-10-24
- **Engine Version**: `0.2.0` (Phase 4 Benchmark Integrity)
- **Status**: Completed Independent Provenance Audit

---

## 1. Executive Summary

This audit establishes the empirical provenance, historical evolution, and integrity limitations of all ground-truth datasets used to evaluate the Food Intelligence Engine.

### Core Provenance Findings:
1. **The historical v1 ground truth (`ground_truth.json`) was NOT transcribed from images**: It was programmatically scraped from Open Food Facts API database fields. This caused 12 of the 22 samples to have incorrect, rounded, basis-mismatched, or entirely non-existent nutritional data.
2. **The v2 ground truth (`ground_truth_v2.json`) resolved transcription errors but suffers from development contamination**: Transcription corrections were made concurrently with OCR debugging, and extraction rules in `src/food_engine/nutrition_extraction/structured.py` were tailored to match OCR character artifacts found on the test images.
3. **The existing "held-out" split is NOT pristine**: The 7 images in the held-out split were inspected, debugged, and used to iterate extraction logic during development. All 22 existing images must be treated as a **Development Set**, never as an independent validation or generalization holdout.

---

## 2. Chronological Timeline of Ground-Truth Evolution

```
[Phase 1: Synthetic Fixtures]
  - 2 PIL-generated PNGs (biscuit & juice).
  - Ground truth matched embedded tEXt PNG metadata.
  - Zero pixel OCR; 100% circular evaluation.
           │
           ▼
[Phase 2: API Scraping for Real Photos (v1)]
  - 22 real packaged food photos downloaded from Open Food Facts API.
  - scripts/download_real_test_photos.py copied OFF API database fields (`prod.get("nutriments")`).
  - No visual image transcription performed.
  - Result: 12/22 samples corrupted with database mismatches.
           │
           ▼
[Phase 3: Visual Re-Transcription & Alignment (v2)]
  - Discrepancies uncovered during audit.
  - tests/fixtures/real_photos/ground_truth_v2.json created by visual pixel inspection.
  - Split defined: 15 dev, 7 held-out.
  - BUT: Extraction rules (structured.py) iteratively modified using errors from all 22 photos.
           │
           ▼
[Phase 4: Benchmark Integrity & Holdout Protocol]
  - Transparent accounting of TP, FP, FN.
  - Strict classification of all 22 photos as Development Set.
  - Definition of new, pristine Independent Holdout Protocol.
```

---

## 3. Detailed Provenance Analysis by Phase

### 3.1 Phase 1: Synthetic Label Fixtures
- **Files**: `tests/fixtures/sample_biscuit_packet.png`, `tests/fixtures/sample_juice_bottle.png`
- **Method**: Generated via PIL canvas drawing.
- **Defect**: Original implementation wrote ground-truth strings into PNG `tEXt` metadata chunks. The historical `OCREngine` read `img.info["ocr_text"]`, bypassing all image pixels. The reported "100% accuracy" was a tautological artifact.

### 3.2 Phase 2: Open Food Facts Database Scraping (`ground_truth.json`)
- **File**: `tests/fixtures/real_photos/ground_truth.json`
- **Script**: `scripts/download_real_test_photos.py` lines 96–129
- **Method**: The script fetched product JSON from `https://world.openfoodfacts.org/api/v2/product/{code}.json` and directly populated `nutrients_per_100g` from `prod.get("nutriments")`.
- **Verified Discrepancies**:
  - `real_photo_13` (Nutella): Image is a photograph of the front label only. The OFF database record contained complete nutrition facts (539 kcal, 30.9g fat, 56.3g sugars, etc.), which were added to the ground truth despite being completely absent from the photo.
  - `real_photo_15` (Monster Energy): Front can photo only. Assigned 47 kcal, 12g carbohydrates, 11g sugars from the API.
  - `real_photo_09` (Sunfeast Yippee Noodles): Photographed panel declares **111 kcal, 19.8g fat** per 100g *prepared*. The OFF database contained **466 kcal, 19.6g fat** per 100g *dry noodle cake*.
  - `real_photo_08` (Thai Peanut Noodle Kit): Photo declares per 1 cup prepared (**310 kcal, 629 mg sodium**). Database recorded **780 mg sodium** for 1/3 dry kit.
  - `real_photo_11` (Heinz Baked Beanz): Photographed container is a Czech/Hungarian multilingual tin (`Energie 339 kJ / 81 kcal`). Ground truth transcribed an English panel that does not exist on the container.
  - `real_photo_12` (Chicken Tortilla Soup): Photo shows 27g serving (90 kcal, 420mg sodium). Database had 30g serving (100 kcal, 720mg sodium).
  - `real_photo_16` (Opti-Meal Protein Shake): Photo shows 190 kcal, 6g fat, 230mg sodium. Database had 160 kcal, 2.5g fat, 240mg sodium.
  - `real_photo_17` (Silk Almondmilk): Photo shows 80 kcal, 2g fat, 130mg sodium. Database had 60 kcal, 2.5g fat, 150mg sodium.

### 3.3 Phase 3: Manual Pixel Re-Transcription (`ground_truth_v2.json`)
- **File**: `tests/fixtures/real_photos/ground_truth_v2.json`
- **Method**: The author zoomed into image pixels and manually transcribed the visible text and declared nutritional panels.
- **Improvements**:
  - Marked `real_photo_13` and `real_photo_15` as `verification_status: "panel_not_legible"`, `serving_basis: "front_only"`, and `declared_nutrients_on_label: {}`.
  - Transcribed verbatim visible values for prepared noodle products and foreign-language panels.
  - Recorded 135 valid non-null declared nutrient targets across 20 legible photos (118 core nutrient targets).

---

## 4. Why the Existing "Held-Out" Split is Compromised

In `tests/fixtures/real_photos/ground_truth_v2.json` lines 17–21, a split was defined:
- **`held_out`**: `real_photo_01`, `real_photo_07`, `real_photo_09`, `real_photo_11`, `real_photo_16`, `real_photo_21`, `real_photo_22` (7 images)
- **`dev`**: Remaining 15 images

### Evidence of Contamination:
1. **Targeted Code Modifications for Held-Out Images**:
   In `src/food_engine/nutrition_extraction/structured.py` lines 59–62, the `_WORD_CORRECTIONS` table includes:
   ```python
   (r"\batieres\b", "matieres"),      # Matches "Matieres grasses" on real_photo_01
   (r"\biont\b", "dont"),              # Matches "dont acides gras" on real_photo_01
   (r"\bdudides\b", "glucides"),       # Matches "Glucides" on real_photo_01
   (r"\bbres\b", "fibres"),            # Matches "Fibres alimentaires" on real_photo_01
   ```
   `real_photo_01` (Prince Chocolate Biscuits) is explicitly part of the **`held_out`** split. Hardcoding dictionary corrections for OCR mistakes that specifically occur in `real_photo_01` constitutes direct train/test leakage.
2. **Interactive Tuning & Image Inspection**:
   Scripts `_tmp_ocr_variants.py`, `_tmp_ocr_scale.py`, and `_tmp_eval_ocr.py` repeatedly tested parameters on `real_photo_11` and `real_photo_19` to diagnose OCR misses.
3. **Conclusion**:
   No performance metric calculated on these 7 images can be honestly claimed as an independent validation result. The entire 22-image collection must be designated as a **Development Benchmark**.

---

## 5. Dataset Preservation and Audit Guarantee

1. **Original Files Preserved**:
   - `tests/fixtures/real_photos/ground_truth.json` remains untouched as evidence of Phase 2 state.
   - `tests/fixtures/real_photos/ground_truth_v2.json` remains untouched as the active Phase 3/4 development ground truth.
2. **Audit Rule**:
   Future evaluations must never alter `ground_truth_v2.json` to make the engine's extraction appear more accurate. Any genuine typo correction in ground truth must be committed with SHA-256 hashes and visual photographic evidence.
