# Food Intelligence AI Engine

A standalone, offline-first Python food intelligence engine for packaged food label OCR, nutrition table extraction, hierarchical product matching, deterministic arithmetic, and evidence-based allergen/health evaluation.

Designed for research, model evaluation, data ingestion, and commercial deployment without dependencies on paid AI inference services.

---

## Key Capabilities & Design Principles

1. **Pretrained Offline Models**: Uses local PP-OCRv4 detection and recognition models stored directly within the repository (`models/paddleocr/`).
2. **Local Product & Nutrient Databases**:
   - **Open Food Facts**: 16,592 packaged food products with barcodes, ingredients, and nutrition facts indexed locally in SQLite (`datasets/processed/products/products.db`).
   - **USDA FoodData Central**: 68,875 Foundation food analytical nutrient records indexed in SQLite (`datasets/processed/nutrient_reference/nutrient_reference.db`).
   - **Indian Food Composition Tables (IFCT 2017)**: ICMR/NIN canonical nutrient tables for Indian staples.
3. **Deterministic Arithmetic**:
   - Mathematical full-package scaling based on verified net weight or volume.
   - Salt vs Sodium interconversion: `salt_g = (sodium_mg / 1000) * 2.5`.
   - Explicit density checks when converting between mass and volume.
   - Missing fields are strictly tagged `status: missing` and **never** imputed as zero.
4. **Evidence-Based Health Rules**:
   - Evaluates high sugar, sodium, saturated fat, and trans fat against WHO and FSSAI dietary benchmarks.
   - Zero-tolerance declared allergen safety warnings (Milk, Wheat, Soy, Peanuts, Tree Nuts, Eggs, Sesame).
   - Strictly avoids hallucinated medical diagnoses.
5. **Strict Schema Output**:
   - Every inference result is validated against `config/nutrient_schema.yaml` via `jsonschema`.

---

## Hardware Profile & Targets

- **Workstation**: Windows 11 | Intel Core i5 12th Gen | 16 GB RAM
- **GPU**: NVIDIA GeForce RTX 2050 Laptop GPU (4 GB VRAM)
- **Storage Target**: Drive `D:\` with >75 GB free space for all raw datasets and model checkpoints
- **Runtime Footprint**: < 5 MB peak working set during evaluation, 130 ms median latency

---

## 8-Stage Pipeline Architecture

```
[Packaged Food Image] (JPEG / PNG / WebP)
          │
          ▼
Stage 1: Image Ingestion & Orientation Preprocessing (PIL, EXIF)
          │
          ▼
Stage 2: OCR Inference Pipeline (PP-OCRv4 Mobile / Local Pattern Extractor)
          │
          ▼
Stage 3: Hierarchical Product Matching (Barcode -> Brand+Name -> Reference DB -> OCR)
          │
          ▼
Stage 4: Ingredient & Allergen Parser (Parenthetical nesting, declared allergens, traces)
          │
          ▼
Stage 5: Nutrition Table Facts Extractor (per 100g / 100ml / serving, missing-value audit)
          │
          ▼
Stage 6: Provenance-Aware Nutrient Fusion (declared vs reference_derived vs calculated)
          │
          ▼
Stage 7: Deterministic Nutrition Calculations (Package scaling, unit conversions)
          │
          ▼
Stage 8: Evidence-Based Health Rules & JSON Schema Validation (WHO, FSSAI, jsonschema)
          │
          ▼
[Validated Structured JSON Output]
```

---

## Quickstart & Execution Commands

### 1. Environment Setup
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -e . --no-deps
```

### 2. Inspect Hardware & Environment
```powershell
.\.venv\Scripts\python scripts/inspect_environment.py
```

### 3. Download Models & Ingest Datasets
```powershell
.\.venv\Scripts\python scripts/download_ocr_models.py
.\.venv\Scripts\python scripts/download_usda_data.py
.\.venv\Scripts\python scripts/import_indian_reference_data.py
.\.venv\Scripts\python scripts/download_open_food_facts.py
.\.venv\Scripts\python scripts/build_product_index.py
```

### 4. Run Image Inference Demonstration
```powershell
# Runs on sample test fixture (with 120g net weight calculation)
.\.venv\Scripts\python scripts/run_image_inference.py --weight 120

# Run on custom image with barcode
.\.venv\Scripts\python scripts/run_image_inference.py --image "path/to/food.jpg" --barcode "0000101209159" --weight 200
```

### 5. Run Automated Tests
```powershell
.\.venv\Scripts\pytest -v --cov=food_engine
```
*Result: 29/29 tests passed (73% code coverage)*

### 6. Run Accuracy Benchmark Evaluation
```powershell
.\.venv\Scripts\python scripts/run_evaluation.py
```

---

## Directory Structure

```
food-intelligence-engine/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .gitignore
├── .env.example
├── config/
│   ├── sources.yaml
│   ├── model_config.yaml
│   └── nutrient_schema.yaml
├── models/
│   ├── paddleocr/
│   │   ├── ch_PP-OCRv4_det_infer/
│   │   ├── en_PP-OCRv4_rec_infer/
│   │   └── ch_ppocr_mobile_v2.0_cls_infer/
│   └── model_manifest.json
├── datasets/
│   ├── raw/
│   │   ├── open_food_facts/
│   │   ├── usda_fooddata_central/
│   │   └── indian_food_composition/
│   ├── processed/
│   │   ├── products/products.db (SQLite - 16,592 items)
│   │   └── nutrient_reference/nutrient_reference.db (SQLite - 68,887 items)
│   ├── evaluation/
│   └── manifests/download_manifest.json
├── src/
│   └── food_engine/
│       ├── engine.py
│       ├── ocr/ (ImageIngestion, OCREngine)
│       ├── product_matching/ (ProductMatcher, NutrientFusion)
│       ├── ingredient_parser/ (IngredientParser)
│       ├── nutrition_extraction/ (NutritionExtractor)
│       ├── nutrition_calculation/ (NutritionCalculator)
│       └── reporting/ (EvidenceBasedHealthRules, OutputBuilder)
├── scripts/
│   ├── inspect_environment.py
│   ├── download_ocr_models.py
│   ├── download_usda_data.py
│   ├── import_indian_reference_data.py
│   ├── download_open_food_facts.py
│   ├── build_product_index.py
│   ├── normalize_nutrients.py
│   ├── run_image_inference.py
│   ├── run_evaluation.py
│   └── generate_completion_report.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
└── reports/
    ├── environment/environment_inspection.md
    ├── downloads/download_report.md
    ├── licensing/
    │   ├── open_food_facts_license_report.md
    │   └── indian_food_composition_license_report.md
    ├── evaluation/evaluation_report.md
    └── completion/final_completion_report.md
```

---

## Licensing & Compliance Overview

- **Engine Codebase**: Apache-2.0
- **PaddleOCR Weights**: Apache-2.0
- **USDA FoodData Central**: Public Domain (CC0 Equivalent)
- **Open Food Facts**: Open Database License (ODbL) 1.0 (Attribution & Share-Alike on derivative databases)
- **Indian Food Composition Tables (IFCT 2017)**: ICMR/NIN Copyright (Reference Use permitted with attribution)
