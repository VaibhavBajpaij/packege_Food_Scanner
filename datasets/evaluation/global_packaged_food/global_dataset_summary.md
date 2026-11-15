# Global Packaged Food Testing Dataset

**License:** Open Food Facts (ODbL 1.0) — **Strictly Commercially Permissible** for QA, Evaluation, and Testing.
**Total Products:** 19
**Regions Covered:** North America, Europe, Asia-Pacific, Global.
**Countries Covered:** Belgium, France, Germany, India, International / Global, Italy, United Kingdom, United Kingdom / EU, United States, United States / Global, United States / Thailand

## Product Manifest & Verified Ground Truth

| Sample ID | Barcode | Product Name | Country / Region | Energy (kcal) | Protein (g) | Carbs (g) | Fat (g) | Image File |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| global_01 | 0044000032029 | **oreo cookies shelf** | United States (North America) | 471.0 | 2.94 | 73.53 | 20.59 | `global_01_US_0044000032029.jpg` |
| global_02 | 0016000275270 | **Gmills hny nut cheerios swee** | United States (North America) | 393.0 | 7.14 | 78.57 | 5.36 | `global_02_US_0016000275270.jpg` |
| global_03 | 0028400070560 | **Nacho Cheese Flavored** | United States (North America) | 524.194 | 8.065 | 60.484 | 26.21 | `global_03_US_0028400070560.jpg` |
| global_04 | 0051500255162 | **Creamy Peanut Butter** | United States (North America) | 575.758 | 21.212 | 24.242 | 48.485 | `global_04_US_0051500255162.jpg` |
| global_05 | 0025293000995 | **Almondmilk** | United States (North America) | 80.0 | 1.0 | 14.0 | 2.0 | `global_05_US_0025293000995.jpg` |
| global_06 | 5000159461122 | **Snickers** | United Kingdom (Europe) | 481.0 | 8.6 | 60.5 | 22.5 | `global_06_GB_5000159461122.jpg` |
| global_07 | 5000157024671 | **Beanz in a rich tomato sauce** | United Kingdom (Europe) | 81.0 | 4.8 | 15.5 | 0.4 | `global_07_GB_5000157024671.jpg` |
| global_08 | 3046920029759 | **Excellence Noir Prodigieux 9** | France (Europe) | 592.0 | 10.0 | 14.0 | 55.0 | `global_08_FR_3046920029759.jpg` |
| global_09 | 3017620422003 | **Nutella** | France (Europe) | 539.0 | 6.3 | 57.5 | 30.9 | `global_09_FR_3017620422003.jpg` |
| global_10 | 7622210449283 | **Prince** | Belgium (Europe) | 467.0 | 6.3 | 69.0 | 17.0 | `global_10_BE_7622210449283.jpg` |
| global_11 | 4008400404127 | **Nutella Nuss-Nugat-Creme** | Germany (Europe) | 538.0 | 6.3 | 57.5 | 30.9 | `global_11_DE_4008400404127.jpg` |
| global_12 | 8076809513753 | **Barilla PESTO alla GENOVESE** | Italy (Europe) | 492.0 | 4.7 | 11.0 | 47.0 | `global_12_IT_8076809513753.jpg` |
| global_13 | 8901725181222 | **Yippee noodles** | India (Asia-Pacific) | 110.0 | 8.857 | 62.429 | 19.714 | `global_13_IN_8901725181222.jpg` |
| global_14 | 8901491101837 | **Lays Classics Salted 20rs** | India (Asia-Pacific) | 554.0 | 7.0 | 51.7 | 35.5 | `global_14_IN_8901491101837.jpg` |
| global_15 | 8901058017687 | **maggi** | India (Asia-Pacific) | 384.0 | 8.2 | 59.4 | 12.5 | `global_15_IN_8901058017687.jpg` |
| global_17 | 737628064502 | **Thai peanut noodle kit inclu** | United States / Thailand (Asia-Pacific) | 385.0 | 9.62 | 71.15 | 7.69 | `global_17_TH_737628064502.jpg` |
| global_18 | 5449000000996 | **Coca-Cola Original** | International / Global (Global) | 42.4 | - | 10.6 | - | `global_18_GLOBAL_5449000000996.jpg` |
| global_19 | 0070847811169 | **Monster Energy** | United States / Global (Global) | 48.608 | - | 12.258 | - | `global_19_GLOBAL_0070847811169.jpg` |
| global_20 | 5000159407236 | **Mars** | United Kingdom / EU (Europe) | 450.0 | 4.04 | 70.0 | 16.8 | `global_20_GB_5000159407236.jpg` |

## Usage in Testing Pipeline
Each sample has:
1. Genuine photographic packaging image downloaded locally to `images/`.
2. Verified EAN/UPC barcode for database lookup testing.
3. Ingredients statement for parser evaluation and allergen detection.
4. Standardized 100g nutritional profile for exact True Positive / False Positive OCR evaluation.
