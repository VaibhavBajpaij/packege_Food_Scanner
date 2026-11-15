# Data and Model Provenance Audit
**Project:** `D:\health app\food packet scanner\food-intelligence-engine`  
**Date:** 2026-10-24  
**Author:** Antigravity Engineering  

---

## 1. Overview of Data Assets and Models

This document details the exact provenance, licensing, row counts, and operational usage of all datasets and pretrained models residing in the repository.

---

## 2. Pretrained Model Provenance

All models reside under `models/paddleocr/` and are tracked in `models/model_manifest.json`:

| Model Name | Artifact Version | Files & Checksum Verified | License | Commercial Status | Runtime Usage |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PP-OCRv4 English Rec** | `PP-OCRv4` (English) | `en_PP-OCRv4_rec_infer` (10.2 MB)<br>SHA-256: `d5ae153a...` | Apache-2.0 | Permitted with standard attribution | **Active Production**: Textline recognition on label pixels |
| **PP-OCRv4 Detection** | `PP-OCRv4` (Universal) | `ch_PP-OCRv4_det_infer` (4.88 MB)<br>SHA-256: `5f7217e0...` | Apache-2.0 | Permitted with standard attribution | **Active Production**: Text polygon detection on label pixels |
| **PP-OCR Angle Classifier** | `v2.0` (Textline Ori) | `ch_ppocr_mobile_v2.0_cls_infer` (2.18 MB)<br>SHA-256: `50735258...` | Apache-2.0 | Permitted with standard attribution | **Active Production**: Line rotation & orientation classification |

### Cooked-Food / Plate-Food Image Classifier Status:
- **Audit Result:** **Zero** plate-food image classifier files, datasets, or checkpoints exist in the repository.
- **Statement of Non-Applicability:** The target product workflow is exclusively packaged food barcode lookup and back-of-pack label OCR. No 43-class plate food model exists or will be trained.

---

## 3. Verified Data Sources and Local Databases

### A. Open Food Facts (Packaged Food Products)
- **File Location:** `datasets/processed/products/products.db` (12.3 MB SQLite database)
- **Table Name:** `off_products`
- **Verified Row Count:** **16,592** packaged food products
- **Indexed Columns:** `code` (barcode), `product_name`, `brands`
- **Fields Available:** `code`, `product_name`, `brands`, `categories`, `countries`, `ingredients_text`, `allergens`, `serving_size`, `energy_100g`, `proteins_100g`, `carbohydrates_100g`, `sugars_100g`, `fat_100g`, `saturated_fat_100g`, `fiber_100g`, `sodium_100g`, `salt_100g`, `nutrients_json`
- **Import Completeness:** **Curated Regional / Common Subset**. Not a complete dump of the 3+ million global OFF database (which would exceed 30 GB compressed).
- **Licensing & Attribution:**
  - Database: Open Database License (ODbL) 1.0
  - Contents: Database Contents License (DbCL) 1.0
  - Requirement: Attribution ("Data sourced from Open Food Facts under ODbL") and Share-Alike on database derivative updates.
- **Operational Fit:**
  - Highly reliable for barcode lookup of popular consumer packaged items.
  - A local database is preferred for instant sub-millisecond offline lookup, with optional live API fallback for barcodes missing from the 16.5k local subset.

### B. USDA FoodData Central (Foundation Foods)
- **File Location:** `datasets/processed/nutrient_reference/nutrient_reference.db` (21.8 MB SQLite database)
- **Table Name:** `usda_foods`
- **Verified Row Count:** **68,875** items
- **Fields Available:** `fdc_id`, `description`, `data_type`, `nutrients_json`
- **Import Completeness:** Complete import of USDA Foundation Foods and SR Legacy subset (Release 2024-10-31).
- **Licensing & Attribution:** U.S. Public Domain (CC0 equivalent). Retained as data provenance best practice.
- **Operational Fit:** High-fidelity nutrient baselines for whole ingredients and reference foods. Used only as a fallback reference estimate when branded packaged data is absent.

### C. Indian Food Composition Tables (IFCT 2017)
- **File Location:** `datasets/processed/nutrient_reference/nutrient_reference.db`
- **Table Name:** `indian_foods`
- **Verified Row Count:** **12** Indian staple foods
- **Source:** National Institute of Nutrition (ICMR - Indian Council of Medical Research), Hyderabad, India.
- **Import Completeness:** Curated analytical staple subset (wheat flour, whole milk, lentils, rice, etc.).
- **Licensing & Attribution:** Government of India / ICMR Copyright. Used strictly for reference comparison with explicit citation.

---

## 4. Evaluation and Ground Truth Provenance

- **Evaluation Benchmark:** 22 real packaged-food packaging photographs located in `tests/fixtures/real_photos/`.
- **Ground Truth Version:** `tests/fixtures/real_photos/ground_truth_v4.json` (Phase 7 reconciled).
- **Dataset Split Disclosures:** All 22 packaging photos are explicitly declared as **development benchmark data**. No independent holdout is claimed on these 22 images.
- **Adjudication Ledger:** Reconciles 79 historical false positives and documents field-level provenance across declared, calculated, and reference-derived nutrients.

---

## 5. Architectural Recommendations

1. **Retain Local SQLite Index:** The 16,592-product local index provides offline capability and zero network latency.
2. **Add Live API Option:** When an unknown barcode is scanned in online mode, query the Open Food Facts API with a 3-second timeout and cache successful results in `products.db`.
3. **Data Precedence Guardrails:**
   - Package-declared values ALWAYS take precedence over Open Food Facts or USDA values.
   - Database values must NEVER overwrite label-declared nutrients.
