# File: improved_bot.py
import os
import re
import asyncio
import logging
from typing import Optional, Dict, List
from urllib.parse import urlparse, parse_qs
from telegram import Update, constants
from telegram.ext import Application, MessageHandler, filters, ContextTypes
import requests

# ==================== CONFIGURATION ====================
# NEVER hardcode tokens in production — use environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN", "8327175937:AAGpC7M85iY-kbMVAcKJTrhXzKokWLGctCo")  # Replace via env
BOT_USERNAME = "@Easy_uknowbot"
DEFAULT_PIN = "110001"

# User agents for rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
]

# Platform detection patterns
PLATFORM_PATTERNS = {
    'amazon': [r'amazon\.in', r'amzn\.to', r'amazon\.com'],
    'flipkart': [r'flipkart\.com', r'fkrt\.cc'],
    'meesho': [r'meesho\.com'],
    'myntra': [r'myntra\.com'],
    'ajio': [r'ajio\.com'],
    'snapdeal': [r'snapdeal\.com']
}

SHORTENERS = [
    'spoo.me', 'wishlink.com', 'cutt.ly', 'fkrt.cc', 
    'bitli.in', 'amzn.to', 'da.gd', 'bit.ly', 't.co'
]

CLOTHING_KEYWORDS = [
    'shirt', 'tshirt', 't-shirt', 'dress', 'kurti', 'saree', 'jeans', 
    'trouser', 'pant', 'shorts', 'skirt', 'top', 'blouse', 'jacket',
    'sweater', 'hoodie', 'suit', 'blazer', 'coat', 'leggings',
    'nightwear', 'innerwear', 'bra', 'panty', 'brief', 'boxer'
]

FLUFF_WORDS = [
    'best', 'offer', 'deal', 'sale', 'new', 'latest', 'trending',
    'stylish', 'fashionable', 'premium', 'luxury', 'exclusive',
    'special', 'limited', 'hot', 'super', 'mega', 'great', 'amazing'
]

BRANDS = ["Vivel", "Dettol", "Mamaearth", "Boat", "Nike", "Puma", "Wildcraft", 
          "OnePlus", "Samsung", "Apple", "Syska", "Amul", "Parle", "Nivea"]

# Headers for different platforms
PLATFORM_HEADERS = {
    'meesho': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://www.google.com/',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate'
    },
    'amazon': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/',
        'Sec-Fetch-Mode': 'navigate'
    },
    'flipkart': {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.google.com/'
    }
}
# ====================================================

class ReviewCheckkBot:
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.is_processing = False
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (compatible)"})
        self.logger = self._setup_logger()

    def _setup_logger(self):
        """Setup logging for debugging and monitoring"""
        logging.basicConfig(
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            level=logging.INFO,
            handlers=[
                logging.FileHandler("bot.log"),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)

    def detect_platform(self, url: str) -> Optional[str]:
        """Detect platform from URL"""
        domain = urlparse(url).netloc.lower()
        for platform, patterns in PLATFORM_PATTERNS.items():
            if any(re.search(pattern, domain) for pattern in patterns):
                return platform
        return None

    async def unshorten_url(self, url: str) -> str:
        """Resolve short URLs and remove affiliate parameters"""
        try:
            # Use HEAD first, fallback to GET
            resp = self.session.get(url, allow_redirects=True, timeout=5, stream=True)
            final_url = resp.url

            # Parse and clean query parameters
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
            self.logger.warning(f"URL resolution failed: {e}")
            return url  # Return original on failure

    def extract_price(self, text: str) -> Optional[str]:
        """Extract price digits only if ₹ or Rs is present"""
        match = re.search(r'(?:₹|Rs?\s*)(\d{1,3}(?:,\d{3})*(?:\.\d+)?)', text)
        return match.group(1).replace(',', '') if match else None

    def extract_quantity(self, text: str) -> Optional[str]:
        """Extract quantity like 200ml, 5pcs"""
        match = re.search(r'\b\d+(?:ml|g|kg|l|ltr|pcs|pack|set|unit)s?\b', text, re.I)
        return match.group().lower() if match else None

    def extract_brand(self, text: str) -> Optional[str]:
        """Extract brand from text"""
        for brand in BRANDS:
            if brand.lower() in text.lower():
                return brand
        return None

    def is_clothing(self, text: str) -> bool:
        """Check if product is clothing"""
        text_lower = text.lower()
        return any(word in text_lower for word in CLOTHING_KEYWORDS)

    def extract_gender(self, text: str) -> Optional[str]:
        """Extract gender"""
        text_lower = text.lower()
        if any(w in text_lower for w in ['men', 'man', 'gents', 'male']):
            return "Men"
        if any(w in text_lower for w in ['women', 'woman', 'ladies', 'female']):
            return "Women"
        if any(w in text_lower for w in ['kid', 'child', 'baby']):
            return "Kids"
        return None

    def clean_title(self, text: str, brand: str, quantity: str) -> str:
        """Clean product name"""
        # Remove brand, quantity, price, fluff
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

    async def generate_response(self, url: str, message_text: str) -> str:
        """Generate response in your exact format"""
        clean_url = await self.unshorten_url(url)
        platform = self.detect_platform(clean_url) or "other"
        full_text = message_text

        price = self.extract_price(full_text)
        quantity = self.extract_quantity(full_text)
        brand = self.extract_brand(full_text)
        gender = self.extract_gender(full_text) if self.is_clothing(full_text) else None
        product = self.clean_title(full_text, brand, quantity)

        # Build title: [quantity] [brand] [gender] [product] @[price] rs
        title_parts = []
        if quantity:
            title_parts.append(quantity)
        if brand:
            title_parts.append(brand)
        if gender:
            title_parts.append(gender)
        if product:
            title_parts.append(product)

        title = " ".join(title_parts).strip()
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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main message handler"""
        if not update.message or not (update.message.text or update.message.caption):
            return

        text = update.message.text or update.message.caption
        url_match = re.search(r'https?://[^\s]+', text)
        if not url_match:
            return

        url = url_match.group(0)

        try:
            response = await self.generate_response(url, text)
            await update.message.reply_text(
                response,
                parse_mode=constants.ParseMode.MARKDOWN_V2,
                disable_web_page_preview=True
            )
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
            await update.message.reply_text("❌ Unable to extract product info.")

    async def run(self):
        """Start the bot"""
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_message
        ))

        print("✅ ReviewCheckkBot is running! Send a link...")
        await application.run_polling()


# ==================== RUN BOT ====================
if __name__ == "__main__":
    bot = ReviewCheckkBot()
    asyncio.run(bot.run())
