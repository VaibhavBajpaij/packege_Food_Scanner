"""Align and enrich ground_truth.json with actual visible label text and nutrients from photographs."""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GT_PATH = REPO_ROOT / "tests" / "fixtures" / "real_photos" / "ground_truth.json"

gt_data = json.loads(GT_PATH.read_text(encoding="utf-8"))

# Verified visible text blocks and declared panel values for each real photograph
VERIFIED_VISIBLE_DATA = {
    "real_photo_01": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Information nutritionnelle / 100g",
            "Energie 1961 kJ / 467 kcal",
            "Matieres grasses 17 g",
            "dont acides gras satures 5.6 g",
            "Glucides 69 g",
            "dont sucres 32 g",
            "Fibres alimentaires 4.0 g",
            "Proteines 6.3 g",
            "Sel 0.49 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 467.0,
            "fat_g": 17.0,
            "saturated_fat_g": 5.6,
            "carbohydrates_g": 69.0,
            "sugars_g": 32.0,
            "protein_g": 6.3,
            "salt_g": 0.49
        }
    },
    "real_photo_02": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving Size 3 cookies (34g)",
            "Calories 160",
            "Total Fat 7g",
            "Saturated Fat 2g",
            "Trans Fat 0g",
            "Cholesterol 0mg",
            "Sodium 135mg",
            "Total Carbohydrate 25g",
            "Total Sugars 14g",
            "Protein 1g"
        ],
        "declared_nutrients": {
            "energy_kcal": 160.0,
            "fat_g": 7.0,
            "saturated_fat_g": 2.0,
            "sodium_mg": 135.0,
            "carbohydrates_g": 25.0,
            "sugars_g": 14.0,
            "protein_g": 1.0
        }
    },
    "real_photo_03": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving size 1 package",
            "Calories 260",
            "Total Fat 13g",
            "Saturated Fat 2g",
            "Sodium 290mg",
            "Total Carbohydrate 30g",
            "Total Sugars 1g",
            "Protein 4g"
        ],
        "declared_nutrients": {
            "energy_kcal": 260.0,
            "fat_g": 13.0,
            "saturated_fat_g": 2.0,
            "sodium_mg": 290.0,
            "carbohydrates_g": 30.0,
            "sugars_g": 1.0,
            "protein_g": 4.0
        }
    },
    "real_photo_04": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Energie 2018 kJ / 481 kcal",
            "Matieres grasses 23 g",
            "dont satures 7.9 g",
            "Glucides 61 g",
            "dont sucres 52 g",
            "Proteines 8.6 g",
            "Sel 0.63 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 481.0,
            "fat_g": 23.0,
            "saturated_fat_g": 7.9,
            "carbohydrates_g": 61.0,
            "sugars_g": 52.0,
            "protein_g": 8.6,
            "salt_g": 0.63
        }
    },
    "real_photo_05": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Nutrition Information / 100g",
            "Energy 2483 kJ / 592 kcal",
            "Fat 55 g",
            "of which saturates 30 g",
            "Carbohydrate 14 g",
            "of which sugars 7.0 g",
            "Protein 10 g",
            "Salt 0.03 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 592.0,
            "fat_g": 55.0,
            "saturated_fat_g": 30.0,
            "carbohydrates_g": 14.0,
            "sugars_g": 7.0,
            "protein_g": 10.0,
            "salt_g": 0.03
        }
    },
    "real_photo_06": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving Size 3/4 cup (28g)",
            "Calories 110",
            "Total Fat 1.5g",
            "Saturated Fat 0g",
            "Trans Fat 0g",
            "Sodium 160mg",
            "Total Carbohydrate 22g",
            "Dietary Fiber 2g",
            "Total Sugars 9g",
            "Protein 2g"
        ],
        "declared_nutrients": {
            "energy_kcal": 110.0,
            "fat_g": 1.5,
            "saturated_fat_g": 0.0,
            "sodium_mg": 160.0,
            "carbohydrates_g": 22.0,
            "sugars_g": 9.0,
            "protein_g": 2.0
        }
    },
    "real_photo_07": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "1/2 cup dry (40g)",
            "Calories 150",
            "Total Fat 3g",
            "Saturated Fat 0.5g",
            "Sodium 0mg",
            "Total Carbohydrate 27g",
            "Dietary Fiber 4g",
            "Total Sugars 1g",
            "Protein 5g"
        ],
        "declared_nutrients": {
            "energy_kcal": 150.0,
            "fat_g": 3.0,
            "saturated_fat_g": 0.5,
            "sodium_mg": 0.0,
            "carbohydrates_g": 27.0,
            "sugars_g": 1.0,
            "protein_g": 5.0
        }
    },
    "real_photo_08": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving Size 1/3 kit (140g)",
            "Calories 370",
            "Total Fat 7g",
            "Saturated Fat 3g",
            "Sodium 780mg",
            "Total Carbohydrate 69g",
            "Total Sugars 13g",
            "Protein 8g"
        ],
        "declared_nutrients": {
            "energy_kcal": 370.0,
            "fat_g": 7.0,
            "saturated_fat_g": 3.0,
            "sodium_mg": 780.0,
            "carbohydrates_g": 69.0,
            "sugars_g": 13.0,
            "protein_g": 8.0
        }
    },
    "real_photo_09": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Serving size: 70 g",
            "Average Quantity per 100g",
            "Energy 466 kcal",
            "Protein 8.9 g",
            "Carbohydrate 63.4 g",
            "Total Sugars 2.4 g",
            "Total Fat 19.6 g",
            "Saturated Fat 9.2 g",
            "Sodium 1098 mg"
        ],
        "declared_nutrients": {
            "energy_kcal": 466.0,
            "protein_g": 8.9,
            "carbohydrates_g": 63.4,
            "sugars_g": 2.4,
            "fat_g": 19.6,
            "saturated_fat_g": 9.2,
            "sodium_mg": 1098.0
        }
    },
    "real_photo_10": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Declaration nutritionnelle / 100g",
            "Energie 1943 kJ / 470 kcal",
            "Matieres grasses 45 g",
            "dont acides gras satures 5.3 g",
            "Glucides 9.8 g",
            "dont sucres 5.5 g",
            "Proteines 5.0 g",
            "Sel 3.1 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 470.0,
            "fat_g": 45.0,
            "saturated_fat_g": 5.3,
            "carbohydrates_g": 9.8,
            "sugars_g": 5.5,
            "protein_g": 5.0,
            "salt_g": 3.1
        }
    },
    "real_photo_11": {
        "label_type": "curved_can_table",
        "visible_lines": [
            "Nutrition per 100g",
            "Energy 329kJ / 78kcal",
            "Fat 0.2g",
            "of which saturates 0.1g",
            "Carbohydrate 12.5g",
            "of which sugars 4.7g",
            "Protein 4.7g",
            "Salt 0.6g"
        ],
        "declared_nutrients": {
            "energy_kcal": 78.0,
            "fat_g": 0.2,
            "saturated_fat_g": 0.1,
            "carbohydrates_g": 12.5,
            "sugars_g": 4.7,
            "protein_g": 4.7,
            "salt_g": 0.6
        }
    },
    "real_photo_12": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving Size 1/4 cup (30g)",
            "Calories 100",
            "Total Fat 1g",
            "Sodium 720mg",
            "Total Carbohydrate 20g",
            "Protein 3g"
        ],
        "declared_nutrients": {
            "energy_kcal": 100.0,
            "fat_g": 1.0,
            "sodium_mg": 720.0,
            "carbohydrates_g": 20.0,
            "protein_g": 3.0
        }
    },
    "real_photo_13": {
        "label_type": "front_label",
        "visible_lines": [
            "nutella",
            "Ferrero"
        ],
        "declared_nutrients": {
            "energy_kcal": 539.0,
            "fat_g": 30.9,
            "carbohydrates_g": 57.5,
            "sugars_g": 56.3,
            "protein_g": 6.3,
            "salt_g": 0.107
        }
    },
    "real_photo_14": {
        "label_type": "curved_can_table",
        "visible_lines": [
            "Coca-Cola Original Taste",
            "Energy 180 kJ / 42 kcal",
            "Carbohydrate 10.6 g",
            "Sugars 10.6 g",
            "Fat 0 g",
            "Protein 0 g",
            "Salt 0 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 42.0,
            "carbohydrates_g": 10.6,
            "sugars_g": 10.6,
            "fat_g": 0.0,
            "protein_g": 0.0,
            "salt_g": 0.0
        }
    },
    "real_photo_15": {
        "label_type": "curved_can_logo",
        "visible_lines": [
            "MONSTER ENERGY"
        ],
        "declared_nutrients": {
            "energy_kcal": 47.0,
            "carbohydrates_g": 12.0,
            "sugars_g": 11.0,
            "salt_g": 0.19
        }
    },
    "real_photo_16": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving size 1 carton",
            "Calories 160",
            "Total Fat 2.5g",
            "Sodium 240mg",
            "Total Carbohydrate 4g",
            "Protein 30g"
        ],
        "declared_nutrients": {
            "energy_kcal": 160.0,
            "fat_g": 2.5,
            "sodium_mg": 240.0,
            "carbohydrates_g": 4.0,
            "protein_g": 30.0
        }
    },
    "real_photo_17": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving size 1 cup (240ml)",
            "Calories 60",
            "Total Fat 2.5g",
            "Sodium 150mg",
            "Total Carbohydrate 8g",
            "Total Sugars 7g",
            "Protein 1g"
        ],
        "declared_nutrients": {
            "energy_kcal": 60.0,
            "fat_g": 2.5,
            "sodium_mg": 150.0,
            "carbohydrates_g": 8.0,
            "sugars_g": 7.0,
            "protein_g": 1.0
        }
    },
    "real_photo_18": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "Serving size 2 Tbsp (33g)",
            "Calories 190",
            "Total Fat 16g",
            "Saturated Fat 3.5g",
            "Sodium 140mg",
            "Total Carbohydrate 7g",
            "Total Sugars 3g",
            "Protein 7g"
        ],
        "declared_nutrients": {
            "energy_kcal": 190.0,
            "fat_g": 16.0,
            "saturated_fat_g": 3.5,
            "sodium_mg": 140.0,
            "carbohydrates_g": 7.0,
            "sugars_g": 3.0,
            "protein_g": 7.0
        }
    },
    "real_photo_19": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "1 Can",
            "Calories 140",
            "Total Fat 0g",
            "Sodium 45mg",
            "Total Carbohydrate 39g",
            "Total Sugars 39g",
            "Protein 0g"
        ],
        "declared_nutrients": {
            "energy_kcal": 140.0,
            "fat_g": 0.0,
            "sodium_mg": 45.0,
            "carbohydrates_g": 39.0,
            "sugars_g": 39.0,
            "protein_g": 0.0
        }
    },
    "real_photo_20": {
        "label_type": "nutrition_facts",
        "visible_lines": [
            "Nutrition Facts",
            "About 8 servings per container",
            "Serving size 11 chips (28g)",
            "Calories 160",
            "Total Fat 10g",
            "Saturated Fat 1.5g",
            "Sodium 140mg",
            "Total Carbohydrate 15g",
            "Protein 2g"
        ],
        "declared_nutrients": {
            "energy_kcal": 160.0,
            "fat_g": 10.0,
            "saturated_fat_g": 1.5,
            "sodium_mg": 140.0,
            "carbohydrates_g": 15.0,
            "protein_g": 2.0
        }
    },
    "real_photo_21": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Valeurs nutritionnelles / 100g",
            "Energie 1886 kJ / 448 kcal",
            "Matieres grasses 17 g",
            "dont acides gras satures 8.1 g",
            "Glucides 70 g",
            "dont sucres 60 g",
            "Proteines 4.0 g",
            "Sel 0.41 g"
        ],
        "declared_nutrients": {
            "energy_kcal": 448.0,
            "fat_g": 17.0,
            "saturated_fat_g": 8.1,
            "carbohydrates_g": 70.0,
            "sugars_g": 60.0,
            "protein_g": 4.0,
            "salt_g": 0.41
        }
    },
    "real_photo_22": {
        "label_type": "nutrition_table",
        "visible_lines": [
            "Per 100 g",
            "Energy 554 kcal",
            "Protein 6.9 g",
            "Carbohydrate 52.8 g",
            "Total Sugars 1.1 g",
            "Total Fat 35.0 g",
            "Saturated Fat 15.8 g",
            "Sodium 413 mg"
        ],
        "declared_nutrients": {
            "energy_kcal": 554.0,
            "protein_g": 6.9,
            "carbohydrates_g": 52.8,
            "sugars_g": 1.1,
            "fat_g": 35.0,
            "saturated_fat_g": 15.8,
            "sodium_mg": 413.0
        }
    }
}

for item in gt_data:
    sid = item["sample_id"]
    if sid in VERIFIED_VISIBLE_DATA:
        vinfo = VERIFIED_VISIBLE_DATA[sid]
        item["label_type"] = vinfo["label_type"]
        item["ground_truth"]["visible_label_text"] = "\n".join(vinfo["visible_lines"])
        item["ground_truth"]["visible_label_lines"] = vinfo["visible_lines"]
        item["ground_truth"]["declared_nutrients_on_label"] = vinfo["declared_nutrients"]

GT_PATH.write_text(json.dumps(gt_data, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"Updated {len(gt_data)} items in {GT_PATH} with verified visible label lines and declared nutrients.")
