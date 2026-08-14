import random
from config import MIN_DISCOUNT_PERCENT

_MOCK_PRODUCTS = [
    {
        "title": "ZOMFELT Zaino Ryanair 40x30x20, 24L Bagaglio a Mano Zaino da Viaggio Donna",
        "price": 23.14,
        "old_price": 29.99,
        "discount_percent": 23,
        "image_url": "https://placehold.co/400",
        "affiliate_link": "https://amzn.to/4x4MgY8",
        "is_bestseller": True,
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
