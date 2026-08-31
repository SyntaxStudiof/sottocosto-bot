"""Pipeline di arricchimento, validazione e approvazione automatica delle offerte.

Non chiama Gemini: lavora sui dati estratti da ai_offer_parser e applica
link affiliato, arricchimento mirato e regole di approvazione automatica.
REGOLA IMMAGINI: si accettano SOLO immagini dai CDN Amazon.
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.request
from bs4 import BeautifulSoup

import config
from utils import clean_title

log = logging.getLogger("auto_approval")

AFFILIATE_TAG = getattr(config, "AFFILIATE_TAG", "sottocostoclu-21")
MIN_DISCOUNT = getattr(config, "MIN_DISCOUNT_PERCENT", 20)
AUTO_APPROVAL_ENABLED = getattr(config, "AUTO_APPROVAL_ENABLED", True)
DEDUP_ORE = getattr(config, "DEDUP_ORE", 48)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.IGNORECASE)

# --- WHITELIST IMMAGINI: solo CDN Amazon ---
AMAZON_IMG_DOMAINS = (
    "m.media-amazon.com",
    "images-na.ssl-images-amazon.com",
    "images-eu.ssl-images-amazon.com",
)


def _is_amazon_image(url: Optional[str]) -> bool:
    return bool(url) and any(d in url for d in AMAZON_IMG_DOMAINS)


def _http_get(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "it-IT,it;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        log.warning("HTTP GET fallita su %s: %s", url, e)
        return None


def extract_asin(url: str) -> Optional[str]:
    m = ASIN_RE.search(url or "")
    return m.group(1).upper() if m else None


def resolve_short_link(url: str) -> Optional[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.geturl()
    except Exception as e:
        log.warning("Risoluzione short link fallita per %s: %s", url, e)
        return None


def build_affiliate_link(url_or_asin: Optional[str]) -> Optional[str]:
    if not url_or_asin:
        return None
    s = url_or_asin.strip()
    if re.fullmatch(r"[A-Z0-9]{10}", s, re.IGNORECASE):
        asin = s.upper()
    else:
        asin = extract_asin(s)
    if not asin:
        return None
    return f"https://www.amazon.it/dp/{asin}?tag={AFFILIATE_TAG}"


def _immagine_alta_qualita(url: str) -> str:
    if not url:
        return url
    return re.sub(r'\._[A-Za-z0-9_,]+_\.', '.', url)


def estrai_dati_da_html(html: str) -> Dict[str, Optional[str]]:
    """Estrae titolo e immagine dall'HTML già scaricato (senza richieste HTTP)."""
    out = {"immagine_url": None, "titolo": None}
    if not html:
        return out

    soup = BeautifulSoup(html, 'html.parser')

    h1 = soup.find('h1', id='title')
    if h1:
        out["titolo"] = h1.get_text(strip=True)
    else:
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            out["titolo"] = og['content']

    main_img = soup.find('img', id='landingImage')
    if main_img and main_img.get('src'):
        out["immagine_url"] = main_img['src']
    else:
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            out["immagine_url"] = og_img['content']

    return out


def fetch_amazon_meta(asin: str) -> Dict[str, Optional[str]]:
    out = {"immagine_url": None, "titolo": None}
    html_bytes = _http_get(f"https://www.amazon.it/dp/{asin}")
    if not html_bytes:
        return out
    return estrai_dati_da_html(html_bytes.decode("utf-8", errors="ignore"))


def _aggiorna_eur(res: Dict[str, Any]) -> None:
    if res.get("prezzo_scontato") is not None:
        res["prezzo_scontato_eur"] = f"{res['prezzo_scontato']:.2f}".replace(".", ",")
    if res.get("prezzo_pieno") is not None:
        res["prezzo_pieno_eur"] = f"{res['prezzo_pieno']:.2f}".replace(".", ",")


def _pulisci_immagine(res: Dict[str, Any], html: str) -> None:
    """Accetta SOLO immagini Amazon; altrimenti prova dalla pagina; se nulla, None."""
    if not _is_amazon_image(res.get("immagine_url")):
        res["immagine_url"] = None
    if not res.get("immagine_url") and res.get("asin"):
        meta = estrai_dati_da_html(html) if html else fetch_amazon_meta(res["asin"])
        cand = meta.get("immagine_url")
        if _is_amazon_image(cand):
            res["immagine_url"] = _immagine_alta_qualita(cand)
    if not _is_amazon_image(res.get("immagine_url")):
        res["immagine_url"] = None


def arricchisci_dati(dati: Dict[str, Any]) -> Dict[str, Any]:
    """Versione con eventuale richiesta HTTP (usata da /aggiungi su Render)."""
    res = dict(dati)

    if not res.get("asin") and res.get("link_originale"):
        link = res["link_originale"]
        asin = extract_asin(link)
        if not asin and ("amzn.to" in link or "amzn.eu" in link):
            finale = resolve_short_link(link)
            if finale:
                asin = extract_asin(finale)
        res["asin"] = asin

    res["link_affiliato"] = build_affiliate_link(res.get("asin"))

    if res.get("prezzo_pieno") is None and res.get("prezzo_scontato") and res.get("sconto_percent") and res["sconto_percent"] < 100:
        res["prezzo_pieno"] = round(res["prezzo_scontato"] / (1 - res["sconto_percent"] / 100), 2)

    if res.get("sconto_percent") is None and res.get("prezzo_scontato") and res.get("prezzo_pieno") and res["prezzo_pieno"] > 0:
        res["sconto_percent"] = round((1 - res["prezzo_scontato"] / res["prezzo_pieno"]) * 100)

    # Titolo mancante -> dalla pagina Amazon
    if res.get("asin") and not res.get("titolo"):
        meta = fetch_amazon_meta(res["asin"])
        if meta.get("titolo"):
            res["titolo"] = clean_title(meta["titolo"])

    # Immagine: SOLO Amazon
    _pulisci_immagine(res, "")

    _aggiorna_eur(res)
    return res


def arricchisci_dati_da_html(dati: Dict[str, Any], html: str) -> Dict[str, Any]:
    """Versione che usa l'HTML già scaricato (usata dal monitor su Actions)."""
    res = dict(dati)

    if not res.get("asin") and res.get("link_originale"):
        link = res["link_originale"]
        asin = extract_asin(link)
        if not asin and ("amzn.to" in link or "amzn.eu" in link):
            finale = resolve_short_link(link)
            if finale:
                asin = extract_asin(finale)
        res["asin"] = asin

    res["link_affiliato"] = build_affiliate_link(res.get("asin"))

    if res.get("prezzo_pieno") is None and res.get("prezzo_scontato") and res.get("sconto_percent") and res["sconto_percent"] < 100:
        res["prezzo_pieno"] = round(res["prezzo_scontato"] / (1 - res["sconto_percent"] / 100), 2)

    if res.get("sconto_percent") is None and res.get("prezzo_scontato") and res.get("prezzo_pieno") and res["prezzo_pieno"] > 0:
        res["sconto_percent"] = round((1 - res["prezzo_scontato"] / res["prezzo_pieno"]) * 100)

    if res.get("asin") and not res.get("titolo"):
        meta = estrai_dati_da_html(html)
        if meta.get("titolo"):
            res["titolo"] = clean_title(meta["titolo"])

    # Immagine: SOLO Amazon, presa dall'HTML già scaricato
    _pulisci_immagine(res, html)

    _aggiorna_eur(res)
    return res


def asin_recenti_dal_foglio(righe: List[Dict[str, Any]], ore: int = DEDUP_ORE) -> Set[str]:
    out: Set[str] = set()
    soglia = datetime.now(timezone.utc) - timedelta(hours=ore)
    stati = {"NUOVO", "APPROVATO", "PUBBLICATO"}
    for r in righe:
        stato = (r.get("stato") or "").strip().upper()
        if stato not in stati:
            continue
        asin = (r.get("ASIN") or "").strip().upper()
        if not asin:
            continue
        try:
            dt = datetime.fromisoformat((r.get("aggiunto_il") or "").replace("Z", "+00:00"))
        except Exception:
            dt = None
        if dt is None or dt >= soglia:
            out.add(asin)
    return out


def valida_offerta(dati: Dict[str, Any], asin_recenti: Set[str]) -> Tuple[bool, List[str]]:
    motivi: List[str] = []
    if not AUTO_APPROVAL_ENABLED:
        motivi.append("auto-approvazione disabilitata")
    if len((dati.get("titolo") or "").strip()) < 6:
        motivi.append("titolo mancante o troppo corto")
    if not dati.get("asin"):
        motivi.append("ASIN mancante")
    elif dati["asin"] in asin_recenti:
        motivi.append("duplicato nelle ultime %d ore" % DEDUP_ORE)
    if not dati.get("link_affiliato"):
        motivi.append("link affiliato non costruibile")
    ps, pp = dati.get("prezzo_scontato"), dati.get("prezzo_pieno")
    if not ps or ps <= 0:
        motivi.append("prezzo scontato mancante")
    if not pp or pp <= 0:
        motivi.append("prezzo pieno mancante")
    if ps and pp and ps >= pp:
        motivi.append("prezzo scontato non inferiore al pieno")
    sconto = dati.get("sconto_percent")
    if sconto is None or sconto < MIN_DISCOUNT:
        motivi.append("sconto sotto soglia (%d%%)" % MIN_DISCOUNT)
    if not _is_amazon_image(dati.get("immagine_url")):
        motivi.append("immagine Amazon mancante")
    return (len(motivi) == 0, motivi)


async def processa_testo_offerta(
    testo: str, righe_foglio: List[Dict[str, Any]], fonte: str = "canale_terzo"
) -> Dict[str, Any]:
    from ai_offer_parser import parse_offerta_da_testo

    dati = await parse_offerta_da_testo(testo)
    dati = await asyncio.to_thread(arricchisci_dati, dati)
    ok, motivi = valida_offerta(dati, asin_recenti_dal_foglio(righe_foglio))
    return {"auto_approvata": ok, "motivi": motivi, "dati": dati, "fonte": fonte}
