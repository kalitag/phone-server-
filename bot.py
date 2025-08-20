# bot.py
# Telegram Deal Title Bot - @reviewcheckk
# Strictly follows: [quantity] [brand] [product] @[price] rs
# Supports: Amazon, Flipkart, Meesho, Myntra, Ajio, Snapdeal, Wishlink
# Handles: Links, images, forwarded messages, shorteners
# Always ends with @reviewcheckk

import os
import re
import logging
import requests
from urllib.parse import urlparse, parse_qs
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==================== CONFIGURATION ====================
# SECURITY: Never hardcode token in production
# Use environment variable: export BOT_TOKEN="your_token_here"
BOT_TOKEN = os.getenv("BOT_TOKEN", "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s")

# Default pin code if not found in message
DEFAULT_PIN = "110001"

# Words to remove from title (marketing fluff)
FLUFF_WORDS = [
    'best', 'offer', 'deal', 'sale', 'new', 'latest', 'trending',
    'fashion', 'stylish', 'premium', 'luxury', 'exclusive',
    'special', 'limited', 'hot', 'super', 'mega', 'great', 'amazing',
    'combo', 'pack', 'set', 'off', 'discount', 'original', 'genuine',
    'top', 'quality', 'high', 'value', 'buy', 'online', 'shop'
]

# Known brands to prioritize
BRANDS = [
    "Vivel", "Dettol", "Mamaearth", "Boat", "Nike", "Puma", "Wildcraft",
    "OnePlus", "Samsung", "Apple", "Syska", "Amul", "Parle", "Nivea",
    "Himalaya", "Boroplus", "Garnier", "Lakme", "Allen Solly"
]

# Clothing keywords for gender detection
CLOTHING_KEYWORDS = [
    'shirt', 'tshirt', 't-shirt', 'dress', 'kurti', 'saree', 'jeans',
    'trouser', 'pant', 'shorts', 'skirt', 'top', 'blouse', 'jacket',
    'sweater', 'hoodie', 'suit', 'blazer', 'coat', 'leggings', 'innerwear'
]

# Shorteners to resolve
SHORTENERS = [
    'fkrt.cc', 'amzn.to', 'spoo.me', 'cutt.ly', 'bitly.in',
    'da.gd', 'wishlink.com', 'bit.ly', 't.co'
]
# ======================================================

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def detect_platform(url: str) -> str:
    """Detect e-commerce platform from URL"""
    domain = urlparse(url).netloc.lower()
    if "meesho" in domain:
        return "meesho"
    for p in ["amazon", "flipkart", "myntra", "ajio", "snapdeal", "wishlink"]:
        if p in domain:
            return "other"
    return "other"

async def unshorten_url(url: str) -> str:
    """Resolve short URLs and clean affiliate tags"""
    try:
        # Add headers to avoid bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36"
        }
        resp = requests.get(url, allow_redirects=True, timeout=5, headers=headers)
        final_url = resp.url

        # Clean query parameters (remove affiliate tags)
        parsed = urlparse(final_url)
        query_params = parse_qs(parsed.query)
        clean_params = {
            k: v for k, v in query_params.items()
            if not re.search(r'tag|ref|aff|utm|src|mcid|icid|camp|click|pid|share', k, re.I)
        }
        query_str = '&'.join(f"{k}={v[0]}" for k, v in clean_params.items())
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if query_str:
            clean_url += f"?{query_str}"
        return clean_url
    except Exception as e:
        logger.warning(f"URL unshorten failed: {e}")
        return url

def extract_price(text: str) -> str:
    """Extract price digits only if ₹ or Rs is present"""
    match = re.search(r'(?:₹|Rs?\s*)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', text)
    return match.group(1).replace(',', '') if match else ""

def extract_quantity(text: str) -> str:
    """Extract quantity like 200ml, 5pcs"""
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
    """Extract gender from text"""
    text_lower = text.lower()
    if any(w in text_lower for w in ['men', 'man', 'gents', 'male']):
        return "Men"
    if any(w in text_lower for w in ['women', 'woman', 'ladies', 'female']):
        return "Women"
    if any(w in text_lower for w in ['kid', 'child']):
        return "Kids"
    return ""

def clean_title(text: str) -> str:
    """Clean product name: remove fluff, brand, special chars"""
    # Remove fluff
    for word in FLUFF_WORDS:
        text = re.sub(r'\b' + re.escape(word) + r'\b', '', text, flags=re.I)
    # Remove brand (if detected later)
    for brand in BRANDS:
        text = re.sub(re.escape(brand), '', text, flags=re.I)
    # Remove price mentions
    text = re.sub(r'(?:₹|Rs?)\s*\d+', '', text)
    # Replace separators
    text = re.sub(r'[-_]+', ' ', text)
    # Keep only letters, numbers, spaces
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    # Split, capitalize, remove duplicates
    words = [w.capitalize() for w in text.split() if len(w) > 1]
    return " ".join(dict.fromkeys(words)).strip()

async def generate_response(url: str, message_text: str, platform: str) -> str:
    """Generate response in exact format"""
    clean_url = await unshorten_url(url)
    price = extract_price(message_text)
    quantity = extract_quantity(message_text)
    brand = extract_brand(message_text)
    gender = extract_gender(message_text) if is_clothing(message_text) else ""
    product = clean_title(message_text)

    # Build title
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
        lines.append("")
        lines.append("Size - All")
        pin_match = re.search(r'\b\d{6}\b', message_text)
        pin = pin_match.group(0) if pin_match else DEFAULT_PIN
        lines.append(f"Pin - {pin}")
    lines.append("")
    lines.append("@reviewcheckk")
    return "\n".join(lines)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for all messages"""
    message = update.message
    if not message:
        return

    # Handle forwarded messages
    if message.forward_date:
        logger.info(f"Forwarded message from {message.forward_from_chat.title if message.forward_from_chat else 'user'}")

    # Extract text
    text = message.text or message.caption or ""

    # Handle images
    if message.photo:
        photo = message.photo[-1]  # Highest resolution
        file_id = photo.file_id

        if message.caption and re.search(r'https?://', message.caption):
            try:
                url_match = re.search(r'https?://[^\s]+', message.caption)
                if not url_match:
                    return
                url = url_match.group(0)
                platform = detect_platform(url)
                response = await generate_response(url, message.caption, platform)
                await message.reply_photo(photo=file_id, caption=response, parse_mode=None, disable_web_page_preview=True)
                return
            except Exception as e:
                logger.error(f"Photo caption error: {e}")

        else:
            await message.reply_photo(photo=file_id, caption="No title provided", parse_mode=None)
            return

    # Handle text messages
    if text:
        url_match = re.search(r'https?://[^\s]+', text)
        if not url_match:
            return
        try:
            url = url_match.group(0)
            platform = detect_platform(url)
            response = await generate_response(url, text, platform)
            await message.reply_text(response, parse_mode=None, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Text message error: {e}")

def main():
    """Start the bot"""
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.critical("❌ BOT_TOKEN not set! Use environment variable.")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    logger.info("✅ Bot is running! Send a link...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
