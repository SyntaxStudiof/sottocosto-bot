"""Pipeline di arricchimento, validazione e approvazione automatica delle offerte.

Non chiama Gemini: lavora sui dati estratti da ai_offer_parser e applica
link affiliato, arricchimento mirato e regole di approvazione automatica.
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
    """Segue i redirect di un link breve (amzn.to/amzn.eu) e restituisce l'URL finale."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.geturl()
    except Exception as e:
        log.warning("Risoluzione short link fallita per %s: %s", url, e)
        return None


def build_affiliate_link(url_or_asin: Optional[str]) -> Optional[str]:
    """Costruisce un link affiliato pulito a partire da ASIN o URL Amazon."""
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
    """Rimuove i codici di thumbnail Amazon dai link immagine."""
    if not url:
        return url
    return re.sub(r'\._[A-Za-z0-9_,]+_\.', '.', url)


def estrai_dati_da_html(html: str) -> Dict[str, Optional[str]]:
    """Estrae titolo e immagine dall'HTML già scaricato (senza richieste HTTP)."""
    out = {"immagine_url": None, "titolo": None}
    if not html:
        return out
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Titolo
    h1 = soup.find('h1', id='title')
    if h1:
        out["titolo"] = h1.get_text(strip=True)
    else:
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            out["titolo"] = og['content']
    
    # Immagine
    main_img = soup.find('img', id='landingImage')
    if main_img and main_img.get('src'):
        out["immagine_url"] = _immagine_alta_qualita(main_img['src'])
    else:
        og_img = soup.find('meta', property='og:image')
        if og_img and og_img.get('content'):
            out["immagine_url"] = _immagine_alta_qualita(og_img['content'])
    
    return out


def fetch_amazon_meta(asin: str) -> Dict[str, Optional[str]]:
    """UNA sola lettura della pagina prodotto per ricavare immagine e titolo."""
    out = {"immagine_url": None, "titolo": None}
    html_bytes = _http_get(f"https://www.amazon.it/dp/{asin}")
    if not html_bytes:
        return out
    html = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html) or re.search(
        r'<meta\s+content="([^"]+)"\s+property="og:image"', html
    )
    if m:
        out["immagine_url"] = m.group(1)
    t = re.search(r'<span[^>]*id="productTitle"[^>]*>([^<]+)</span>', html) or re.search(
        r'<meta\s+property="og:title"\s+content="([^"]+)"', html
    )
    if t:
        out["titolo"] = t.group(1).strip()
    return out


def _aggiorna_eur(res: Dict[str, Any]) -> None:
    if res.get("prezzo_scontato") is not None:
        res["prezzo_scontato_eur"] = f"{res['prezzo_scontato']:.2f}".replace(".", ",")
    if res.get("prezzo_pieno") is not None:
        res["prezzo_pieno_eur"] = f"{res['prezzo_pieno']:.2f}".replace(".", ",")


def arricchisci_dati(dati: Dict[str, Any]) -> Dict[str, Any]:
    """Riempie i campi mancanti con calcoli o al massimo 1 richiesta mirata."""
    res = dict(dati)

    # 1. ASIN mancante ma link presente (risolve anche i link brevi)
    if not res.get("asin") and res.get("link_originale"):
        link = res["link_originale"]
        asin = extract_asin(link)
        if not asin and ("amzn.to" in link or "amzn.eu" in link):
            finale = resolve_short_link(link)
            if finale:
                asin = extract_asin(finale)
        res["asin"] = asin

    # 2. Link affiliato pulito
    res["link_affiliato"] = build_affiliate_link(res.get("asin"))

    # 3. Prezzo pieno mancante -> calcolo da scontato + sconto%
    if res.get("prezzo_pieno") is None and res.get("prezzo_scontato") and res.get("sconto_percent") and res["sconto_percent"] < 100:
        res["prezzo_pieno"] = round(res["prezzo_scontato"] / (1 - res["sconto_percent"] / 100), 2)

    # 4. Sconto mancante -> calcolo dai due prezzi
    if res.get("sconto_percent") is None and res.get("prezzo_scontato") and res.get("prezzo_pieno") and res["prezzo_pieno"] > 0:
        res["sconto_percent"] = round((1 - res["prezzo_scontato"] / res["prezzo_pieno"]) * 100)

    # 5. Titolo/immagine mancanti ma ASIN presente -> UNA richiesta mirata
    if res.get("asin") and (not res.get("immagine_url") or not res.get("titolo")):
        meta = fetch_amazon_meta(res["asin"])
        if not res.get("immagine_url") and meta.get("immagine_url"):
            res["immagine_url"] = meta["immagine_url"]
        if not res.get("titolo") and meta.get("titolo"):
            res["titolo"] = clean_title(meta["titolo"])

    _aggiorna_eur(res)
    return res


def arricchisci_dati_da_html(dati: Dict[str, Any], html: str) -> Dict[str, Any]:
    """Versione che usa l'HTML già scaricato invece di fare richieste HTTP."""
    res = dict(dati)

    # 1. ASIN mancante ma link presente
    if not res.get("asin") and res.get("link_originale"):
        link = res["link_originale"]
        asin = extract_asin(link)
        if not asin and ("amzn.to" in link or "amzn.eu" in link):
            finale = resolve_short_link(link)
            if finale:
                asin = extract_asin(finale)
        res["asin"] = asin

    # 2. Link affiliato pulito
    res["link_affiliato"] = build_affiliate_link(res.get("asin"))

    # 3. Prezzo pieno mancante -> calcolo da scontato + sconto%
    if res.get("prezzo_pieno") is None and res.get("prezzo_scontato") and res.get("sconto_percent") and res["sconto_percent"] < 100:
        res["prezzo_pieno"] = round(res["prezzo_scontato"] / (1 - res["sconto_percent"] / 100), 2)

    # 4. Sconto mancante -> calcolo dai due prezzi
    if res.get("sconto_percent") is None and res.get("prezzo_scontato") and res.get("prezzo_pieno") and res["prezzo_pieno"] > 0:
        res["sconto_percent"] = round((1 - res["prezzo_scontato"] / res["prezzo_pieno"]) * 100)

    # 5. Titolo/immagine mancanti -> estrai dall'HTML già disponibile
    if res.get("asin") and (not res.get("immagine_url") or not res.get("titolo")):
        meta = estrai_dati_da_html(html)
        if not res.get("immagine_url") and meta.get("immagine_url"):
            res["immagine_url"] = _immagine_alta_qualita(meta["immagine_url"])
        if not res.get("titolo") and meta.get("titolo"):
            res["titolo"] = clean_title(meta["titolo"])

    _aggiorna_eur(res)
    return res


def asin_recenti_dal_foglio(righe: List[Dict[str, Any]], ore: int = DEDUP_ORE) -> Set[str]:
    """ASIN gia' presenti nel foglio (stati attivi) nelle ultime `ore` ore."""
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
    """Regole d'oro per l'approvazione automatica. Restituisce (ok, motivi)."""
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
    if not dati.get("immagine_url"):
        motivi.append("immagine mancante")
    return (len(motivi) == 0, motivi)


async def processa_testo_offerta(
    testo: str, righe_foglio: List[Dict[str, Any]], fonte: str = "canale_terzo"
) -> Dict[str, Any]:
    """Pipeline completa: parsing AI -> arricchimento -> validazione."""
    from ai_offer_parser import parse_offerta_da_testo

    dati = await parse_offerta_da_testo(testo)
    dati = await asyncio.to_thread(arricchisci_dati, dati)
    ok, motivi = valida_offerta(dati, asin_recenti_dal_foglio(righe_foglio))
    return {"auto_approvata": ok, "motivi": motivi, "dati": dati, "fonte": fonte}
