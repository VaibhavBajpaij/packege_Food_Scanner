# Food Intelligence Engine — Phase 4 Reproducible Benchmark Report

- **Evaluation Date**: `2026-10-24T12:51:50.686627`
- **Benchmark Type**: `development_benchmark` (This is a DEVELOPMENT benchmark on existing samples, NOT an independent holdout result.)
- **Git Commit**: `0104415` (Branch: `main` | Dirty: `True`)
- **Environment**: Python `3.13.9` on `Windows-11-10.0.26300-SP0` | RAM: `15.71 GB`
- **Engine Mode**: Full-pipeline `FoodIntelligenceEngine.process_image` (Deskew + 1.5x Upscale Rescue + Structured)

---

## 1. Executive Summary & Headline Metrics

| Metric Name | Value | Evaluation Details & Mathematical Definition |
|---|---|---|
| **Overall Field Recall** | **82.2%** | $111 / 135$ declared fields correctly matched within 5% tolerance |
| **Overall Field Precision** | **58.4%** | $111 / (111 + 79)$ extracted values that were correct |
| **Overall Field F1 Score** | **0.6831** | Harmonic mean of field precision and field recall |
| **Core Nutrient Recall** | **82.2%** | $97 / 118$ core nutrients (Energy, Fat, Carbs, Sugars, Protein, Sodium, Salt) |
| **Core Nutrient Precision** | **85.8%** | $97 / (97 + 16)$ core extractions that were correct |
| **Serving Basis Accuracy** | **100.0%** | $20 / 20$ packages where detected basis matched ground truth |
| **Packet-Level Perfect Accuracy** | **0.0%** | **0 / 22** packets with 100% fields correct, zero false positives, and basis match |
| **Mean Latency per Image** | **33.05 s** | CPU execution (Median: 32.20s, Min: 8.56s, Max: 89.60s) |
| **Peak Working Set Memory** | **532.0 MB** | Peak process memory observed during high-resolution multi-scale OCR |

---

## 2. Dev vs. Historical 'Held-Out' Split Comparison

> [!IMPORTANT]
> **Provenance Warning**: As established in the independent audit, the 'held-out' split of 7 images was previously inspected during exploratory debugging. It is reported below strictly for historical continuity and must **not** be presented as an independent validation set.

| Split Group | Sample Count | Total Declared Fields | TP | FP | FN | Field Recall | Field Precision | Perfect Packets | Basis Accuracy |
|---|---|---|---|---|---|---|---|---|---|
| **Dev Split** | 15 | 88 | 72 | 59 | 16 | **81.8%** | 55.0% | 0 / 15 | 86.7% |
| **Inspected 'Held-Out' Split** | 7 | 47 | 39 | 20 | 8 | **83.0%** | 66.1% | 0 / 7 | 100.0% |

---

## 3. Per-Nutrient Precision & Recall Breakdown

| Nutrient Field | Core? | GT Declared | TP | FP | FN | Precision | Recall | F1 Score |
|---|---|---|---|---|---|---|---|---|
| `added_sugars_g` | No | 0 | 0 | 5 | 0 | 0.0% | 0.0% | 0.0000 |
| `calcium_mg` | No | 0 | 0 | 4 | 0 | 0.0% | 0.0% | 0.0000 |
| `carbohydrates_g` | Yes | 20 | 16 | 0 | 4 | 100.0% | 80.0% | 0.8889 |
| `cholesterol_mg` | No | 0 | 0 | 7 | 0 | 0.0% | 0.0% | 0.0000 |
| `energy_kcal` | Yes | 20 | 19 | 0 | 1 | 100.0% | 95.0% | 0.9744 |
| `energy_kj` | No | 0 | 0 | 7 | 0 | 0.0% | 0.0% | 0.0000 |
| `fat_g` | Yes | 20 | 17 | 0 | 3 | 100.0% | 85.0% | 0.9189 |
| `fibre_g` | No | 0 | 0 | 13 | 0 | 0.0% | 0.0% | 0.0000 |
| `iron_mg` | No | 0 | 0 | 5 | 0 | 0.0% | 0.0% | 0.0000 |
| `magnesium_mg` | No | 0 | 0 | 2 | 0 | 0.0% | 0.0% | 0.0000 |
| `potassium_mg` | No | 0 | 0 | 6 | 0 | 0.0% | 0.0% | 0.0000 |
| `protein_g` | Yes | 20 | 16 | 1 | 4 | 94.1% | 80.0% | 0.8649 |
| `salt_g` | Yes | 6 | 2 | 12 | 4 | 14.3% | 33.3% | 0.2000 |
| `saturated_fat_g` | No | 17 | 14 | 3 | 3 | 82.3% | 82.3% | 0.8235 |
| `sodium_mg` | Yes | 13 | 12 | 2 | 1 | 85.7% | 92.3% | 0.8889 |
| `sugars_g` | Yes | 19 | 15 | 1 | 4 | 93.8% | 79.0% | 0.8572 |
| `trans_fat_g` | No | 0 | 0 | 8 | 0 | 0.0% | 0.0% | 0.0000 |
| `vitamin_d_mcg` | No | 0 | 0 | 3 | 0 | 0.0% | 0.0% | 0.0000 |

---

## 4. Case-by-Case Sample Results

| ID | Split | Product Name | Time (s) | Memory (MB) | Basis (Pred / GT) | Declared | TP | FP | FN | Recall | Perfect? |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `real_photo_01` | held_out | Unknown | 25.6 | 337 | `per_100g` / `per_100g` | 7 | 7 | 3 | 0 | 100.0% | No |
| `real_photo_02` | dev | Unknown | 46.5 | 370 | `per_serving` / `per_serving` | 7 | 7 | 5 | 0 | 100.0% | No |
| `real_photo_03` | dev | Unknown | 19.3 | 366 | `per_serving` / `per_serving` | 7 | 6 | 7 | 1 | 85.7% | No |
| `real_photo_04` | dev | Unknown | 32.2 | 369 | `per_100g` / `per_100g` | 7 | 5 | 1 | 2 | 71.4% | No |
| `real_photo_05` | dev | Unknown | 23.4 | 375 | `per_100g` / `per_100g` | 7 | 6 | 2 | 1 | 85.7% | No |
| `real_photo_06` | dev | Unknown | 51.2 | 449 | `per_serving` / `per_serving` | 7 | 7 | 5 | 0 | 100.0% | No |
| `real_photo_07` | held_out | Unknown | 20.7 | 449 | `per_serving` / `per_serving` | 7 | 6 | 5 | 1 | 85.7% | No |
| `real_photo_08` | dev | Unknown | 23.8 | 459 | `per_serving` / `per_serving` | 7 | 7 | 3 | 0 | 100.0% | No |
| `real_photo_09` | held_out | Unknown | 17.0 | 450 | `per_100g` / `per_100g` | 7 | 7 | 3 | 0 | 100.0% | No |
| `real_photo_10` | dev | Unknown | 36.5 | 447 | `per_100g` / `per_100g` | 7 | 3 | 4 | 4 | 42.9% | No |
| `real_photo_11` | held_out | Unknown | 33.2 | 453 | `per_100g` / `per_100g` | 5 | 1 | 0 | 4 | 20.0% | No |
| `real_photo_12` | dev | Unknown | 54.6 | 449 | `per_serving` / `per_serving` | 7 | 7 | 7 | 0 | 100.0% | No |
| `real_photo_13` | dev | Unknown | 28.4 | 454 | `per_100g` / `front_only` | 0 | 0 | 0 | 0 | 0.0% | No |
| `real_photo_14` | dev | Unknown | 37.9 | 453 | `per_100ml` / `per_100ml` | 6 | 5 | 2 | 1 | 83.3% | No |
| `real_photo_15` | dev | Unknown | 8.6 | 464 | `per_100g` / `front_only` | 0 | 0 | 0 | 0 | 0.0% | No |
| `real_photo_16` | held_out | Unknown | 18.8 | 458 | `per_serving` / `per_serving` | 7 | 7 | 6 | 0 | 100.0% | No |
| `real_photo_17` | dev | Unknown | 52.2 | 458 | `per_serving` / `per_serving` | 7 | 7 | 10 | 0 | 100.0% | No |
| `real_photo_18` | dev | Unknown | 19.8 | 455 | `per_serving` / `per_serving` | 7 | 6 | 8 | 1 | 85.7% | No |
| `real_photo_19` | dev | Unknown | 89.6 | 520 | `per_serving` / `per_serving` | 6 | 1 | 0 | 5 | 16.7% | No |
| `real_photo_20` | dev | Unknown | 33.7 | 528 | `per_serving` / `per_serving` | 6 | 5 | 5 | 1 | 83.3% | No |
| `real_photo_21` | held_out | Unknown | 40.3 | 532 | `per_100g` / `per_100g` | 7 | 4 | 1 | 3 | 57.1% | No |
| `real_photo_22` | held_out | Unknown | 13.9 | 527 | `per_100g` / `per_100g` | 7 | 7 | 2 | 0 | 100.0% | No |

---

## 5. Metric Definitions & Formulas

1. **True Positive ($TP$)**: Predicted value $\hat{v}$ matches ground-truth declared value $v$ within relative tolerance: $|\hat{v} - v| / |v| \le 0.05$ (or absolute difference $\le 10^{-6}$ when $v=0$).
2. **False Negative ($FN$)**: Ground truth declares value $v$, but the engine either produced $None$ (missing) or a value outside the 5% tolerance.
3. **False Positive ($FP$)**: Engine produced a numeric prediction that was either incorrect for a declared field ($|\hat{v} - v| / |v| > 0.05$) or predicted a nutrient not declared on the physical packaging.
4. **Field Recall**: $\frac{TP}{TP + FN}$ across all declared non-null ground-truth fields.
5. **Field Precision**: $\frac{TP}{TP + FP}$ across all extracted candidate values.
6. **Perfect Packet Accuracy**: Percentage of food packages where all declared nutrients are correctly extracted with zero false negatives, zero false positives, and an exact serving basis match.
