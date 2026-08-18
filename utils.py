def extract_prices(text):
    # Cerca pattern tipo: 12,99€ o 12.99€ o Prezzo: 15€
    prices = re.findall(r'(\d+[.,]?\d*)\s?[€€]', text)
    # Converti in float sostituendo virgola con punto
    prices_float = []
    for p in prices:
        p_clean = p.replace(',', '.').replace(' ', '')
        try:
            prices_float.append(float(p_clean))
        except:
            continue
    
    if not prices_float:
        return None, None
    
    # Se trova almeno 2 prezzi, il più piccolo è scontato, il più grande è pieno
    if len(prices_float) >= 2:
        sconto = min(prices_float)
        pieno = max(prices_float)
    else:
        sconto = prices_float[0]
        pieno = None
    
    return sconto, pieno
