# bot.py
import os
import re
import logging
import requests
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes, ExtBot

# ===== CONFIGURATION =====
# 🔒 Replace with your new token (but revoke it after use!)
BOT_TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"  # ⚠️ REVOKE THIS AFTER TESTING

# Default pin code
DEFAULT_PIN = "110001"

# Brands to detect
BRANDS = ["Vivel", "Dettol", "Mamaearth", "Boat", "Nike", "Puma", "Wildcraft", 
          "OnePlus", "Samsung", "Apple", "Syska", "Amul", "Parle"]

# Clothing keywords
CLOTHING_KEYWORDS = [
    'shirt', 'tshirt', 't-shirt', 'dress', 'kurti', 'saree', 'jeans', 'trouser',
    'pant', 'shorts', 'skirt', 'top', 'blouse', 'jacket', 'sweater', 'hoodie',
    'suit', 'blazer', 'coat', 'leggings', 'nightwear', 'innerwear'
]

# Fluff words to remove
FLUFF_WORDS = [
    'best', 'offer', 'deal', 'sale', 'new', 'latest', 'trending', 'fashion',
    'stylish', 'premium', 'luxury', 'exclusive', 'special', 'limited', 'hot'
]
# ========================

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def detect_platform(url: str) -> str:
    """Detect e-commerce platform from URL"""
    domain = urlparse(url).netloc.lower()
    if "meesho" in domain:
        return "meesho"
    for p in ["amazon", "flipkart", "myntra", "ajio", "snapdeal"]:
        if p in domain:
            return "other"
    return "other"

def extract_price(text: str) -> str:
    """Extract price digits only if ₹ or Rs is present"""
    match = re.search(r'(?:₹|Rs?\s*)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', text)
    return match.group(1).replace(',', '') if match else ""

def extract_quantity(text: str) -> str:
    """Extract 200ml, 5pcs, etc."""
    match = re.search(r'\b\d+(?:ml|g|kg|l|ltr|pcs|pack|set)s?\b', text, re.I)
    return match.group().lower() if match else ""

def extract_brand(text: str) -> str:
    """Extract brand from text"""
    for brand in BRANDS:
        if brand.lower() in text.lower():
            return brand
    return ""

def is_clothing(text: str) -> bool:
    """Check if product is clothing"""
    text_lower = text.lower()
    return any(word in text_lower for word in CLOTHING_KEYWORDS)

def extract_gender(text: str) -> str:
    """Extract gender"""
    text_lower = text.lower()
    if any(w in text_lower for w in ['men', 'man', 'gents', 'male']):
        return "Men"
    if any(w in text_lower for w in ['women', 'woman', 'ladies', 'female']):
        return "Women"
    if any(w in text_lower for w in ['kid', 'child']):
        return "Kids"
    return ""

def clean_product_name(text: str, brand: str, quantity: str) -> str:
    """Remove brand, quantity, price, fluff"""
    if brand:
        text = re.sub(re.escape(brand), '', text, flags=re.I)
    if quantity:
        text = re.sub(r'\b' + re.escape(quantity) + r'\b', '', text, flags=re.I)
    text = re.sub(r'(?:₹|Rs?)\s*\d+', '', text)
    text = re.sub(r'\b(?:' + '|'.join(FLUFF_WORDS) + r')\b', '', text, flags=re.I)
    text = re.sub(r'[-_]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    words = [w.capitalize() for w in text.split() if len(w) > 1]
    return " ".join(dict.fromkeys(words)).strip()

async def unshorten_url(url: str) -> str:
    """Resolve short URLs"""
    try:
        resp = requests.get(url, allow_redirects=True, timeout=5, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
        })
        return resp.url
    except:
        return url  # fallback

async def generate_response(url: str, message_text: str) -> str:
    """Generate response in your exact format"""
    clean_url = await unshorten_url(url)
    platform = detect_platform(clean_url)
    full_text = message_text

    price = extract_price(full_text)
    quantity = extract_quantity(full_text)
    brand = extract_brand(full_text)
    gender = extract_gender(full_text) if is_clothing(full_text) else ""
    product = clean_product_name(full_text, brand, quantity)

    # Build title: [quantity] [brand] [gender] [product] @[price] rs
    parts = []
    if quantity: parts.append(quantity)
    if brand: parts.append(brand)
    if gender: parts.append(gender)
    if product: parts.append(product)

    title = " ".join(parts).strip()
    price_text = f"@{price} rs" if price else "@ rs"
    final_title = f"{title} {price_text}"

    # Build response
    lines = [final_title]

    if platform == "meesho":
        lines.append("")  # blank line
        lines.append("Size - All")
        pin_match = re.search(r'\b\d{6}\b', full_text)
        pin = pin_match.group(0) if pin_match else DEFAULT_PIN
        lines.append(f"Pin - {pin}")

    lines.append("")  # blank line
    lines.append("@reviewcheckk")

    return "\n".join(lines)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    if not update.message:
        return

    text = update.message.text or update.message.caption or ""
    url_match = re.search(r'https?://[^\s]+', text)
    if not url_match:
        return

    try:
        response = await generate_response(url_match.group(0), text)
        await update.message.reply_text(
            response,
            parse_mode=None,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("❌ Unable to extract product info.")

# ============ DO NOT CHANGE BELOW ============
def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))

    print("✅ Bot is running! Send a link...")
    application.run_polling()

if __name__ == "__main__":
    main()
