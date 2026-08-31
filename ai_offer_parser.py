"""Parser AI di offerte Amazon da messaggi Telegram.

Logica: Regex PRIMA (gratis, sempre) per titolo/link/ASIN.
Gemini DOPO (solo se necessario) per prezzi/sconto.
Risparmia chiamate API e garantisce titoli sempre puliti.
"""

import asyncio
import json
import logging
import re
from typing import Dict, Any

from google import genai
from google.genai import types

from config import GEMINI_API_KEY, GEMINI_MODEL
from utils import clean_title, AMAZON_URL_RE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ai_offer_parser")

SYSTEM_PROMPT = """Sei un estrattore di dati da offerte Amazon. Restituisci SOLO JSON valido (senza markdown) con:
- "prezzo_scontato": float o null
- "prezzo_pieno": float o null  
- "sconto_percent": int o null
Regole: prezzi in formato float con punto (es. 19.99). Se non determinabile, usa null. Niente altro."""

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


def _extract_with_regex(testo: str) -> Dict[str, Any]:
    """Estrazione base con regex: titolo pulito, link, ASIN. GRATIS e SEMPRE."""
    result = DEFAULT_RESULT.copy()
    
    # Titolo pulito via regex (motore principale)
    result["titolo"] = clean_title(testo)
    
    # Link Amazon
    links = AMAZON_URL_RE.findall(testo)
    if links:
        result["link_originale"] = links[0]
        
        # ASIN dal link
        asin_match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", links[0])
        if asin_match:
            result["asin"] = asin_match.group(1).upper()
    
    # Prezzo base da testo (pattern comune: "29,99€" o "€ 29.99")
    price_match = re.search(r'(\d+[.,]\d{2})\s*€|€\s*(\d+[.,]\d{2})', testo)
    if price_match:
        price_str = (price_match.group(1) or price_match.group(2)).replace(",", ".")
        try:
            result["prezzo_scontato"] = float(price_str)
        except ValueError:
            pass
    
    return result


async def _call_gemini_for_prices(testo: str, retries: int = 2) -> Dict[str, Any]:
    """Chiama Gemini SOLO per prezzi/sconto. Ritorna dict parziale."""
    if not GEMINI_API_KEY:
        return {}
    
    client = genai.Client(api_key=GEMINI_API_KEY)
    delay = 1.0
    
    for attempt in range(retries):
        try:
            response = await client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=f"Estrai prezzi da:\n\n{testo}",
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            )
            
            raw = (response.text or "").strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
                
        except Exception as e:
            err_str = str(e)
            is_transient = any(c in err_str for c in ["429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"])
            if is_transient and attempt < retries - 1:
                log.warning("Gemini retry %d/%d: %s", attempt + 1, retries, e)
                await asyncio.sleep(delay)
                delay *= 2
            else:
                log.error("Gemini fallito: %s", e)
                break
    
    return {}


async def parse_offerta_da_testo(testo: str) -> Dict[str, Any]:
    """Analizza offerta: regex prima (gratis), Gemini dopo (solo prezzi)."""
    if not testo or not testo.strip():
        return DEFAULT_RESULT.copy()
    
    # STEP 1: Regex sempre (titolo pulito + link + ASIN + prezzo base)
    result = _extract_with_regex(testo)
    
    # STEP 2: Gemini SOLO se mancano prezzi/sconto
    needs_ai = (
        result["prezzo_scontato"] is None or 
        result["prezzo_pieno"] is None or 
        result["sconto_percent"] is None
    )
    
    if needs_ai:
        ai_data = await _call_gemini_for_prices(testo)
        
        # Sovrascrivi solo campi mancanti
        for field in ("prezzo_scontato", "prezzo_pieno", "sconto_percent"):
            if ai_data.get(field) is not None and result.get(field) is None:
                val = ai_data[field]
                try:
                    if field == "sconto_percent":
                        result[field] = int(float(str(val)))
                    else:
                        result[field] = float(str(val).replace(",", "."))
                except (ValueError, TypeError):
                    pass
    
    # Calcola sconto % se mancante ma ho entrambi i prezzi
    if (result["sconto_percent"] is None and 
        result["prezzo_scontato"] and result["prezzo_pieno"] and 
        result["prezzo_pieno"] > 0):
        result["sconto_percent"] = round(
            (1 - result["prezzo_scontato"] / result["prezzo_pieno"]) * 100
        )
    
    # Formattazione EUR
    if result["prezzo_scontato"] is not None:
        result["prezzo_scontato_eur"] = f"{result['prezzo_scontato']:.2f}".replace(".", ",")
    if result["prezzo_pieno"] is not None:
        result["prezzo_pieno_eur"] = f"{result['prezzo_pieno']:.2f}".replace(".", ",")
    
    # Validazione ASIN
    asin = result.get("asin")
    if isinstance(asin, str) and len(asin.strip()) == 10 and asin.strip().isalnum():
        result["asin"] = asin.strip().upper()
    else:
        result["asin"] = None
    
    return result