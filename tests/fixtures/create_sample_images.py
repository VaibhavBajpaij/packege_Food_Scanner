"""Generate realistic packaged food label images with actual visible text pixels for testing.

Does NOT embed any hidden PNG metadata or ocr_text keys. All text is directly drawn onto
the image pixel raster using Pillow ImageDraw.
"""

from pathlib import Path
from PIL import Image, ImageDraw


def create_sample_label_images(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sample Biscuit Packet Label (rendered directly to pixels)
    biscuit_img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(biscuit_img)

    # Header banner
    draw.rectangle([20, 20, 780, 90], fill=(230, 240, 255), outline=(180, 200, 230))
    draw.text((40, 35), "PREMIUM WHOLE WHEAT CRUNCH BISCUITS", fill=(0, 50, 150))
    draw.text((40, 65), "Net Weight: 120g | Barcode: 8901030000001", fill=(60, 60, 60))

    biscuit_lines = [
        "INGREDIENTS: Whole Wheat Flour (62%), Vegetable Oil (Palm Oil, Antioxidant (E319)),",
        "Sugar, Invert Sugar Syrup, Raising Agents (INS 503(ii), INS 500(ii)),",
        "Milk Solids (1.5%), Iodised Salt, Emulsifier (Soy Lecithin INS 322).",
        "ALLERGEN DECLARATION: CONTAINS WHEAT (GLUTEN), MILK, AND SOY.",
        "MAY CONTAIN TRACES OF PEANUTS AND TREE NUTS.",
        "",
        "NUTRITION FACTS",
        "Serving Size: 30g",
        "Values per 100g:",
        "Energy: 460 kcal",
        "Protein: 7.5 g",
        "Total Carbohydrates: 68.0 g",
        "Total Sugars: 24.5 g",
        "Added Sugars: 22.0 g",
        "Dietary Fibre: 6.2 g",
        "Total Fat: 18.0 g",
        "Saturated Fat: 8.5 g",
        "Trans Fat: 0.0 g",
        "Sodium: 380 mg",
        "Salt: 0.95 g",
        "Iron: 4.2 mg",
        "Calcium: 85 mg",
    ]

    y = 110
    for line in biscuit_lines:
        if line.startswith("NUTRITION FACTS") or line.startswith("INGREDIENTS"):
            draw.text((40, y), line, fill=(0, 0, 0))
        elif line.startswith("ALLERGEN"):
            draw.text((40, y), line, fill=(180, 20, 20))
        else:
            draw.text((40, y), line, fill=(40, 40, 40))
        y += 32

    p1 = output_dir / "sample_biscuit_packet.png"
    # Save standard PNG with NO custom metadata
    biscuit_img.save(p1)

    # 2. Sample Juice Bottle Label (rendered directly to pixels)
    juice_img = Image.new("RGB", (800, 900), color=(255, 255, 255))
    draw2 = ImageDraw.Draw(juice_img)

    # Header banner
    draw2.rectangle([20, 20, 780, 90], fill=(255, 240, 220), outline=(230, 200, 180))
    draw2.text((40, 35), "PURE ORANGE & CARROT NECTAR", fill=(180, 70, 0))
    draw2.text((40, 65), "Volume: 250ml | Barcode: 8901040000002", fill=(60, 60, 60))

    juice_lines = [
        "INGREDIENTS: Water, Orange Juice Concentrate (40%), Carrot Puree (15%), Sugar, Vitamin C (Ascorbic Acid).",
        "ALLERGEN INFORMATION: No declared major allergens.",
        "",
        "NUTRITION INFORMATION per 100 ml:",
        "Energy: 48 kcal",
        "Protein: 0.6 g",
        "Total Carbohydrates: 11.4 g",
        "Total Sugars: 10.8 g",
        "Total Fat: 0.1 g",
        "Saturated Fat: 0.0 g",
        "Sodium: 15 mg",
        "Vitamin C: 24 mg",
    ]

    y = 110
    for line in juice_lines:
        if line.startswith("NUTRITION") or line.startswith("INGREDIENTS"):
            draw2.text((40, y), line, fill=(0, 0, 0))
        else:
            draw2.text((40, y), line, fill=(40, 40, 40))
        y += 35

    p2 = output_dir / "sample_juice_bottle.png"
    # Save standard PNG with NO custom metadata
    juice_img.save(p2)

    print(f"Created sample food label test images in {output_dir} (pixels only, no metadata)")
    return [p1, p2]


if __name__ == "__main__":
    create_sample_label_images(Path(__file__).resolve().parent)
