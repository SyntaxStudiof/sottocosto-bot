from datetime import datetime, timezone

from sheet_client import get_all_rows, mark_row


def controlla_scaduti():
    righe, ws = get_all_rows()
    ora_adesso = datetime.now(timezone.utc)
    trovati = 0

    for riga in righe:
        stato = riga.get("stato")
        scade_il = riga.get("scade_il")

        if stato == "APPROVATO" and scade_il:
            try:
                data_scadenza = datetime.fromisoformat(scade_il)
            except ValueError:
                # data scritta in modo strano, la saltiamo invece di far crashare tutto
                print(f"Data non valida per '{riga.get('titolo')}': {scade_il}")
                continue

            if data_scadenza < ora_adesso:
                mark_row(ws, riga["_row_number"], "SCADUTO")
                print(f"Segnato come SCADUTO: {riga.get('titolo')}")
                trovati += 1

    print(f"Fatto. Prodotti scaduti trovati: {trovati}")


if __name__ == "__main__":
    controlla_scaduti()