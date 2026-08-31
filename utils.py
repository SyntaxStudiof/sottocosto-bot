import re

# Regex per trovare il link Amazon
AMAZON_URL_RE = re.compile(r'https?://(?:www\.)?(?:amazon\.[a-z.]+|amzn\.to|amzn\.eu)/\S+')

def clean_title(raw_text: str) -> str:
    """Pulisce il titolo da spam, emoji, prezzi e frasi promozionali."""
    if not raw_text:
        return "Prodotto Amazon (controlla anteprima)"
    
    text = raw_text
    
    # 1. Rimuovi formattazione Telegram
    text = re.sub(r'\*\*', '', text)
    text = re.sub(r'__', '', text)
    
    # 2. Rimuovi frasi promozionali/spam (CASE INSENSITIVE)
    spam_patterns = [
        r'prezzo\s*imperdibile', r'contattami.*?problemi', r'offerta\s*del\s*giorno',
        r'solo\s*oggi', r'affrettati', r'vai\s+all\'?offerta', r'clicca\s+qui',
        r'link\s+in\s+bio', r'scrivimi', r'dm\s+', r'telegram', r'whatsapp',
        r'instagram', r'facebook', r'disclaimer\s*[-–]?\s*condividi\s+su\s+wa',
        r'condividi\s+su\s+wa', r'disclaimer'
    ]
    for pattern in spam_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # 3. Rimuovi emoji e simboli decorativi
    text = re.sub(r'[🔥💣⚡🎁💰🛒✅❌⭐🏷️📦🚀💥🎯🔔📢💡🎉🎊🎈🎀🎁🎂🎃🎄🎅🎆🎇🎋🎌🎍🎎🎏🎐🎑🎒🎓🎖️🎗️🎙️🎚️🎛️🎞️🎟️🎠🎡🎢🎣🎤🎥🎦🎧🎨🎩🎪🎫🎬🎭🎮🎯🎰🎱🎲🎳🎴🎵🎶🎷🎸🎹🎺🎻🎼🎽🎾🎿🏀🏁🏂🏃🏄🏅🏆🏇🏈🏉🏊🏋️🏌️🏍️🏎️🏏🏐🏑🏒🏓🏔️🏕️🏖️🏗️🏘️🏙️🏚️🏛️🏜️🏝️🏞️🏟️🏠🏡🏢🏣🏤🏥🏦🏧🏨🏩🏪🏫🏬🏭🏮🏯🏰🏱️🏲️🏳️🏴🏵️🏶️🏷️🏸🏹🏺🏻🏼🏽🏾🏿]', '', text)
    
    # 4. Rimuovi prezzi, link, hashtag, parentesi
    text = re.sub(r'[Pp]rezzo\s*[a-zA-Z\s]*?[:.]?\s*\d+[.,]?\d*\s?[€$]\s*', '', text)
    text = re.sub(r'\b\d+[.,]?\d*\s?[€$]\b', '', text)
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'#\w+', '', text)
    text = re.sub(r'[\(\)\[\]\{\}]', '', text)
    text = re.sub(r'@\w+', '', text)
    
    # 5. Pulisci spazi e punteggiatura residua
    text = ' '.join(text.split())
    text = re.sub(r'[-–_\s:,;]+$', '', text.strip())
    text = re.sub(r'^[-–_\s:,;]+', '', text.strip())
    
    # Fallback anti-titolo vuoto
    if len(text.strip()) < 5:
        fallback = re.sub(r'https?://\S+|#\w+|[\(\)\[\]\{\}]', '', raw_text)
        fallback = ' '.join(fallback.split()).strip()
        text = fallback if fallback else "Prodotto Amazon (controlla anteprima)"
    
    # Tronca a 200 caratteri
    if len(text) > 200:
        return text[:197] + "..."
    
    return text.strip()


def split_multiple_offers(text: str) -> list[str]:
    """Divide il messaggio in offerte multiple in modo intelligente."""
    parts = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    
    final_offers = []
    buffer = ""
    
    for part in parts:
        if AMAZON_URL_RE.search(part):
            if buffer:
                final_offers.append(f"{buffer}\n\n{part}")
                buffer = ""
            else:
                final_offers.append(part)
        else:
            buffer = f"{buffer}\n\n{part}" if buffer else part
    
    if buffer and final_offers:
        final_offers[-1] += f"\n\n{buffer}"
    elif buffer and not final_offers:
        final_offers.append(buffer)
            
    return final_offers