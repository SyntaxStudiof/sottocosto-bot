"""Parser AI di offerte Amazon da messaggi Telegram.

Usa Gemini per estrarre dati strutturati, con supporto per chiavi multiple
(fallback automatico se una chiave ha finito la quota).
"""

import asyncio
import json
import logging
import os
import re
from typing import Dict, Any, List

from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_offer_parser")

# Supporta chiavi multiple separate da virgola (fallback automatico)
GEMINI_API_KEYS_RAW = os.environ.get("GEMINI_API_KEY", "")
GEMINI_API_KEYS = [k.strip() for k in GEMINI_API_KEYS_RAW.split(",") if k.strip()]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')

SYSTEM_PROMPT = """Sei un estrattore esperto e rigoroso di dati da offerte prodotti Amazon per canali Telegram.
Dato un messaggio di offerta, estrai le informazioni ed elabora ESCLUSIVAMENTE un oggetto JSON con i seguenti campi:

- "titolo": stringa pulita del prodotto (massimo 200 caratteri, senza prezzi, senza parole come 'VAI ALL'OFFERTA', senza hashtag, senza emoji).
- "prezzo_scontato": numero float (es: 23.14) o null se non specificato.
- "prezzo_pieno": numero float originale (es: 29.99) o null se non specificato.
- "sconto_percent": numero intero indicante la percentuale di sconto (es: 23) o null se non calcolabile.
- "asin": stringa di 10 caratteri alfanumerici (es: B08N5WRWNW) estratta dal testo o dal link, oppure null.
- "immagine_url": URL dell'immagine se presente esplicitamente nel messaggio, altrimenti null.
- "link_originale": il primo URL Amazon (amazon.it, amzn.to, amzn.eu, ecc.) presente nel messaggio, oppure null.

REGOLE RIGIDE:
1. Restituisci SOLO un JSON valido, senza blocchi di codice markdown (senza ```json), senza spiegazioni, introduzioni o commenti.
2. Se un campo non è presente o non è determinabile con certezza, imposta il suo valore a null.
3. I prezzi devono essere numeri decimali float con punto (es. 19.99 e non "19,99 €").
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


def _fallback_regex_extract(testo: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Estrazione di fallback con regex per link Amazon e ASIN se non catturati dall'AI."""
    res = data.copy()
    if not res.get("link_originale"):
        links = AMAZON_URL_RE.findall(testo)
        if links:
            res["link_originale"] = links[0]

    if not res.get("asin") and res.get("link_originale"):
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", res["link_originale"])
        if match:
            res["asin"] = match.group(1).upper()

    return res


async def _call_gemini_single(api_key: str, testo: str) -> str:
    """Prova una singola chiamata Gemini. Restituisce la risposta o stringa vuota se fallisce."""
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Analizza il seguente messaggio di un'offerta Amazon ed estrai i dati richiesti:\n\n{testo}"
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )
        return response.text or ""
    except Exception as e:
        err_str = str(e)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            log.warning(f"Gemini quota esaurita per questa chiave, provo la successiva...")
            return ""
        log.error(f"Errore chiamata Gemini: {e}")
        return ""


async def _call_gemini_with_fallback(testo: str, retries_per_key: int = 2) -> str:
    """Prova tutte le chiavi disponibili, con retry per ciascuna."""
    if not GEMINI_API_KEYS:
        log.warning("Nessuna GEMINI_API_KEY configurata.")
        return ""

    for api_key in GEMINI_API_KEYS:
        for attempt in range(retries_per_key):
            result = await _call_gemini_single(api_key, testo)
            if result:
                return result
            # Se la risposta è vuota, potrebbe essere quota esaurita → prova la prossima chiave
            if attempt < retries_per_key - 1:
                await asyncio.sleep(2 ** attempt)  # backoff

    log.error("Tutte le chiavi Gemini hanno fallito (quota esaurita o errori).")
    return ""


async def parse_offerta_da_testo(testo: str) -> Dict[str, Any]:
    """Analizza il testo del messaggio Telegram di un'offerta Amazon tramite Gemini API
    e restituisce un dizionario strutturato."""
    empty_result = DEFAULT_RESULT.copy()

    if not testo or not testo.strip():
        return empty_result

    raw_response = await _call_gemini_with_fallback(testo)
    if not raw_response:
        return _fallback_regex_extract(testo, empty_result)

    try:
        cleaned_json = raw_response.strip()
        if cleaned_json.startswith("```"):
            cleaned_json = re.sub(r"^```(?:json)?\s*", "", cleaned_json)
            cleaned_json = re.sub(r"\s*```$", "", cleaned_json)

        parsed = json.loads(cleaned_json)
        if not isinstance(parsed, dict):
            return _fallback_regex_extract(testo, empty_result)
    except Exception as e:
        log.warning("Errore di parsing JSON restituito da Gemini: %s. Raw: %s", e, raw_response)
        return _fallback_regex_extract(testo, empty_result)

    result = empty_result.copy()

    # 1. Titolo
    titolo = parsed.get("titolo")
    if isinstance(titolo, str) and titolo.strip():
        titolo_clean = titolo.strip()
        if len(titolo_clean) > 200:
            titolo_clean = titolo_clean[:197] + "..."
        result["titolo"] = titolo_clean

    # 2. Prezzi (float)
    for field in ("prezzo_scontato", "prezzo_pieno"):
        val = parsed.get(field)
        if val is not None:
            try:
                result[field] = float(str(val).replace(",", "."))
            except (ValueError, TypeError):
                result[field] = None

    # Formattazione prezzi in EUR (es. "23,14")
    if result["prezzo_scontato"] is not None:
        result["prezzo_scontato_eur"] = f"{result['prezzo_scontato']:.2f}".replace(".", ",")
    if result["prezzo_pieno"] is not None:
        result["prezzo_pieno_eur"] = f"{result['prezzo_pieno']:.2f}".replace(".", ",")

    # 3. Sconto %
    sconto = parsed.get("sconto_percent")
    if sconto is not None:
        try:
            result["sconto_percent"] = int(float(str(sconto)))
        except (ValueError, TypeError):
            result["sconto_percent"] = None

    if (
        result["sconto_percent"] is None
        and result["prezzo_scontato"] is not None
        and result["prezzo_pieno"] is not None
        and result["prezzo_pieno"] > 0
    ):
        result["sconto_percent"] = round(
            (1 - result["prezzo_scontato"] / result["prezzo_pieno"]) * 100
        )

    # 4. ASIN
    asin = parsed.get("asin")
    if isinstance(asin, str) and len(asin.strip()) == 10 and asin.strip().isalnum():
        result["asin"] = asin.strip().upper()

    # 5. Link originale
    link = parsed.get("link_originale")
    if isinstance(link, str) and link.startswith("http"):
        result["link_originale"] = link.strip()

    # 6. Immagine URL
    img = parsed.get("immagine_url")
    if isinstance(img, str) and img.startswith("http"):
        result["immagine_url"] = img.strip()

    return _fallback_regex_extract(testo, result)
