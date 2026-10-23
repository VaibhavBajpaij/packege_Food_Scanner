import re
import requests

def probe_off():
    r = requests.get('https://world.openfoodfacts.org/data', timeout=20)
    for line in r.text.splitlines():
        if 'href=' in line and any(ext in line for ext in ['.csv', '.parquet', '.jsonl', '.gz']):
            m = re.search(r'href=[\'"]([^\'"]+)[\'"]', line)
            if m:
                print('OFF candidate:', m.group(1))

if __name__ == '__main__':
    probe_off()
