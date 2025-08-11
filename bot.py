import logging
import re
import aiohttp
from typing import Dict, List, Any
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ================= LOGGING =================
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

SHORTENERS = [
    'cutt.ly', 'spoo.me', 'amzn.to', 'amzn-to.co', 'fkrt.cc', 'bitli.in',
    'da.gd', 'wishlink.com', 'bit.ly', 'tinyurl.com', 'short.link', 'ow.ly',
    'is.gd', 't.co', 'goo.gl', 'rb.gy', 'short.gy', 'tiny.cc', 'v.gd', 'x.co'
]

GENDER_KEYWORDS = {
    'Men': ['men', "men's", 'male', 'boy', 'boys', 'gents', 'gentleman', 'masculine'],
    'Women': ['women', "women's", 'female', 'girl', 'girls', 'ladies', 'lady', 'feminine'],
    'Kids': ['kids', 'children', 'child', 'baby', 'infant', 'toddler', 'teen'],
    'Unisex': ['unisex', 'universal', 'both', 'all']
}

QUANTITY_KEYWORDS = [
    r'pack\s+of\s+\d+', r'set\s+of\s+\d+', r'\d+\s*pcs?', r'\d+\s*pieces?',
    r'\d+\s*kg', r'\d+\s*g(?:ram)?', r'\d+\s*ml', r'\d+\s*l(?:itr?e)?',
    r'combo\s+\d+', r'pair', r'\d+\s*pack', r'multipack'
]

SIZE_PATTERNS = [
    'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '2XL', '3XL', '4XL', '5XL',
    'FREE SIZE', 'ONE SIZE', 'ADJUSTABLE', '28', '30', '32', '34', '36', '38', '40', '42'
]

PLATFORM_SELECTORS = {
    'amazon': {
        'title': ['#productTitle'],
        'price': ['.a-price-whole']
    },
    'flipkart': {
        'title': ['.B_NuCI'],
        'price': ['._1_WHN1']
    },
    'meesho': {
        'title': ['[data-testid="product-title"]'],
        'price': ['[data-testid="current-price"]']
    }
}

# ================= LINK PROCESSOR =================
class LinkProcessor:
    @staticmethod
    def extract_links(text: str) -> List[str]:
        if not text:
            return []
        url_pattern = r'https?://[^\s<>()"\']+'
        urls = re.findall(url_pattern, text)
        return [u.rstrip('.,:;!?') for u in urls]

    @staticmethod
    def is_shortened_url(url: str) -> bool:
        try:
            domain = urlparse(url).netloc.lower()
            return any(shortener in domain for shortener in SHORTENERS)
        except:
            return False

    @staticmethod
    async def unshorten_url(url: str, session: aiohttp.ClientSession) -> str:
        try:
            async with session.get(url, allow_redirects=True, timeout=20) as resp:
                return str(resp.url)
        except Exception as e:
            logger.warning(f"Unshorten failed: {e}")
            return url

    @staticmethod
    def clean_affiliate_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if 'amazon' in domain:
                match = re.search(r'/([A-Z0-9]{10})', parsed.path)
                if match:
                    return f"https://www.amazon.in/dp/{match.group(1)}"
            elif 'flipkart' in domain or 'meesho' in domain:
                return url.split('?')[0]
            return url
        except:
            return url

# ================= PRODUCT SCRAPER =================
class ProductScraper:
    @staticmethod
    def get_platform(url: str) -> str:
        domain = urlparse(url).netloc.lower()
        if 'amazon' in domain:
            return 'Amazon'
        elif 'flipkart' in domain:
            return 'Flipkart'
        elif 'meesho' in domain:
            return 'Meesho'
        return 'Generic'

    @staticmethod
    def detect_gender(title: str) -> str:
        title_lower = title.lower()
        for gender, keywords in GENDER_KEYWORDS.items():
            if any(kw in title_lower for kw in keywords):
                return gender
        return ""

    @staticmethod
    def detect_quantity(title: str) -> str:
        for pattern in QUANTITY_KEYWORDS:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    @staticmethod
    async def scrape_product(url: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        platform = ProductScraper.get_platform(url)
        product_info = {
            'platform': platform, 'title': '', 'price': '',
            'gender': '', 'quantity': '', 'sizes': [],
            'pin': '', 'brand': ''
        }

        try:
            async with session.get(url, timeout=20) as resp:
                if resp.status != 200:
                    return {'error': f"Access denied: {resp.status}"}
                html = await resp.text()

            soup = BeautifulSoup(html, 'html.parser')

            # Title
            selectors = PLATFORM_SELECTORS.get(platform.lower(), {})
            for sel in selectors.get('title', []):
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    product_info['title'] = el.get_text(strip=True)
                    break

            # Price
            for sel in selectors.get('price', []):
                el = soup.select_one(sel)
                if el and el.get_text(strip=True):
                    price_txt = re.sub(r'[^\d]', '', el.get_text(strip=True))
                    product_info['price'] = price_txt
                    break

            # Brand detection
            brand_tag = soup.find("meta", property="og:brand")
            if brand_tag and brand_tag.get("content"):
                product_info['brand'] = brand_tag.get("content").strip()
            else:
                if product_info['title']:
                    first_word = product_info['title'].split()[0]
                    if first_word and first_word[0].isupper() and len(first_word) > 2:
                        product_info['brand'] = first_word

            # Gender & Quantity
            product_info['gender'] = ProductScraper.detect_gender(product_info['title'])
            product_info['quantity'] = ProductScraper.detect_quantity(product_info['title'])

            # Sizes (Meesho only)
            if platform.lower() == "meesho":
                size_elems = soup.select('.VariantButton')
                if size_elems:
                    product_info['sizes'] = [el.get_text(strip=True).upper() for el in size_elems]
                pin_el = soup.find(attrs={"data-testid": "delivery-info"})
                if pin_el:
                    pin_match = re.search(r'\b\d{6}\b', pin_el.get_text())
                    if pin_match:
                        product_info['pin'] = pin_match.group(0)

        except Exception as e:
            logger.error(f"Scrape error: {e}")
            return {'error': str(e)}

        return product_info

# ================= FORMAT OUTPUT =================
def format_product(product_info: Dict[str, Any], url: str) -> str:
    if product_info.get('error'):
        return f"❌ {product_info['error']}\n\n{url}\n\n@reviewcheckk"

    brand = product_info.get('brand', '').strip()
    title = product_info.get('title') or "NA"

    # Remove brand repetition in title
    if brand and title.lower().startswith(brand.lower()):
        title = title[len(brand):].strip()

    gender = product_info.get('gender') or ""
    quantity = product_info.get('quantity') or ""
    price = product_info.get('price') or "0"

    parts = [brand if brand else f"[{product_info.get('platform') or 'NA'}]"]
    if gender: parts.append(gender)
    if quantity: parts.append(quantity)
    if title: parts.append(title)
    parts.append(f"@{price} rs")

    msg = " ".join(parts) + "\n" + (url or "")

    if (product_info.get('platform') or "").lower() == "meesho":
        if product_info.get('sizes'):
            size_text = "Size - All" if len(product_info['sizes']) >= 8 else f"Size - {', '.join(product_info['sizes'])}"
            msg += f"\n{size_text}"
        if product_info.get('pin'):
            msg += f"\nPin - {product_info['pin']}"

    msg += "\n\n@reviewcheckk"
    return msg

# ================= TELEGRAM BOT HANDLERS =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    links = LinkProcessor.extract_links(text)

    async with aiohttp.ClientSession() as session:
        for link in links:
            if LinkProcessor.is_shortened_url(link):
                link = await LinkProcessor.unshorten_url(link, session)
            link = LinkProcessor.clean_affiliate_url(link)

            product_info = await ProductScraper.scrape_product(link, session)
            output_msg = format_product(product_info, link)
            await update.message.reply_text(output_msg)

# ================= MAIN =================
if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
