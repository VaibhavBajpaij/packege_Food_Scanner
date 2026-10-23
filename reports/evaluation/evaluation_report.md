# Food Intelligence Engine — Evaluation & Accuracy Report

- **Evaluation Date**: `2026-10-24T00:22:46.993130`
- **Evaluated Engine Version**: `0.1.0`
- **Benchmark Scenarios Evaluated**: `2` (Baked snacks per 100g, Beverage nectar per 100ml)

## 1. Measured Accuracy Metrics

| Evaluation Metric | Measured Result | Benchmark Target | Status |
|---|---|---|---|
| **Exact Nutrient-Field Accuracy** | `100.0%` | >= 90.0% | PASS |
| **Numeric Value Accuracy (±5%)** | `100.0%` | >= 95.0% | PASS |
| **Unit Consistency Accuracy** | `100.0%` | 100.0% | PASS |
| **Serving Basis Accuracy** | `100.0%` | 100.0% | PASS |
| **Missing Field Detection Rate** | `100.0%` | 100.0% | PASS |
| **False Allergen-Negative Rate** | `0.0%` | **0.0%** | **PASS (CRITICAL SAFETY)** |

## 2. Latency & Resource Utilization Profile

- **Median Latency**: `219.6 ms`
- **95th-Percentile Latency**: `276.4 ms`
- **Peak Working Memory**: `4.59 MB` (Well within 16 GB system RAM & 4 GB VRAM constraints)

## 3. Detailed Benchmark Case Log

| Case ID | Label Type | Image | Basis Match | Declared Allergens Identified | Latency |
|---|---|---|---|---|---|
| `biscuit_sample_01` | Solid Packaged Food (Baked Goods) | `sample_biscuit_packet.png` | YES | Wheat, Milk / Dairy, Soybeans / Soy | `0.2764s` |
| `juice_sample_02` | Liquid Beverage (Nectar) | `sample_juice_bottle.png` | YES | None | `0.1628s` |

## 4. Evaluation Methodology & Ground Truth Integrity
1. **Zero Self-Prediction Contamination**: Models are evaluated against manually codified ground truth labels containing exact analytical nutrient amounts.
2. **Strict Missing Value Treatment**: Missing fields are never imputed as zero; they must be identified as `missing` by the extractor.
3. **Zero False Allergen Negative Safety Threshold**: Any failure to detect an explicitly printed allergen is treated as a critical safety defect.
