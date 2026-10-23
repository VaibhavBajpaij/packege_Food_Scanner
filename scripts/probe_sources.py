import re
import requests

def probe_usda():
    print("=== Probing USDA Download Page ===")
    r = requests.get('https://fdc.nal.usda.gov/download-datasets/', timeout=20)
    links = re.findall(r'href=[\'"]([^\'"]+\.zip)[\'"]', r.text)
    for l in links:
        full = l if l.startswith('http') else f"https://fdc.nal.usda.gov{l}"
        print("USDA Zip:", full)

def probe_off():
    print("\n=== Probing Open Food Facts Data Page ===")
    r = requests.get('https://world.openfoodfacts.org/data', timeout=20)
    links = re.findall(r'href=[\'"]([^\'"]+(?:\.csv\.gz|\.parquet|\.jsonl\.gz))[\'"]', r.text)
    for l in set(links[:15]):
        print("OFF Dataset:", l)

if __name__ == '__main__':
    probe_usda()
    probe_off()
