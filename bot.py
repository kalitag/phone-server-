import re
import logging
from telegram import Update, ParseMode
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext
import requests
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"

SHORTENERS = ['fkrt.cc', 'amzn.to', 'spoo.me', 'cutt.ly', 'bitly.in', 'da.gd', 'wishlink.com']
SUPPORTED_SITES = ['amazon', 'flipkart', 'meesho', 'myntra', 'ajio', 'snapdeal', 'wishlink']

def unshorten_url(url):
    try:
        if any(shortener in url for shortener in SHORTENERS):
            response = requests.head(url, allow_redirects=True, timeout=2)
            return response.url
        return url
    except:
        return url

def clean_url(url):
    try:
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        params_to_remove = ['tag', 'ref', 'utm_source', 'utm_medium', 'utm_campaign', 
                           'src', 'affid', 'affExtParam1', 'affExtParam2']
        
        for param in params_to_remove:
            query_params.pop(param, None)
        
        new_query = urlencode(query_params, doseq=True)
        clean = urlunparse((parsed.scheme, parsed.netloc, parsed.path, 
                           parsed.params, new_query, ''))
        
        return clean
    except:
        return url

def extract_title_from_url(url):
    try:
        path = urlparse(url).path
        
        if 'amazon' in url:
            match = re.search(r'/([^/]+)/dp/', path)
            if match:
                title = match.group(1).replace('-', ' ')
                return clean_title(title)
        
        elif 'flipkart' in url:
            match = re.search(r'/([^/]+)/p/', path)
            if match:
                title = match.group(1).replace('-', ' ')
                return clean_title(title)
        
        elif 'meesho' in url:
            match = re.search(r'/([^/]+)/p/', path)
            if match:
                title = match.group(1).replace('-', ' ')
                return clean_title(title)
        
        elif 'myntra' in url or 'ajio' in url:
            parts = path.strip('/').split('/')
            if parts:
                title = parts[-1].split('-')
                if len(title) > 2:
                    brand = title[0]
                    product = ' '.join(title[1:-1])
                    return f"{brand} {product}"
        
        elif 'snapdeal' in url:
            match = re.search(r'/product/([^/]+)/', path)
            if match:
                title = match.group(1).replace('-', ' ')
                return clean_title(title)
        
        return "Product"
    except:
        return "Product"

def clean_title(title):
    title = re.sub(r'\b(pack|of|combo|set|offer|deal|sale|discount|best|new|latest|exclusive)\b', '', title, flags=re.IGNORECASE)
    title = re.sub(r'[^\w\s]', ' ', title)
    title = re.sub(r'\s+', ' ', title)
    
    words = title.split()
    seen = set()
    result = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            result.append(word)
    
    title = ' '.join(result).strip()
    
    title = title.title()
    
    return title[:50] if len(title) > 50 else title

def extract_price(text):
    patterns = [
        r'₹\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'Rs\.?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'@\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
        r'\b(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:rs|RS|Rs|rupees?)\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            price = match.group(1).replace(',', '').split('.')[0]
            return price
    
    return None

def extract_pin(text):
    match = re.search(r'\b(\d{6})\b', text)
    if match:
        return match.group(1)
    return "110001"

def extract_quantity(title):
    patterns = [
        r'\b(\d+\s*(?:ml|ML|l|L|kg|KG|g|G|mg|MG))\b',
        r'\b(\d+\s*(?:pcs|PCS|pieces|PIECES|pc|PC|piece|PIECE))\b',
        r'\b(\d+\s*(?:pack|PACK|packs|PACKS))\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            qty = match.group(1).lower()
            remaining = re.sub(pattern, '', title, flags=re.IGNORECASE).strip()
            return qty, remaining
    
    return None, title

def process_message(update: Update, context: CallbackContext):
    try:
        text = update.message.text
        
        url_pattern = r'https?://[^\s]+'
        urls = re.findall(url_pattern, text)
        
        if not urls:
            return
        
        url = urls[0]
        
        if not any(site in url.lower() for site in SUPPORTED_SITES):
            return
        
        url = unshorten_url(url)
        clean = clean_url(url)
        
        title = extract_title_from_url(clean)
        
        qty, title_without_qty = extract_quantity(title)
        
        if qty:
            final_title = f"{qty} {title_without_qty}"
        else:
            final_title = title
        
        price = extract_price(text)
        if price:
            price_str = f"@{price} rs"
        else:
            price_str = "@ rs"
        
        output = f"{final_title} {price_str}\n"
        
        if 'meesho' in clean.lower():
            pin = extract_pin(text)
            output += f"\nSize - All\nPin - {pin}\n\n"
        
        output += f"{clean}\n\n@reviewcheckk"
        
        update.message.reply_text(
    output,
    parse_mode=None,  # ← This fixes the error
    disable_web_page_preview=True
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        pass

def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, process_message))
    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
