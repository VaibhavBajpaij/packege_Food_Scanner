# Food Intelligence Engine — Phase 7 Verified Benchmark Report

- **Evaluation Date**: `2026-10-24T14:49:03.516708`
- **Benchmark Type**: `development_benchmark` (All 22 samples are development photos; no independent holdout claimed)
- **Dataset Split**: `development_only` (None - all 22 photos are explicitly designated and evaluated as development data. No independent holdout validation is claimed.)
- **Git Commit**: `905f82c` (Branch: `main` | Dirty: `True`)
- **Environment**: Python `3.13.9` on `Windows-11-10.0.26300` | RAM: `15.71 GB`
- **Ground Truth**: `ground_truth_v4.json` (Statutory Nutrients, Reconciled Packaging Evidence)

---

## 1. Executive Summary: Legacy vs Verified Scoring Progression

| Metric Name | Phase 4 Legacy (`ground_truth_v2.json`) | Phase 6 (`ground_truth_v3.json`) | Phase 7 Corrected (`ground_truth_v4.json`) | Impact & Findings |
|---|---|---|---|---|
| **Overall Field Precision** | 58.4% (111 / 190) | 96.0% (170 / 177) | **96.6%** (171 / 177) | Reconciled `real_photo_14` saturated fat 0.0g from image crop; only 6 genuine OCR errors remain |
| **Overall Field Recall** | 82.2% (111 / 135) | 77.3% (170 / 220) | **77.4%** (171 / 221) | Evaluated against all 221 physical label declarations |
| **Overall Field F1 Score** | 0.6831 | 0.8564 | **0.8593** | Robust harmonic balance across all declared fields |
| **Core Nutrient Precision** | 85.8% (97 / 113) | 96.6% (113 / 117) | **97.4%** (114 / 117) | Core precision reaches 97.4% with salt separated |
| **Core Nutrient Recall** | 82.2% (97 / 118) | 81.3% (113 / 139) | **81.4%** (114 / 140) | 114/140 core statutory nutrients correctly matched |
| **Core Nutrient F1 Score** | 0.8398 | 0.8828 | **0.8872** | High fidelity core extraction |
| **Total False Positives** | 79 reported FPs | 7 FPs | **6 true FPs** | All 79 historical errors adjudicated; 6 genuine OCR errors |
| **Serving Basis Accuracy** | 100.0% (20 / 20) | 95.0% (19 / 20) | **95.0%** (19 / 20) | Robust basis identification across legible panels |
| **Perfect Package Accuracy** | 0.0% (0 / 22) | 27.3% (6 / 22) | **27.3%** (6 / 22) | 6 packages achieve 100% exact extraction with zero FPs |
| **Mean Latency per Image** | 33.05 s | 31.15 s | **31.15 s** (Median: 22.95 s) | CPU execution time |
| **Peak RSS Memory** | 532.0 MB | 527.4 MB | **527.4 MB** | Stable memory ceiling |

---

## 2. Mathematical Reconciliation Audit

| Metric Dimension | Overall Aggregate | Per-Nutrient Sum | Per-Sample Sum | Reconciled? |
|---|---|---|---|---|
| **True Positives (TP)** | 171 | 171 | 171 | **MATCH** |
| **False Positives (FP)** | 6 | 6 | 6 | **MATCH** |
| **False Negatives (FN)** | 50 | 50 | 50 | **MATCH** |
| **Total GT Fields** | 221 | 221 | 221 | **MATCH** |

- **Reconciliation Status**: `VERIFIED (100% strict equality)`

---

## 3. Dataset Split Verification

| Split Category | Sample Count | Total GT Fields | TP | FP | FN | Precision | Recall | F1 Score |
|---|---|---|---|---|---|---|---|---|
| `dev` | 22 | 221 | 171 | 6 | 50 | 96.6% | 77.4% | 0.8593 |

> [!NOTE]
> All 22 samples are explicitly accounted for as development evaluation data (`dev`). Zero independent holdout claims are made.

---

## 4. Per-Nutrient Precision & Recall Breakdown (Label Declared Only)

| Nutrient Field | Core? | GT Declared | TP | FP | FN | Precision | Recall | F1 Score |
|---|---|---|---|---|---|---|---|---|
| `added_sugars_g` | No | 5 | 5 | 0 | 0 | 100.0% | 100.0% | 1.0000 |
| `calcium_mg` | No | 7 | 4 | 0 | 3 | 100.0% | 57.1% | 0.7272 |
| `carbohydrates_g` | Yes | 20 | 16 | 0 | 4 | 100.0% | 80.0% | 0.8889 |
| `cholesterol_mg` | No | 11 | 7 | 0 | 4 | 100.0% | 63.6% | 0.7778 |
| `energy_kcal` | Yes | 20 | 19 | 0 | 1 | 100.0% | 95.0% | 0.9744 |
| `energy_kj` | No | 8 | 7 | 0 | 1 | 100.0% | 87.5% | 0.9333 |
| `fat_g` | Yes | 20 | 17 | 0 | 3 | 100.0% | 85.0% | 0.9189 |
| `fibre_g` | No | 14 | 12 | 1 | 2 | 92.3% | 85.7% | 0.8889 |
| `iron_mg` | No | 7 | 4 | 1 | 3 | 80.0% | 57.1% | 0.6666 |
| `magnesium_mg` | No | 2 | 2 | 0 | 0 | 100.0% | 100.0% | 1.0000 |
| `potassium_mg` | No | 9 | 5 | 1 | 4 | 83.3% | 55.6% | 0.6667 |
| `protein_g` | Yes | 20 | 16 | 1 | 4 | 94.1% | 80.0% | 0.8649 |
| `salt_g` | Yes | 8 | 3 | 0 | 5 | 100.0% | 37.5% | 0.5455 |
| `saturated_fat_g` | Yes | 19 | 15 | 2 | 4 | 88.2% | 79.0% | 0.8334 |
| `sodium_mg` | Yes | 13 | 12 | 0 | 1 | 100.0% | 92.3% | 0.9600 |
| `sugars_g` | Yes | 20 | 16 | 0 | 4 | 100.0% | 80.0% | 0.8889 |
| `trans_fat_g` | No | 11 | 8 | 0 | 3 | 100.0% | 72.7% | 0.8421 |
| `vitamin_d_mcg` | No | 7 | 3 | 0 | 4 | 100.0% | 42.9% | 0.6000 |

---

## 5. Case-by-Case Sample Results

| ID | Split | Status | Basis (Pred/GT) | GT Fields | TP | FP | FN | Recall | Prec | Perfect? | Time (s) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `real_photo_01` | dev | panel_verified_exact | `per_100g` / `per_100g` | 9 | 9 | 0 | 0 | 100.0% | 100.0% | **Yes** | 10.8 |
| `real_photo_02` | dev | panel_verified_exact | `per_serving` / `per_serving` | 11 | 11 | 0 | 0 | 100.0% | 100.0% | **Yes** | 21.4 |
| `real_photo_03` | dev | panel_verified_exact | `per_serving` / `per_serving` | 14 | 11 | 1 | 3 | 78.6% | 91.7% | No | 11.9 |
| `real_photo_04` | dev | panel_verified_exact | `per_100g` / `per_100g` | 8 | 6 | 0 | 2 | 75.0% | 100.0% | No | 22.4 |
| `real_photo_05` | dev | panel_verified_exact | `per_100g` / `per_100g` | 8 | 7 | 0 | 1 | 87.5% | 100.0% | No | 19.4 |
| `real_photo_06` | dev | panel_verified_partial | `per_serving` / `per_serving` | 11 | 11 | 0 | 0 | 100.0% | 100.0% | **Yes** | 46.5 |
| `real_photo_07` | dev | panel_verified_exact | `per_serving` / `per_serving` | 16 | 9 | 1 | 7 | 56.2% | 90.0% | No | 19.9 |
| `real_photo_08` | dev | panel_verified_partial | `per_serving` / `per_serving` | 10 | 9 | 0 | 1 | 90.0% | 100.0% | No | 23.0 |
| `real_photo_09` | dev | panel_verified_exact | `per_100g` / `per_100g` | 10 | 10 | 0 | 0 | 100.0% | 100.0% | **Yes** | 17.5 |
| `real_photo_10` | dev | panel_verified_partial | `per_100g` / `per_100g` | 9 | 4 | 3 | 5 | 44.4% | 57.1% | No | 37.6 |
| `real_photo_11` | dev | panel_verified_partial | `per_100g` / `per_100g` | 9 | 1 | 0 | 8 | 11.1% | 100.0% | No | 31.8 |
| `real_photo_12` | dev | panel_verified_exact | `per_serving` / `per_serving` | 15 | 13 | 0 | 2 | 86.7% | 100.0% | No | 55.9 |
| `real_photo_13` | dev | panel_not_legible | `per_100g` / `front_only` | 0 | 0 | 0 | 0 | 100.0% | 0.0% | No | 29.9 |
| `real_photo_14` | dev | panel_verified_exact | `per_100g` / `per_100ml` | 8 | 7 | 0 | 1 | 87.5% | 100.0% | No | 39.9 |
| `real_photo_15` | dev | panel_not_legible | `per_100g` / `front_only` | 0 | 0 | 0 | 0 | 100.0% | 0.0% | No | 9.1 |
| `real_photo_16` | dev | panel_verified_exact | `per_serving` / `per_serving` | 15 | 12 | 0 | 3 | 80.0% | 100.0% | No | 20.7 |
| `real_photo_17` | dev | panel_verified_exact | `per_serving` / `per_serving` | 16 | 16 | 0 | 0 | 100.0% | 100.0% | **Yes** | 56.6 |
| `real_photo_18` | dev | panel_verified_exact | `per_serving` / `per_serving` | 15 | 13 | 0 | 2 | 86.7% | 100.0% | No | 20.3 |
| `real_photo_19` | dev | panel_verified_exact | `per_serving` / `per_serving` | 7 | 1 | 0 | 6 | 14.3% | 100.0% | No | 96.4 |
| `real_photo_20` | dev | panel_verified_exact | `per_serving` / `per_serving` | 14 | 8 | 1 | 6 | 57.1% | 88.9% | No | 36.1 |
| `real_photo_21` | dev | panel_verified_exact | `per_100g` / `per_100g` | 8 | 5 | 0 | 3 | 62.5% | 100.0% | No | 43.6 |
| `real_photo_22` | dev | panel_verified_exact | `per_100g` / `per_100g` | 8 | 8 | 0 | 0 | 100.0% | 100.0% | **Yes** | 14.8 |

---
