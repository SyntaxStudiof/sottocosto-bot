import json
import os
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
CREDS_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")


def _get_worksheet():
    creds_dict = json.loads(CREDS_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID).sheet1


def get_all_rows():
    """Ritorna lista di dict, ognuno con anche il numero di riga reale nel foglio."""
    ws = _get_worksheet()
    records = ws.get_all_records(numericise_ignore=['all'])
    rows = []
    for i, r in enumerate(records, start=2):  # riga 1 = header
        r["_row_number"] = i
        rows.append(r)
    return rows, ws


def mark_row(ws, row_number, stato, extra_updates=None):
    """Aggiorna la colonna stato (e opzionalmente altre) per una riga."""
    header = ws.row_values(1)
    updates = {"stato": stato}
    if extra_updates:
        updates.update(extra_updates)
    for col_name, value in updates.items():
        if col_name in header:
            col_index = header.index(col_name) + 1
            ws.update_cell(row_number, col_index, value)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_config_worksheet(client=None):
    if client is None:
        creds_dict = json.loads(CREDS_JSON)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
        client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID)
    try:
        return sheet.worksheet("Config")
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title="Config", rows=10, cols=2)
        ws.update([["chiave", "valore"]], "A1")
        return ws


def get_state(key, default=""):
    ws = _get_config_worksheet()
    values = ws.get_all_records()
    for row in values:
        if row.get("chiave") == key:
            return str(row.get("valore", default))
    return default


def set_state(key, value):
    ws = _get_config_worksheet()
    cell = ws.find(key)
    if cell:
        ws.update_cell(cell.row, 2, value)
    else:
        ws.append_row([key, value])


def append_product_row(product_dict):
    """Aggiunge una nuova riga prodotto in coda, rispettando l'ordine delle colonne del foglio principale."""
    ws = _get_worksheet()
    header = ws.row_values(1)
    row = [product_dict.get(col, "") for col in header]
    ws.append_row(row)
