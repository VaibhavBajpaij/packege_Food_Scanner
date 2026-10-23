"""Inspect detailed OCR text for each of the 22 real photos."""
import json
from pathlib import Path

bench_path = Path("reports/evaluation/real_photos_ocr_benchmark.json")
data = json.loads(bench_path.read_text(encoding="utf-8"))

print(f"{'ID':<14} | {'Lines':<5} | {'Product Name':<30} | Top Recognized Lines")
print("-" * 100)
for r in data["detailed_results"]:
    top_3 = " // ".join(r.get("first_3_lines", []))
    print(f"{r['sample_id']:<14} | {r['line_count']:<5} | {r['product_name'][:30]:<30} | {top_3[:60]}")
