# bot.py
import os
import re
import requests
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
BOT_TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"  # Replace after revoking
DEFAULT_PIN = "110001"
# =================================================

# List of known shorteners
SHORTENER_DOMAINS = [
    'fkrt.cc', 'amzn.to', 'spoo.me', 'cutt.ly', 
    'bitly.in', 'da.gd', 'wishlink.com'
]

def is_shortened(url):
    """Check if URL is from a shortener"""
    domain = urlparse(url).netloc.lower()
    return any(s in domain for s in SHORTENER_DOMAINS)

async def unshorten_url(url):
    """Resolve shortened URLs"""
    if not is_shortened(url):
        return url  # Already full
    
    try:
        resp = requests.get(url, allow_redirects=True, timeout=5, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
        })
        return resp.url.split('?')[0]  # Remove query params
    except:
        return url

def extract_price(text):
    """Extract digits from ₹50 or Rs 299"""
    match = re.search(r'(?:₹|Rs?\s*)(\d+)', text.replace(',', ''))
    return match.group(1) if match else ""

def extract_quantity(text):
    """Extract 200ml, 5pcs, etc."""
    match = re.search(r'\b\d+(?:ml|g|kg|l|pcs|pack|set)s?\b', text, re.I)
    return match.group().lower() if match else ""

def extract_brand(text):
    """Extract brand"""
    brands = ["Vivel", "Dettol", "Mamaearth", "Boat", "Nike", "Puma", "Wildcraft"]
    for brand in brands:
        if brand.lower() in text.lower():
            return brand
    return ""

def clean_title(text, brand, quantity):
    """Clean product name"""
    if brand:
        text = re.sub(re.escape(brand), '', text, flags=re.I)
    if quantity:
        text = re.sub(r'\b' + re.escape(quantity) + r'\b', '', text, flags=re.I)
    text = re.sub(r'(?:₹|Rs?)\s*\d+', '', text)
    text = re.sub(r'[-_]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    words = [w.capitalize() for w in text.split() if len(w) > 1]
    return " ".join(dict.fromkeys(words))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption or ""
    url_match = re.search(r'https?://[^\s]+', text)
    
    if not url_match:
        return
    
    url = url_match.group(0)
    
    try:
        # Step 1: Unshorten URL
        clean_url = await unshorten_url(url)
        
        # Step 2: Extract info from message text
        price = extract_price(text)
        quantity = extract_quantity(text)
        brand = extract_brand(text)
        product = clean_title(text, brand, quantity)
        
        # Step 3: Build title
        parts = []
        if quantity: parts.append(quantity)
        if brand: parts.append(brand)
        if product: parts.append(product)
        title = " ".join(parts).strip()
        
        # Price: @50 rs or @ rs
        price_text = f"@{price} rs" if price else "@ rs"
        final_title = f"{title} {price_text}"
        
        # Step 4: Build response
        lines = [final_title]
        
        # Add Meesho-specific lines if domain is meesho
        if "meesho.com" in urlparse(clean_url).netloc.lower():
            lines.append("")  # blank line
            lines.append("Size - All")
            pin_match = re.search(r'\b\d{6}\b', text)
            pin = pin_match.group(0) if pin_match else DEFAULT_PIN
            lines.append(f"Pin - {pin}")
        
        lines.append("")  # blank line
        lines.append("@reviewcheckk")
        
        response = "\n".join(lines)
        
        # Step 5: Send reply with clean preview
        await update.message.reply_text(
            response,
            disable_web_page_preview=True
        )
        
    except Exception as e:
        # Silent fail — no error messages in chat
        print(f"Error: {e}")
        pass  # Don't send "error" to user

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running! Send a link...")
    app.run_polling()

if __name__ == "__main__":
    main()
