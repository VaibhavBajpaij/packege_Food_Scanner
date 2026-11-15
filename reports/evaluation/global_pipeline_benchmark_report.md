# Global Packaged Food Scanner — Benchmark & Verification Report

**Evaluation Date:** 2026-10-24 20:20:39 UTC  
**Dataset Scope:** Multi-Country Global Holdout (North America, Europe, Asia-Pacific, Global Brands)  
**License:** Open Food Facts (ODbL 1.0) — **100% Commercially Permissible for QA & Evaluation**  

---

## Executive Summary

| Total Packaged Foods | Total Correct (TP) | Incorrect (FP) | Missing (FN) | Field Precision | Field Recall | Global F1-Score |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **19** | **61** | **41** | **64** | **59.8%** | **48.8%** | **53.7%** |
> [!NOTE]
> Evaluation enforces a standard tolerance of $\pm 5\%$ relative error or $\pm 0.5\text{g}$ absolute difference. Extra ungrounded extractions are penalized as False Positives, and undetected nutrients are penalized as False Negatives.

---

## Regional Performance Breakdown

| Region | Samples | Barcode DB Matches | Successful Extractions | TP | FP | FN | Precision | Recall |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **North America** | 5 | 1 | 3 | 10 | 24 | 11 | 29.4% | 47.6% |
| **Europe** | 8 | 1 | 7 | 30 | 5 | 36 | 85.7% | 45.5% |
| **Asia-Pacific** | 4 | 0 | 3 | 16 | 12 | 7 | 57.1% | 69.6% |
| **Global** | 2 | 0 | 1 | 5 | 0 | 10 | 100.0% | 33.3% |

---

## Product-by-Product Evaluation Ledger

| Sample ID | Country | Product Name | TP | FP | FN | Precision | Recall | Physical Sanity | Runtime |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `global_01` | United States | **oreo cookies shelf** | 1 | 6 | 2 | 14.3% | 33.3% | ✅ Pass | 24.06s |
| `global_02` | United States | **Gmills hny nut cheerios ** | 2 | 5 | 2 | 28.6% | 50.0% | ⚠️ Warn | 14.17s |
| `global_03` | United States | **Nacho Cheese Flavored** | 0 | 7 | 2 | 0.0% | 0.0% | ⚠️ Warn | 13.52s |
| `global_04` | United States | **Creamy Peanut Butter** | 0 | 6 | 3 | 0.0% | 0.0% | ✅ Pass | 16.1s |
| `global_05` | United States | **Almondmilk** | 7 | 0 | 2 | 100.0% | 77.8% | ✅ Pass | 49.25s |
| `global_06` | United Kingdom | **Snickers** | 4 | 0 | 5 | 100.0% | 44.4% | ⚠️ Warn | 30.81s |
| `global_07` | United Kingdom | **Beanz in a rich tomato s** | 4 | 1 | 4 | 80.0% | 50.0% | ✅ Pass | 46.46s |
| `global_08` | France | **Excellence Noir Prodigie** | 6 | 0 | 3 | 100.0% | 66.7% | ⚠️ Warn | 37.57s |
| `global_09` | France | **Nutella** | 0 | 0 | 9 | 0.0% | 0.0% | ✅ Pass | 45.34s |
| `global_10` | Belgium | **Prince** | 7 | 0 | 2 | 100.0% | 77.8% | ⚠️ Warn | 24.52s |
| `global_11` | Germany | **Nutella Nuss-Nugat-Creme** | 3 | 2 | 3 | 60.0% | 50.0% | ✅ Pass | 78.37s |
| `global_12` | Italy | **Barilla PESTO alla GENOV** | 3 | 2 | 4 | 60.0% | 42.9% | ⚠️ Warn | 48.36s |
| `global_13` | India | **Yippee noodles** | 7 | 0 | 2 | 100.0% | 77.8% | ⚠️ Warn | 17.71s |
| `global_14` | India | **Lays Classics Salted 20r** | 5 | 2 | 2 | 71.4% | 71.4% | ⚠️ Warn | 14.64s |
| `global_15` | India | **maggi** | 4 | 3 | 1 | 57.1% | 80.0% | ⚠️ Warn | 65.83s |
| `global_17` | United States / Thailand | **Thai peanut noodle kit i** | 0 | 7 | 2 | 0.0% | 0.0% | ✅ Pass | 33.34s |
| `global_18` | International / Global | **Coca-Cola Original** | 5 | 0 | 3 | 100.0% | 62.5% | ✅ Pass | 46.54s |
| `global_19` | United States / Global | **Monster Energy** | 0 | 0 | 7 | 0.0% | 0.0% | ✅ Pass | 9.06s |
| `global_20` | United Kingdom / EU | **Mars** | 3 | 0 | 6 | 100.0% | 33.3% | ✅ Pass | 53.17s |

---

## Automated Hard-Example & Failure Triage (Active Learning)

Failed or uncertain scans are automatically logged with companion JSON sidecars in `datasets/triage/reports/`:
- **Bucket A (Photographic Fault):** Blur, extreme glare, out-of-focus camera. Prompt user to retake photo.
- **Bucket B (Engine Bug):** Sharp readable image, but table parser or regex missed fields. Automatically added to the developer remediation queue.
