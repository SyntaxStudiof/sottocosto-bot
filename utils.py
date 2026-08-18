import re

# Regex per trovare il link Amazon
AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi formattazione Telegram e parole dei prezzi
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€€]\s*', '', text)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€]\b', '', text)
    
    # 2. Rimuovi link, frasi comuni, hashtag e parentesi
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'VAI ALL\'OFFERTA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    
    # 3. Rimuovi disclaimer e footer sparsi
    text = re.sub(r'Disclaimer\s*[-–]\s*Condividi\s*su\s*WA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Condividi\s*su\s*WA', '', text, flags=re.IGNORECASE)
    text = re.sub(r'Disclaimer', '', text, flags=re.IGNORECASE)
    
    # 4. Pulisci gli spazi
    text = ' '.join(text.split())
    
    # --- FALLBACK ANTI-TITOLO VUOTO ---
    if len(text.strip()) < 5:
        fallback = raw_text
        fallback = re.sub(r'https?://\S+', '', fallback)
        fallback = re.sub(r'#\w+', '', fallback)
        fallback = re.sub(r'[\(\)\[\]\{\}]', '', fallback)
        fallback = ' '.join(fallback.split())
        
        if fallback.strip():
            if len(fallback) > 200:
                return fallback[:197] + "..."
            return fallback.strip()
        else:
            return "Prodotto Amazon (controlla anteprima)"
    
    # --- FIX: Rimuovi eventuali spazi, trattini o punteggiatura rimasti alla fine ---
    text = re.sub(r'[-–_\s]+$', '', text.strip())
    
    # --- REGOLA DEI PUNTINI PER TITOLI LUNGHI (Max 200 caratteri) ---
    if len(text) > 200:
        return text[:197] + "..."
        
    return text.strip()


def split_multiple_offers(text):
    """
    Divide il messaggio in offerte in modo INTELLIGENTE.
    """
    # Dividi il testo in base a dove ci sono doppi a capo
    parts = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    
    final_offers = []
    buffer = ""
    
    for part in parts:
        # Controlla se questa parte contiene un link Amazon valido
        if AMAZON_URL_RE.search(part):
            # Se avevamo del testo in attesa nel buffer, uniscilo a questa offerta
            if buffer:
                final_offers.append(f"{buffer}\n\n{part}")
                buffer = ""
            else:
                final_offers.append(part)
        else:
            # Se questa parte NON ha un link Amazon, è un pezzo di descrizione/footer.
            # Aggiungilo al buffer per unirlo al prossimo pezzo che ha il link.
            if buffer:
                buffer += f"\n\n{part}"
            else:
                buffer = part
    
    # Se alla fine del ciclo è rimasto del testo nel buffer, attaccalo all'ultima offerta.
    if buffer and final_offers:
        final_offers[-1] += f"\n\n{buffer}"
    elif buffer and not final_offers:
        final_offers.append(buffer)
            
    return final_offers
