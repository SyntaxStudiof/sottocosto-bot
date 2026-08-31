import json
import os
import time
from datetime import datetime, timedelta, timezone

import gspread
from gspread.exceptions import APIError
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
CREDS_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# --- CACHE DELL'INTESTAZIONE E DEL CLIENT (per evitare errori 429) ---
_HEADER_CACHE = None
_CLIENT_CACHE = None

# --- CACHE PER LEGGI CONFIG (riduce le chiamate a Sheets) ---
_CONFIG_CACHE = {}
_CONFIG_CACHE_TIME = {}
_CONFIG_CACHE_TTL = 300  # 5 minuti

def _get_client():
    global _CLIENT_CACHE
    if _CLIENT_CACHE is None:
        creds_dict = json.loads(CREDS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        _CLIENT_CACHE = gspread.authorize(creds)
    return _CLIENT_CACHE

def _with_retry(fn, *args, retries=4, **kwargs):
    """Ritenta le chiamate all'API di Google in caso di 429 (quota superata),
    con backoff esponenziale. Rilancia l'errore se non è un problema di quota
    o se i tentativi sono esauriti."""
    last_err = None
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except APIError as e:
            last_err = e
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "Quota exceeded" in msg:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_err

def _get_worksheet():
    client = _get_client()
    spreadsheet = _with_retry(client.open_by_key, SHEET_ID)
    return spreadsheet.worksheet("Foglio1")

def _get_header():
    """Legge l'intestazione una volta sola e la mette in cache."""
    global _HEADER_CACHE
    if _HEADER_CACHE is None:
        ws = _get_worksheet()
        _HEADER_CACHE = _with_retry(ws.row_values, 1)
    return _HEADER_CACHE

def get_all_rows():
    """Ritorna lista di dict, ognuno con anche il numero di riga reale nel foglio."""
    ws = _get_worksheet()
    records = _with_retry(ws.get_all_records, numericise_ignore=['all'])
    rows = []
    for i, r in enumerate(records, start=2):  # riga 1 = header
        r["_row_number"] = i
        rows.append(r)
    return rows, ws

def mark_row(ws, row_number, stato, extra_updates=None):
    """Aggiorna la colonna stato (e opzionalmente altre) per una riga."""
    header = _with_retry(ws.row_values, 1)
    updates = {"stato": stato}
    if extra_updates:
        updates.update(extra_updates)
    for col_name, value in updates.items():
        if col_name in header:
            col_index = header.index(col_name) + 1
            _with_retry(ws.update_cell, row_number, col_index, value)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _get_config_worksheet():
    client = _get_client()
    sheet = _with_retry(client.open_by_key, SHEET_ID)
    try:
        return sheet.worksheet("Config")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Config", rows=10, cols=2)
        ws.update([["chiave", "valore"]], "A1")
        return ws

def get_state(key, default=""):
    """Legge una chiave dal foglio Config con cache in memoria."""
    global _CONFIG_CACHE, _CONFIG_CACHE_TIME
    
    now = time.time()
    if key in _CONFIG_CACHE and (now - _CONFIG_CACHE_TIME.get(key, 0)) < _CONFIG_CACHE_TTL:
        return _CONFIG_CACHE[key]
    
    ws = _get_config_worksheet()
    values = _with_retry(ws.get_all_records, numericise_ignore=['all'])
    for row in values:
        if row.get("chiave") == key:
            val = str(row.get("valore", default))
            _CONFIG_CACHE[key] = val
            _CONFIG_CACHE_TIME[key] = now
            return val
    
    _CONFIG_CACHE[key] = default
    _CONFIG_CACHE_TIME[key] = now
    return default

def set_state(key, value):
    ws = _get_config_worksheet()
    value_str = str(value)
    cell = _with_retry(ws.find, key)
    if cell:
        _with_retry(ws.update, f"B{cell.row}", [[value_str]], value_input_option='RAW')
    else:
        _with_retry(ws.append_row, [key, value_str], value_input_option='RAW')
    
    # Aggiorna la cache
    _CONFIG_CACHE[key] = value_str
    _CONFIG_CACHE_TIME[key] = time.time()

def delete_state(key):
    """Cancella davvero la riga della chiave, invece di lasciarla con valore vuoto."""
    ws = _get_config_worksheet()
    cell = _with_retry(ws.find, key)
    if cell:
        _with_retry(ws.delete_rows, cell.row)
    
    # Rimuovi dalla cache
    if key in _CONFIG_CACHE:
        del _CONFIG_CACHE[key]
    if key in _CONFIG_CACHE_TIME:
        del _CONFIG_CACHE_TIME[key]

def get_state_json(key, default=None):
    """Legge una chiave e la interpreta come JSON. Ritorna {} (o default) se assente/non valida."""
    raw = get_state(key, "")
    if not raw:
        return default if default is not None else {}
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return default if default is not None else {}

def set_state_json(key, data):
    """Scrive un dict come singola cella JSON, invece di una riga per campo."""
    set_state(key, json.dumps(data, ensure_ascii=False))

def append_product_row(product_dict):
    """Aggiunge una nuova riga prodotto in coda, rispettando l'ordine delle colonne del foglio principale."""
    ws = _get_worksheet()
    header = _get_header()  # <--- Usa l'header in cache, evitando il 429!
    row = [product_dict.get(col, "") for col in header]
    _with_retry(ws.append_row, row)
