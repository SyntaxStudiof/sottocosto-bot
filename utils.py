import re

def clean_title(raw_text):
    text = raw_text
    
    # 1. Rimuovi tutti gli URL (link Amazon, ecc.)
    text = re.sub(r'https?://\S+', '', text)
    
    # 2. Rimuovi la formattazione di Telegram (doppi asterischi, doppi underscore, ecc.)
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    
    # 3. Rimuovi TUTTI i prezzi e le etichette dei prezzi (es. "Prezzo consigliato: 224,27€", "Prezzo in : 103,10€")
    # Questa regex cattura la parola "Prezzo", qualsiasi altra parola dopo, i due punti, e il numero con l'euro
    text = re.sub(r'[Pp]rezzo\s*\w*\s*[:.]?\s*\d+[.,]?\d*\s?[€€]', '', text)
    
    # 4. Rimuovi eventuali numeri con l'euro rimasti "sparsi" (che non avevano la parola Prezzo)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€€]\b', '', text)
    
    # 5. Rimuovi parentesi, tag e hashtag come "[VAI ALL']", "(Disclamer)", "#adv"
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'#\w+', '', text)
    
    # 6. Pulisci gli spazi extra e i ritorni a capo
    text = ' '.join(text.split())
    
    return text.strip()


def split_multiple_offers(text):
    # Lista di simboli che spesso separano le offerte nei canali Telegram
    separators = [r'\n-+\n', r'\n\s*\n', r'✅', r'❌', r'🔹', r'🔸', r'⬇️']
    
    for sep in separators:
        parts = re.split(sep, text)
        if len(parts) > 1:
            return [p.strip() for p in parts if p.strip()]
            
    return [text.strip()]
