"""Parser AI di offerte Amazon da messaggi Telegram.

Usa Groq per estrarre dati strutturati da offerte Amazon.
Se Groq non è disponibile o fallisce, usa un fallback regex.
"""

import asyncio
import json
import logging
import os
import re
from typing import Dict, Any, Optional, List

from groq import AsyncGroq

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_offer_parser")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "").strip() or "openai/gpt-oss-20b"

AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+', re.IGNORECASE)
ASIN_RE = re.compile(r"/(?:dp|gp/product|gp/aw/d)/([A-Z0-9]{10})", re.IGNORECASE)
PRICE_RE = re.compile(r'(\d+[.,]\d{2})\s*€')

SYSTEM_PROMPT = """Sei un estrattore esperto e rigoroso di dati da offerte prodotti Amazon per canali Telegram.

Dato un messaggio di offerta, devi estrarre SOLO dati strutturati.

Rispondi ESCLUSIVAMENTE con un oggetto JSON valido, senza markdown, senza spiegazioni, senza testo extra.

Schema JSON richiesto:

{
  "titolo": string | null,
  "prezzo_scontato": number | null,
  "prezzo_pieno": number | null,
  "sconto_percent": integer | null,
  "asin": string | null,
  "immagine_url": string | null,
  "link_originale": string | null
}

Regole:
1. "titolo": prodotto pulito, massimo 200 caratteri, senza prezzi, senza emoji, senza hashtag, senza frasi tipo "VAI ALL'OFFERTA".
2. "prezzo_scontato": prezzo finale/offerta, numero con punto decimale. Esempio: 23.14.
3. "prezzo_pieno": prezzo originale/pieno/precedente/consigliato, numero con punto decimale.
4. "sconto_percent": percentuale di sconto intera, senza simbolo %. Esempio: 35.
5. "asin": codice Amazon di 10 caratteri alfanumerici, se presente o deducibile dal link.
6. "immagine_url": URL immagine solo se presente esplicitamente nel testo; altrimenti null.
7. "link_originale": primo link Amazon/amzn.to/amzn.eu presente nel messaggio.
8. Se un dato non è certo, usa null.
9. Se ci sono due prezzi, di norma il più basso è prezzo_scontato e il più alto è prezzo_pieno.
10. Non inventare dati.
"""

DEFAULT_RESULT: Dict[str, Any] = {
    "titolo": None,
    "prezzo_scontato": None,
    "prezzo_pieno": None,
    "sconto_percent": None,
    "asin": None,
    "immagine_url": None,
    "link_originale": None,
    "prezzo_scontato_eur": None,
    "prezzo_pieno_eur": None,
}


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", ".").replace("€", "").strip())
    except Exception:
        return None


def _safe_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(round(float(str(value).replace("%", "").replace(",", ".").strip())))
    except Exception:
        return None


def _format_eur(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    return f"{value:.2f}".replace(".", ",")


def _extract_json_from_text(text: str) -> Optional[dict]:
    """Estrae un JSON anche se il modello aggiunge accidentalmente testo o markdown."""
    if not text:
        return None

    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # Fallback: prova a prendere la prima {...}
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def _fallback_regex_extract(testo: str, base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Fallback senza AI: estrae link, ASIN e prezzi base."""
    res = DEFAULT_RESULT.copy()
    if base:
        res.update(base)

    # Link Amazon
    if not res.get("link_originale"):
        links = AMAZON_URL_RE.findall(testo or "")
        if links:
            res["link_originale"] = links[0].rstrip(").,]")

    # ASIN da link
    if not res.get("asin") and res.get("link_originale"):
        m = ASIN_RE.search(res["link_originale"])
        if m:
            res["asin"] = m.group(1).upper()

    # Prezzi nel testo
    prices = PRICE_RE.findall(testo or "")
    nums: List[float] = []
    for p in prices:
        val = _safe_float(p)
        if val is not None:
            nums.append(val)

    if nums:
        nums = sorted(set(nums))
        if res.get("prezzo_scontato") is None:
            res["prezzo_scontato"] = nums[0]
        if res.get("prezzo_pieno") is None and len(nums) > 1:
            res["prezzo_pieno"] = nums[-1]

    # Se il modello/fallback ha invertito i prezzi, correggi
    ps = res.get("prezzo_scontato")
    pp = res.get("prezzo_pieno")
    if ps is not None and pp is not None and ps > pp:
        res["prezzo_scontato"], res["prezzo_pieno"] = pp, ps

    # Calcola sconto se possibile
    ps = res.get("prezzo_scontato")
    pp = res.get("prezzo_pieno")
    if res.get("sconto_percent") is None and ps and pp and pp > 0 and ps < pp:
        res["sconto_percent"] = round((1 - ps / pp) * 100)

    res["prezzo_scontato_eur"] = _format_eur(res.get("prezzo_scontato"))
    res["prezzo_pieno_eur"] = _format_eur(res.get("prezzo_pieno"))

    return res


async def _call_groq(testo: str) -> str:
    if not GROQ_API_KEY:
        log.warning("GROQ_API_KEY non configurata. Uso fallback regex.")
        return ""

    try:
        client = AsyncGroq(api_key=GROQ_API_KEY)

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"Analizza questo messaggio Telegram di offerta Amazon:\n\n{testo}",
                },
            ],
            temperature=0.1,
            max_completion_tokens=800,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or ""
        log.info("Groq OK con modello %s", GROQ_MODEL)
        return content

    except Exception as e:
        log.error("Groq fallito: %s", e)
        return ""


async def parse_offerta_da_testo(testo: str) -> Dict[str, Any]:
    """Analizza il testo di un'offerta Amazon e restituisce dati strutturati."""
    if not testo or not testo.strip():
        return DEFAULT_RESULT.copy()

    raw_response = await _call_groq(testo)

    if not raw_response:
        return _fallback_regex_extract(testo)

    parsed = _extract_json_from_text(raw_response)
    if not parsed:
        log.warning("Risposta Groq non parsabile come JSON. Uso fallback regex. Raw: %s", raw_response[:500])
        return _fallback_regex_extract(testo)

    result = DEFAULT_RESULT.copy()

    # Titolo
    titolo = parsed.get("titolo")
    if isinstance(titolo, str) and titolo.strip():
        titolo = titolo.strip()
        if len(titolo) > 200:
            titolo = titolo[:197] + "..."
        result["titolo"] = titolo

    # Prezzi
    result["prezzo_scontato"] = _safe_float(parsed.get("prezzo_scontato"))
    result["prezzo_pieno"] = _safe_float(parsed.get("prezzo_pieno"))

    # Se Groq ha invertito i prezzi, correggi
    ps = result["prezzo_scontato"]
    pp = result["prezzo_pieno"]
    if ps is not None and pp is not None and ps > pp:
        result["prezzo_scontato"], result["prezzo_pieno"] = pp, ps

    # Sconto
    result["sconto_percent"] = _safe_int(parsed.get("sconto_percent"))

    if (
        result["sconto_percent"] is None
        and result["prezzo_scontato"] is not None
        and result["prezzo_pieno"] is not None
        and result["prezzo_pieno"] > 0
        and result["prezzo_scontato"] < result["prezzo_pieno"]
    ):
        result["sconto_percent"] = round(
            (1 - result["prezzo_scontato"] / result["prezzo_pieno"]) * 100
        )

    # ASIN
    asin = parsed.get("asin")
    if isinstance(asin, str):
        asin = asin.strip().upper()
        if len(asin) == 10 and asin.isalnum():
            result["asin"] = asin

    # Link
    link = parsed.get("link_originale")
    if isinstance(link, str) and link.startswith("http"):
        result["link_originale"] = link.strip().rstrip(").,]")

    # Immagine
    img = parsed.get("immagine_url")
    if isinstance(img, str) and img.startswith("http"):
        result["immagine_url"] = img.strip()

    result["prezzo_scontato_eur"] = _format_eur(result.get("prezzo_scontato"))
    result["prezzo_pieno_eur"] = _format_eur(result.get("prezzo_pieno"))

    # Completa eventuali buchi con regex
    result = _fallback_regex_extract(testo, result)

    return result
