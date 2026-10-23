"""Generate realistic packaged food label images with embedded PNG metadata for deterministic test validation."""

from pathlib import Path
from PIL import Image, ImageDraw, PngImagePlugin


def create_sample_label_images(output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sample Biscuit Packet Label
    biscuit_img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(biscuit_img)
    draw.rectangle([20, 20, 780, 80], fill=(230, 240, 255))
    draw.text((40, 35), "PREMIUM WHOLE WHEAT CRUNCH BISCUITS", fill=(0, 50, 150))
    draw.text((40, 60), "Net Weight: 120g | Barcode: 8901030000001", fill=(80, 80, 80))

    biscuit_text = (
        "PREMIUM WHOLE WHEAT CRUNCH BISCUITS\n"
        "Net Weight: 120g | Barcode: 8901030000001\n"
        "INGREDIENTS: Whole Wheat Flour (62%), Vegetable Oil (Palm Oil, Antioxidant (E319)), "
        "Sugar, Invert Sugar Syrup, Raising Agents (INS 503(ii), INS 500(ii)), "
        "Milk Solids (1.5%), Iodised Salt, Emulsifier (Soy Lecithin INS 322).\n"
        "ALLERGEN DECLARATION: CONTAINS WHEAT (GLUTEN), MILK, AND SOY.\n"
        "MAY CONTAIN TRACES OF PEANUTS AND TREE NUTS.\n"
        "NUTRITION FACTS\n"
        "Serving Size: 30g\n"
        "Values per 100g:\n"
        "Energy: 460 kcal\n"
        "Protein: 7.5 g\n"
        "Total Carbohydrates: 68.0 g\n"
        "Total Sugars: 24.5 g\n"
        "Added Sugars: 22.0 g\n"
        "Dietary Fibre: 6.2 g\n"
        "Total Fat: 18.0 g\n"
        "Saturated Fat: 8.5 g\n"
        "Trans Fat: 0.0 g\n"
        "Sodium: 380 mg\n"
        "Salt: 0.95 g\n"
        "Iron: 4.2 mg\n"
        "Calcium: 85 mg\n"
    )

    info1 = PngImagePlugin.PngInfo()
    info1.add_text("ocr_text", biscuit_text)
    p1 = output_dir / "sample_biscuit_packet.png"
    biscuit_img.save(p1, pnginfo=info1)

    # 2. Sample Juice Bottle Label
    juice_img = Image.new("RGB", (800, 900), color=(255, 255, 255))
    draw2 = ImageDraw.Draw(juice_img)
    draw2.rectangle([20, 20, 780, 80], fill=(255, 240, 220))
    draw2.text((40, 35), "PURE ORANGE & CARROT NECTAR", fill=(180, 70, 0))

    juice_text = (
        "PURE ORANGE & CARROT NECTAR\n"
        "Volume: 250ml | Barcode: 8901040000002\n"
        "INGREDIENTS: Water, Orange Juice Concentrate (40%), Carrot Puree (15%), Sugar, Vitamin C (Ascorbic Acid).\n"
        "ALLERGEN INFORMATION: No declared major allergens.\n"
        "NUTRITION INFORMATION per 100 ml:\n"
        "Energy: 48 kcal\n"
        "Protein: 0.6 g\n"
        "Total Carbohydrates: 11.4 g\n"
        "Total Sugars: 10.8 g\n"
        "Total Fat: 0.1 g\n"
        "Saturated Fat: 0.0 g\n"
        "Sodium: 15 mg\n"
        "Vitamin C: 24 mg\n"
    )
    info2 = PngImagePlugin.PngInfo()
    info2.add_text("ocr_text", juice_text)
    p2 = output_dir / "sample_juice_bottle.png"
    juice_img.save(p2, pnginfo=info2)

    print(f"Created sample food label test images in {output_dir}")
    return [p1, p2]


if __name__ == "__main__":
    create_sample_label_images(Path(__file__).resolve().parent)
