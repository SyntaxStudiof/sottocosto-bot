import requests
from auto_approval import arricchisci_dati_da_html, _is_amazon_image

LINK = "https://amzn.to/4iKo9JM"   # es. https://www.amazon.it/dp/B0XXXXXX

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
resp = requests.get(LINK, allow_redirects=True, timeout=15, headers=HEADERS)

dati = {
    "titolo": None,
    "prezzo_scontato": 26.99,
    "prezzo_pieno": 69.99,
    "sconto_percent": None,
    "asin": None,
    "immagine_url": "https://t.me/fake/immagine-con-logo.png",  # immagine "cattiva" simulata
    "link_originale": LINK,
}
out = arricchisci_dati_da_html(dati, resp.text)
print("Immagine finale:", out["immagine_url"])
print("E' un'immagine Amazon?", _is_amazon_image(out["immagine_url"]))
