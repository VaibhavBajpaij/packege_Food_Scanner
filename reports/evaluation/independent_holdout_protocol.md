# Independent Holdout Validation Protocol (Phase 4)

- **Document ID**: `PROTO-EVAL-2026-V1`
- **Effective Date**: 2026-10-24
- **Objective**: Establish a rigorous, clean-room evaluation methodology for measuring food packaging OCR and nutrition extraction accuracy without data leakage or overfitting.

---

## 1. Protocol Rationale & Problem Statement

Prior evaluations in Phase 2 and Phase 3 suffered from:
1. Ground truth initially scraped from database fields rather than visual packaging (`ground_truth.json`).
2. Iterative model regex rules tailored directly to characters misread in the test images (`structured.py`).
3. Reporting performance on a "held-out" split that had already been inspected during development.

To establish authentic generalization performance, all future model releases must be evaluated against a **new, independently acquired, cryptographically frozen holdout set**.

---

## 2. Image Collection Protocol

### 2.1 Target Dataset Composition
The holdout dataset must consist of a minimum of **50 distinct, previously unseen packaged food products**.

```
Packaging Form Factors (Stratified Sampling):
  ├── Flexible Film / Foil Pouches (Snacks, chips, noodles)      : 12 images (24%)
  ├── Rigid Cardboard Boxes (Cereals, crackers, cookies)        : 10 images (20%)
  ├── Cylindrical Metal Cans (Beans, soups, tuna)               :  6 images (12%)
  ├── Glass / Plastic Jars (Spreads, sauces, condiments)        :  6 images (12%)
  ├── Beverage Cartons & Tetra Paks (Milk, plant milk, juice)   :  6 images (12%)
  ├── Beverage Cans (Soda, energy drinks, tea)                  :  5 images (10%)
  └── Confectionery Wrappers (Candy bars, small snacks)         :  5 images (10%)
```

### 2.2 Photographic & Environmental Diversity
Photographs must be captured under authentic consumer mobile scanning conditions:
- **Devices**: At least 3 different mobile phone cameras (varying focal lengths and sensors).
- **Resolutions**: Native phone resolution (clamped to max side 1920px prior to storage).
- **Lighting Conditions**:
  - Direct artificial overhead lighting (causing specular glare on foil and glossy surfaces).
  - Ambient diffuse indoor lighting.
  - Shadow gradients across curved surfaces (cans and bottles).
- **Surface Geometries**:
  - Planar (flat box panels).
  - Cylindrical curvature (cans, jars, bottles).
  - Crumpled/wrinkled surfaces (flexible pouches).
  - Diagonal / tilted orientations (5° to 25° camera angle).

---

## 3. Independent Double-Blind Transcription Protocol

To ensure ground-truth values are authoritative and free from model bias:

```
[Camera Raw Image]
       │
       ├───► Transcriber A (Independent Manual Visual Transcription) ───┐
       │                                                                ▼
       └───► Transcriber B (Independent Manual Visual Transcription) ───► Discrepancy Reconciliation
                                                                        │ (Pixel-level zoom by Auditor)
                                                                        ▼
                                                             [Frozen Ground Truth JSON]
```

### 3.1 Strict Transcription Rules
1. **Zero Model Interaction**: Transcribers must never run OCR or inspect model predictions before or during transcription.
2. **Visual Pixels Only**: Values must be transcribed strictly from visual image inspection. Never copy values from online databases, barcode lookups, or Open Food Facts.
3. **Dual-Column Handling**: If a product has dual declarations (e.g., "Per Serving (30g)" and "Per 100g"), both columns must be transcribed into distinct fields:
   - `declared_nutrients_per_100g`
   - `declared_nutrients_per_serving`
   - `serving_size_declared`: verbatim text (e.g., `3 cookies (34g)`).
4. **Legibility Thresholds**:
   - `panel_verified_exact`: All numeric values clearly readable without ambiguity.
   - `panel_verified_partial`: Certain lines blurred; legible lines recorded, blurred lines set to `null` (not 0.0).
   - `panel_not_legible`: Text too low-resolution or out of focus; declared nutrients recorded as `{}`.
5. **Zero vs. Missing**:
   - If a package states `Fat 0g` or `Sodium 0mg`, record as `0.0`.
   - If a nutrient is absent from the printed panel, omit the key or record `null`. Never record `0.0` for an undeclared field.

---

## 4. Cryptographic Freezing & Checkpointing Protocol

Before executing any evaluation code:

1. **Format Specifications**:
   The holdout ground truth must adhere to `tests/fixtures/holdout_v1/ground_truth.json` schema.
2. **SHA-256 Manifest Generation**:
   A cryptographic manifest (`manifest.sha256`) must be generated for all images and the ground-truth JSON:
   ```powershell
   Get-FileHash tests/fixtures/holdout_v1/* -Algorithm SHA256 > tests/fixtures/holdout_v1/manifest.sha256
   ```
3. **Git Tagging**:
   The dataset and manifest must be committed to Git and tagged:
   ```powershell
   git tag -a holdout-v1-frozen -m "Cryptographically frozen holdout dataset v1 (50 images)"
   ```

---

## 5. Single-Pass Execution & Anti-Overfitting Governance

To prevent benchmark degradation:

1. **Single-Pass Evaluation**:
   The engine must be run exactly once against the frozen holdout set:
   ```powershell
   python scripts/run_reproducible_benchmark.py --gt tests/fixtures/holdout_v1/ground_truth.json --out-json reports/evaluation/holdout_v1_evaluation.json
   ```
2. **Prohibition of Holdout Tuning**:
   Engine extraction logic, regexes, dictionaries, and model weights must **NEVER** be modified in response to holdout errors.
3. **Holdout Retirement**:
   Once a holdout dataset has been evaluated and its detailed error cases analyzed, it transitions into the **Development / Regression Pool**. Future releases must be validated against a newly acquired holdout set (`holdout_v2`).

---

## 6. Official Acceptance Quality Gates

A release is certified for production deployment only if it meets all minimum criteria on the pristine holdout dataset:

| Quality Gate | Minimum Target | Rationale |
|---|---|---|
| **Overall Field Recall** | $\ge \mathbf{80.0\%}$ | Minimizes missing critical nutritional information. |
| **Overall Field Precision** | $\ge \mathbf{80.0\%}$ | Prevents dangerous nutritional hallucinations or false extractions. |
| **Core Nutrient Recall** | $\ge \mathbf{85.0\%}$ | Enforces high reliability on mandatory macro nutrients. |
| **Serving Basis Accuracy** | $\ge \mathbf{85.0\%}$ | Prevents catastrophic per-serving vs per-100g column inversion. |
| **Packet-Level Accuracy** | $\ge \mathbf{60.0\%}$ | Packages where every declared nutrient is 100% correct. |
| **Mean Latency (CPU)** | $\le \mathbf{15.0\text{ s}}$ | Acceptable response time for consumer mobile workflow. |
| **Peak Memory Utilization** | $\le \mathbf{1,200\text{ MB}}$ | Prevents low-memory termination on client devices / container hosts. |
