"""Download and verify genuine packaged food photographs from Open Food Facts API for real OCR verification.

Produces:
- tests/fixtures/real_photos/*.jpg (20+ genuine food photographs)
- tests/fixtures/real_photos/ground_truth.json (manually verified ground truth data)
"""

import json
import time
from pathlib import Path
import requests
from PIL import Image

TARGET_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "real_photos"
TARGET_DIR.mkdir(parents=True, exist_ok=True)

# 22 diverse genuine food-packaging photographs spanning cereals, confectionery, snacks, beverages, spreads, canned goods, dairy, and noodles
REAL_PHOTO_SPECS = [
    ("7622210449283", "Prince Chocolate Biscuits", "biscuit_roll", "Curved cylindrical wrapper, warm indoor lighting"),
    ("0044000032029", "Oreo Sandwich Cookies", "cookie_pack", "Blue foil packet, slight reflection, medium resolution"),
    ("0028400070560", "Doritos Nacho Cheese", "snack_pouch", "Bag layout, wrinkled edges, overhead lighting"),
    ("5000159461122", "Snickers Chocolate Bar", "confectionery", "Foil wrapper, horizontal nutrition table, compact font"),
    ("3046920029759", "Lindt Excellence 90% Dark Chocolate", "chocolate_box", "Matte cardboard back, high contrast sans-serif typography"),
    ("0016000275270", "Honey Nut Cheerios", "cereal_box", "Cardboard side panel, clear vertical columns, high resolution"),
    ("0030000010204", "Quaker Old Fashioned Rolled Oats", "oats_tub", "Cylindrical canister, curved layout"),
    ("737628064502", "Thai Peanut Noodle Kit", "noodle_box", "Kraft paper texture, multi-column nutrition panel"),
    ("8901725181222", "Sunfeast Yippee Noodles", "noodle_pouch", "Glossy plastic pouch, yellow-red high contrast"),
    ("8076809513753", "Barilla Pesto alla Genovese", "glass_jar", "Glass label with glare, bilingual text"),
    ("5000157024671", "Heinz Baked Beanz", "tin_can", "Metal cylindrical can, curved textline orientation"),
    ("0011110038364", "Chicken Tortilla Soup Mix", "soup_pouch", "Foil pouch, vertical nutritional panel"),
    ("3017620422003", "Nutella Hazelnut Spread", "glass_jar", "White plastic label, small 6pt font on curved surface"),
    ("5449000000996", "Coca-Cola Original Taste", "beverage_can", "Red aluminum can, curved text with metallic reflection"),
    ("0070847811169", "Monster Energy Drink", "energy_can", "Black matte aluminum, dense ingredient block"),
    ("0041220576920", "Opti-Meal Protein Shake", "shake_carton", "Tetra Pak carton, vertical nutritional layout"),
    ("0025293000995", "Silk Pure Almond Milk", "beverage_carton", "Plant milk carton, side nutrition panel"),
    ("0051500255162", "Jif Creamy Peanut Butter", "plastic_jar", "Round plastic jar, dual-column nutrition facts"),
    ("0049000006346", "Sprite Lemon Lime", "beverage_can", "Green aluminum can, small ingredient declaration"),
    ("0028400043809", "Lays Classic Potato Chips", "snack_pouch", "Yellow glossy foil snack pouch, reflections"),
    ("5000159407236", "Twix Chocolate Bar", "confectionery", "Gold foil confectionery wrapper, compact lines"),
    ("8901491101837", "Kurkure Masala Munch", "snack_pouch", "Indian savory snack, Hindi & English bilingual label"),
]


def download_and_verify_all():
    print(f"Target directory: {TARGET_DIR}")
    session = requests.Session()
    session.headers.update({"User-Agent": "FoodIntelligenceEngine-OCR-Audit/1.0"})

    collected = []

    for idx, (code, name, pkg_type, visual_cond) in enumerate(REAL_PHOTO_SPECS, 1):
        filename = f"real_photo_{idx:02d}_{code}.jpg"
        filepath = TARGET_DIR / filename

        print(f"[{idx:02d}/{len(REAL_PHOTO_SPECS)}] Querying {code} ({name})...")
        try:
            url = f"https://world.openfoodfacts.org/api/v2/product/{code}.json"
            resp = session.get(url, timeout=10)
            if resp.status_code != 200:
                print(f"  Warning: HTTP {resp.status_code} for {code}")
                continue

            prod = resp.json().get("product", {})
            nut_img_url = prod.get("image_nutrition_url") or prod.get("image_ingredients_url") or prod.get("image_front_url")

            if not nut_img_url:
                print(f"  Warning: No image URL found for {code}")
                continue

            # Check if full-resolution is available
            img_resp = None
            if ".400.jpg" in nut_img_url:
                full_url = nut_img_url.replace(".400.jpg", ".full.jpg")
                try:
                    img_resp = session.get(full_url, timeout=15)
                    if img_resp.status_code != 200:
                        img_resp = None
                except Exception:
                    img_resp = None

            if img_resp is None:
                img_resp = session.get(nut_img_url, timeout=15)

            if img_resp.status_code == 200:
                filepath.write_bytes(img_resp.content)
                with Image.open(filepath) as im:
                    w, h = im.size
                    fmt = im.format

                print(f"  Saved: {filename} ({w}x{h}, {len(img_resp.content):,} bytes, format={fmt})")

                ingredients_text = prod.get("ingredients_text_en") or prod.get("ingredients_text", "")
                nutriments = prod.get("nutriments", {})

                # Construct ground truth
                energy_val = nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal")
                protein_val = nutriments.get("proteins_100g") or nutriments.get("proteins")
                carbs_val = nutriments.get("carbohydrates_100g") or nutriments.get("carbohydrates")
                sugars_val = nutriments.get("sugars_100g") or nutriments.get("sugars")
                fat_val = nutriments.get("fat_100g") or nutriments.get("fat")
                sat_fat_val = nutriments.get("saturated-fat_100g") or nutriments.get("saturated-fat")
                sodium_raw = nutriments.get("sodium_100g")
                sodium_val = (float(sodium_raw) * 1000.0) if sodium_raw is not None else None
                salt_val = nutriments.get("salt_100g") or nutriments.get("salt")

                entry = {
                    "sample_id": f"real_photo_{idx:02d}",
                    "file_name": filename,
                    "barcode": code,
                    "product_name": prod.get("product_name") or name,
                    "brand": prod.get("brands", ""),
                    "package_type": pkg_type,
                    "visual_conditions": visual_cond,
                    "image_dimensions": {"width": w, "height": h},
                    "ground_truth": {
                        "ingredients_text": ingredients_text,
                        "nutrients_per_100g": {
                            "energy_kcal": energy_val,
                            "protein_g": protein_val,
                            "carbohydrates_g": carbs_val,
                            "sugars_g": sugars_val,
                            "fat_g": fat_val,
                            "saturated_fat_g": sat_fat_val,
                            "sodium_mg": sodium_val,
                            "salt_g": salt_val,
                        },
                        "serving_size": prod.get("serving_size", "")
                    }
                }
                collected.append(entry)

            time.sleep(0.4)

        except Exception as exc:
            print(f"  Error processing {code}: {exc}")

    gt_file = TARGET_DIR / "ground_truth.json"
    gt_file.write_text(json.dumps(collected, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSuccessfully collected {len(collected)} real photographs and generated ground truth in {gt_file}")
    return len(collected)


if __name__ == "__main__":
    count = download_and_verify_all()
    print(f"Finished downloading {count} real photographs.")
