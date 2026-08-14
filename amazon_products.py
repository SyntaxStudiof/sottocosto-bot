import random
import csv
from io import StringIO
import os
from urllib.request import urlopen

from config import MIN_DISCOUNT_PERCENT

# URL del foglio Google Sheets esportato come CSV
SHEET_URL = os.environ.get("GOOGLE_SHEET_CSV_URL", "")


def fetch_products_from_sheet():
    """Legge i prodotti dal Google Sheet CSV."""
    if not SHEET_URL:
        return []
    
    try:
        with urlopen(SHEET_URL) as response:
            csv_text = response.read().decode('utf-8')
        
        products = []
        reader = csv.DictReader(StringIO(csv_text))
        for row in reader:
            if not row.get('titolo'):  # salta righe vuote
                continue
            
            product = {
                "title": row.get('titolo', '').strip(),
                "price": float(row.get('prezzo', 0).replace(',', '.')),
                "old_price": float(row.get('prezzo_originale', 0).replace(',', '.')),
                "discount_percent": int(row.get('sconto_percento', 0)),
                "image_url": row.get('immagine_url', '').strip(),
                "affiliate_link": row.get('link_affiliato', '').strip(),
                "is_bestseller": True,
            }
            products.append(product)
        
        return products
    except Exception as e:
        print(f"Errore nel leggere il foglio: {e}")
        return []


def get_deals(min_discount=MIN_DISCOUNT_PERCENT, bestseller_only=False):
    products = fetch_products_from_sheet()
    results = [
        p for p in products
        if p["discount_percent"] >= min_discount
        and (not bestseller_only or p["is_bestseller"])
    ]
    return results


def pick_next_product():
    candidates = get_deals(bestseller_only=True)
    if not candidates:
        candidates = get_deals()
    if not candidates:
        return None
    return random.choice(candidates)
