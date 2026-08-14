import random
from config import MIN_DISCOUNT_PERCENT

_MOCK_PRODUCTS = [
    {
        "title": "Cuffie Bluetooth Over-Ear Cancellazione Rumore",
        "price": 39.99,
        "old_price": 69.99,
        "discount_percent": 43,
        "image_url": "https://placehold.co/400",
        "affiliate_link": "https://www.amazon.it/dp/ESEMPIO1?tag=TUOTAG-21",
        "is_bestseller": True,
    },
    {
        "title": "Friggitrice ad Aria 5.5L Digitale",
        "price": 59.90,
        "old_price": 89.90,
        "discount_percent": 33,
        "image_url": "https://placehold.co/400",
        "affiliate_link": "https://www.amazon.it/dp/ESEMPIO2?tag=TUOTAG-21",
        "is_bestseller": True,
    },
    {
        "title": "Power Bank 20000mAh Ricarica Rapida",
        "price": 19.99,
        "old_price": 29.99,
        "discount_percent": 33,
        "image_url": "https://placehold.co/400",
        "affiliate_link": "https://www.amazon.it/dp/ESEMPIO3?tag=TUOTAG-21",
        "is_bestseller": False,
    },
]


def get_deals(min_discount=MIN_DISCOUNT_PERCENT, bestseller_only=False):
    results = [
        p for p in _MOCK_PRODUCTS
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
