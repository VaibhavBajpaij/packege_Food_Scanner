# Implementation and Cleanup Plan: Barcode-First Food Scanner
**Project:** `D:\health app\food packet scanner\food-intelligence-engine`  
**Date:** 2026-10-24  
**Author:** Antigravity Engineering  
**Status:** Approved for Implementation  

---

## 1. Objectives and Scope

Transform the existing `food-intelligence-engine` into a reliable, barcode-first packaged-food scanner with:
1. Robust barcode scanning, normalization (EAN-13, EAN-8, UPC-A, UPC-E), and checksum validation.
2. Transparent completeness policy that checks whether product identity, energy, macronutrients, ingredients, and serving basis are sufficient.
3. Fallback flow to capture back-of-package label (supporting single image or separate nutrition and ingredients images).
4. Real pixel-level OCR with bounding-box geometry and confidence reporting.
5. Structured nutrient extraction handling edge cases (decimals `.`/`,`, inequalities `<1 g` preserved as bounds, units, %DV separation, printed zeros, salt vs sodium).
6. Strict provenance-aware enrichment (declared label > exact product DB match > reference estimate; never overwrite declared label with DB value).
7. User-friendly nutrition report with provenance badges, explainable warnings, and no medical claims.
8. Comprehensive test coverage for all 24 required scenarios.
9. Safe, verified cleanup of any dead code.

---

## 2. Phased Implementation Roadmap

### Phase A — Baseline & Integrity Verification (Completed)
- **Status:** Complete.
- **Verification:** Git commit `dde7109` clean. All 99 pytest tests passed in 76s. Models and local databases verified.

### Phase B — Architecture & Typed Schemas
- **Goal:** Define typed data structures and contracts for barcode scans, completeness verdicts, extraction results, and reports.
- **Files to create/modify:**
  - Create `src/food_engine/validation/barcode_validator.py`: Normalizer and checksum validator for EAN-13, EAN-8, UPC-A, UPC-E with leading-zero preservation.
  - Create `src/food_engine/validation/completeness.py`: `CompletenessPolicy` evaluating product records for missing vs non-applicable fields.
- **Dependencies:** None.
- **Acceptance Criteria:** Unit tests verifying valid/invalid barcodes, checksums, and completeness states.

### Phase C — Barcode-First Workflow & Product Lookup
- **Goal:** Implement primary `FoodIntelligenceEngine.scan_barcode(barcode: str)` method and enhance `ProductMatcher`.
- **Files to modify:**
  - `src/food_engine/product_matching/matcher.py`: Use normalized barcode lookup; support both 12-digit UPC-A and 13-digit EAN-13 representations.
  - `src/food_engine/engine.py`: Add `scan_barcode()` entry point that validates the barcode, queries local database, evaluates completeness policy, and returns structured verdict indicating if label scan is recommended.
- **Dependencies:** Phase B.
- **Acceptance Criteria:** Tests for valid complete barcode, valid incomplete barcode, unknown barcode, absent barcode, and invalid barcode checksum.

### Phase D — Multi-Image Capture, OCR & Extraction Enhancements
- **Goal:** Enable separate images for nutrition table and ingredient list (`nutrition_image` + `ingredients_image`) and ensure difficult extraction cases are handled cleanly.
- **Files to modify:**
  - `src/food_engine/engine.py`: Enhance `process_image()` / add `scan_package_label()` to accept single image or dual images (`nutrition_image`, `ingredients_image`).
  - `src/food_engine/nutrition_extraction/structured.py`: Ensure inequality bounds (`upper_bound: True` for `<1 g`, `≤ 0.5 g`) are preserved in output nutrient dictionaries without converting `<1 g` to `1 g`.
  - `src/food_engine/ingredient_parser/parser.py`: Parse ingredients from dual-image runs and preserve raw printed text.
- **Dependencies:** Phase C.
- **Acceptance Criteria:** Tests for dual-image input, `<1 g` inequality preservation, decimal commas/points, %DV separation, and printed zeros.

### Phase E — Data Precedence & Conflict Enrichment
- **Goal:** Enforce strict data precedence rules in `NutrientFusion`.
- **Precedence Order:**
  1. Printed label values (`declared`) = primary.
  2. Exact product DB match (`exact_db_match`) = fills missing fields only.
  3. Generic reference DB (`reference_derived`) = fills remaining missing fields as estimate.
  4. Calculated values (`calculated`) = kept distinct.
- **Rules:**
  - Never overwrite a declared label value with a database value.
  - Never convert missing to zero.
  - Record conflicting values between label and database with explanation.
- **Files to modify:**
  - `src/food_engine/product_matching/nutrient_fusion.py`
- **Dependencies:** Phase D.
- **Acceptance Criteria:** Tests verifying declared values are preserved when DB differs, and conflicts are audited.

### Phase F — Final Result Presentation & Reporting
- **Goal:** Produce clear, user-friendly reports with visual provenance badges and explainable warnings.
- **Badges:** `[DECLARED]`, `[EXACT_DB]`, `[CALCULATED]`, `[REFERENCE_ESTIMATE]`, `[MISSING]`, `[UNCERTAIN]`.
- **Files to modify:**
  - `src/food_engine/reporting/output_builder.py`: Add text report generator and format badges.
- **Dependencies:** Phase E.
- **Acceptance Criteria:** Output JSON satisfies `config/nutrient_schema.yaml` and formatted text report is human-readable.

### Phase G — Safe Cleanup
- **Goal:** Remove verified-unused items without breaking imports or test infrastructure.
- **Action:**
  - Archive ad-hoc scripts (`scripts/probe_off.py`, `scripts/probe_sources.py`) into `scripts/archive/` or document their purpose.
  - Clean any unused imports.
- **Dependencies:** Phase F.
- **Acceptance Criteria:** Full test suite passes after cleanup.

### Phase H — Final Verification & Documentation
- **Goal:** Run complete test suite (all 24 scenarios), benchmark, and generate completion report.
- **Files to create:**
  - `tests/unit/test_barcode_first_workflow.py` (covering scenarios 1–6).
  - `tests/unit/test_difficult_nutrition_cases.py` (covering scenarios 10–18).
  - `tests/unit/test_enrichment_and_provenance.py` (covering scenarios 19–24).
  - `reports/completion/packaged_food_scanner_completion_report.md`.
- **Acceptance Criteria:** All unit, integration, and benchmark tests pass. Clean git diff.

---

## 3. Rollback Plan for Cleanup

1. Before any file removal or refactoring, check git status and test baseline.
2. In case of unexpected breakages:
   - Git rollback: `git checkout HEAD -- <filepath>` or `git restore <filepath>`.
   - Never delete uncommitted files without explicit backup.
3. Every cleanup step is accompanied by `pytest` execution before proceeding.
