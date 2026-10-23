# Nutrient Normalization & Database Audit Report

- **Audit Timestamp**: `2026-10-23T23:52:31.755730`

## 1. Open Food Facts Packaged Products Audit
- **Total Indexed Packaged Products**: `16592`
- **Products with Declared Energy**: `15753` (94.9%)
- **Products with Declared Protein**: `15712` (94.7%)
- **Products with Declared Carbohydrates**: `15723` (94.8%)
- **Products with Declared Fat**: `15725` (94.8%)
- **Products with Declared Sodium / Salt**: `15576` (93.9%)

## 2. Reference Databases Audit
- **USDA FoodData Central Foundation Foods**: `68875` analytical food items
- **Indian Food Composition Tables (IFCT 2017)**: `12` core composite items

## 3. Mathematical Sanity Checks & Rules Enforced
1. **Non-negativity**: All nutrient amounts must be `>= 0`.
2. **Mass Balance**: In solid food per 100g, the sum of `(protein + total_fat + carbohydrates + dietary_fibre + ash/minerals + water)` cannot exceed 100g plus analytical measurement tolerance (~105g).
3. **Sodium/Salt Determinism**: Where one is absent, `salt_g = (sodium_mg / 1000) * 2.5` and `sodium_mg = salt_g * 1000 * 0.4`.
4. **Missing Value Integrity**: If a nutrient is absent on a label, it is recorded as `status: missing` and never imputed as `0.0`.
