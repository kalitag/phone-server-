# bot.py
import os
import re
import requests
import logging
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ==================== CONFIG ====================
# ✅ CHANGE THIS: Get a new token from @BotFather
BOT_TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"  # ← Replace with your real token

# Default pin code
DEFAULT_PIN = "110001"
# =================================================

# Enable logging so you can SEE what’s happening
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO  # ← You will see this in console
)
logger = logging.getLogger(__name__)

def extract_price(text):
    match = re.search(r'(?:₹|Rs?\s*)(\d+)', text)
    return match.group(1) if match else ""

def extract_quantity(text):
    match = re.search(r'\b\d+(?:ml|g|kg|l|pcs|pack|set)s?\b', text, re.I)
    return match.group().lower() if match else ""

def clean_title(text):
    # Remove fluff
    text = re.sub(r'\b(?:best|offer|deal|sale|new|latest|trending|fashion|stylish|premium|luxury)\b', '', text, flags=re.I)
    # Clean special chars
    text = re.sub(r'[-_]+', ' ', text)
    text = re.sub(r'[^a-zA-Z0-9\s]', '', text)
    # Capitalize, deduplicate
    words = [w.capitalize() for w in text.split() if len(w) > 1]
    return " ".join(dict.fromkeys(words)).strip()

async def unshorten_url(url):
    try:
        logger.info(f"Resolving: {url}")
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=5,
            headers={"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"}
        )
        logger.info(f"Resolved to: {resp.url}")
        return resp.url
    except Exception as e:
        logger.error(f"Unshorten failed: {e}")
        return url

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        logger.warning("No message object")
        return

    logger.info(f"Received message: {message.text or message.caption or 'Photo only'}")

    # Handle image with caption
    if message.photo and message.caption:
        logger.info("Photo with caption detected")
        url_match = re.search(r'https?://[^\s]+', message.caption)
        if not url_match:
            logger.warning("No URL in caption")
            return

        url = url_match.group(0)
        clean_url = await unshorten_url(url)
        price = extract_price(message.caption)
        quantity = extract_quantity(message.caption)
        product = clean_title(message.caption)

        title = f"{quantity} {product}".strip()
        price_text = f"@{price} rs" if price else "@ rs"
        final_title = f"{title} {price_text}"

        lines = [final_title]
        if "meesho.com" in clean_url.lower():
            lines.append("")
            lines.append("Size - All")
            pin_match = re.search(r'\b\d{6}\b', message.caption)
            pin = pin_match.group(0) if pin_match else DEFAULT_PIN
            lines.append(f"Pin - {pin}")
        lines.append("")
        lines.append("@reviewcheckk")

        response = "\n".join(lines)
        logger.info(f"Sending photo + response:\n{response}")

        await message.reply_photo(
            photo=message.photo[-1].file_id,
            caption=response,
            parse_mode=None,
            disable_web_page_preview=True
        )
        return

    # Handle image only
    if message.photo and not message.caption:
        logger.info("Photo without caption")
        await message.reply_photo(
            photo=message.photo[-1].file_id,
            caption="No title provided",
            parse_mode=None
        )
        return

    # Handle text message
    text = message.text or ""
    url_match = re.search(r'https?://[^\s]+', text)
    if not url_match:
        logger.warning("No URL in text message")
        return

    try:
        url = url_match.group(0)
        logger.info(f"Processing URL: {url}")
        clean_url = await unshorten_url(url)
        price = extract_price(text)
        quantity = extract_quantity(text)
        product = clean_title(text)

        title = f"{quantity} {product}".strip()
        price_text = f"@{price} rs" if price else "@ rs"
        final_title = f"{title} {price_text}"

        lines = [final_title]
        if "meesho.com" in clean_url.lower():
            lines.append("")
            lines.append("Size - All")
            pin_match = re.search(r'\b\d{6}\b', text)
            pin = pin_match.group(0) if pin_match else DEFAULT_PIN
            lines.append(f"Pin - {pin}")
        lines.append("")
        lines.append("@reviewcheckk")

        response = "\n".join(lines)
        logger.info(f"Sending text response:\n{response}")

        await message.reply_text(
            response,
            parse_mode=None,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error in text handler: {e}")

def main():
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: You must set BOT_TOKEN to a real token from @BotFather")
        return

    print("✅ Starting bot... Check logs above for activity")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
