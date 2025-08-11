import logging
import re
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, List, Any
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from telegram import Update, Message
from telegram.ext import Application, MessageHandler, filters, ContextTypes, CommandHandler
from io import BytesIO
from PIL import Image
import pytesseract

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot Configuration
BOT_TOKEN = "8475626328:AAHpLsi5hL-1UfKGOdOWxQBHbDPyU6ExTG8"
BOT_USERNAME = "@Py_hostbot"

# Enhanced supported URL shorteners
SHORTENERS = [
    'cutt.ly', 'spoo.me', 'amzn.to', 'amzn-to.co', 'fkrt.cc', 
    'bitli.in', 'da.gd', 'wishlink.com', 'bit.ly', 'tinyurl.com', 
    'short.link', 'ow.ly', 'is.gd', 't.co', 'goo.gl', 'rb.gy',
    'short.gy', 'cutt.ly', 'tiny.cc', 'v.gd', 'x.co'
]

# Enhanced gender keywords
GENDER_KEYWORDS = {
    'Men': ['men', "men's", 'male', 'boy', 'boys', 'gents', 'gentleman', 'masculine'],
    'Women': ['women', "women's", 'female', 'girl', 'girls', 'ladies', 'lady', 'feminine'],
    'Kids': ['kids', 'children', 'child', 'baby', 'infant', 'toddler', 'teen'],
    'Unisex': ['unisex', 'universal', 'both', 'all']
}

# Enhanced quantity keywords
QUANTITY_KEYWORDS = [
    r'pack\s+of\s+\d+', r'set\s+of\s+\d+', r'\d+\s*pcs?', r'\d+\s*pieces?',
    r'\d+\s*kg', r'\d+\s*g(?:ram)?', r'\d+\s*ml', r'\d+\s*l(?:itr?e)?',
    r'combo\s+\d+', r'pair', r'\d+\s*pack', r'multipack'
]

# Enhanced size patterns
SIZE_PATTERNS = [
    'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL', '2XL', '3XL', '4XL', '5XL',
    'FREE SIZE', 'ONE SIZE', 'ADJUSTABLE', '28', '30', '32', '34', '36', '38', '40', '42'
]

# Platform-specific selectors
PLATFORM_SELECTORS = {
    'amazon': {
        'title': ['#productTitle', 'span[data-a-color="base"]', '.product-title'],
        'price': ['.a-price-whole', '.a-offscreen', '.a-price.a-text-price'],
        'original_price': ['.a-text-strike', '.a-price.a-text-strike'],
        'discount': ['.savingsPercentage', '.a-color-price'],
        'sizes': ['.a-button-text', '.swatchElement'],
        'availability': ['#availability span', '.a-color-success']
    },
    'flipkart': {
        'title': ['.B_NuCI', '._35KyD6', '.x2Jiya'],
        'price': ['._1_WHN1', '._30jeq3', '.CEmiEU'],
        'original_price': ['._3I9_wc', '._2MRP4d'],
        'discount': ['._3Ay6Sb', '._1uv9Cb'],
        'sizes': ['._1fGeJ5', '._8vVO0'],
        'availability': ['._16FRp0']
    },
    'meesho': {
        'title': ['[data-testid="product-title"]', '.sc-fubCfw', '.ProductCard__ProductName'],
        'price': ['[data-testid="current-price"]', '.ProductCard__ProductPrice'],
        'original_price': ['[data-testid="original-price"]', '.ProductCard__ProductMRP'],
        'discount': ['[data-testid="discount"]'],
        'sizes': ['.VariantButton', '.size-variant'],
        'availability': ['[data-testid="delivery-info"]']
    },
    'myntra': {
        'title': ['.pdp-name', '.pdp-title'],
        'price': ['.pdp-price', '.discount-price'],
        'original_price': ['.mrp', '.original-price'],
        'discount': ['.discount-percent'],
        'sizes': ['.size-buttons-size-text', '.size-button'],
        'availability': ['.delivery-options']
    },
    'ajio': {
        'title': ['.prod-name', '.product-title'],
        'price': ['.prod-sp', '.price'],
        'original_price': ['.prod-op', '.orig-price'],
        'discount': ['.prod-discnt', '.discount'],
        'sizes': ['.size-variant', '.swatch'],
        'availability': ['.delivery-info']
    },
    'snapdeal': {
        'title': ['.pdp-title', '.product-title'],
        'price': ['.payBlkBig', '.product-price'],
        'original_price': ['.strike', '.product-mrp'],
        'discount': ['.percent-off', '.discount-label'],
        'sizes': ['.size-buttons', '.variant'],
        'availability': ['.pdp-availability']
    }
}

class LinkProcessor:
    @staticmethod
    def extract_links(text: str) -> List[str]:
        if not text:
            return []
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]\(\)]*[^\s<>"{}|\\^`\[\]\(\)\.,;:!?]'
        urls = re.findall(url_pattern, text)
        cleaned_urls = []
        for url in urls:
            url = re.sub(r'[.,:;!?\)]+$', '', url)
            if url:
                cleaned_urls.append(url)
        return cleaned_urls

    @staticmethod
    def is_shortened_url(url: str) -> bool:
        try:
            domain = urlparse(url).netloc.lower()
            return any(shortener in domain for shortener in SHORTENERS)
        except:
            return False

    @staticmethod
    async def unshorten_url(url: str, session: aiohttp.ClientSession, max_redirects: int = 10) -> str:
        try:
            async with session.head(url, allow_redirects=True, timeout=15) as response:
                final_url = str(response.url)
                if final_url != url:
                    logger.info(f"Unshortened: {url} -> {final_url}")
                return final_url
        except:
            try:
                async with session.get(url, allow_redirects=True, timeout=15) as response:
                    final_url = str(response.url)
                    if final_url != url:
                        logger.info(f"Unshortened (GET): {url} -> {final_url}")
                    return final_url
            except Exception as e:
                logger.warning(f"Failed to unshorten {url}: {e}")
                return url

    @staticmethod
    def clean_affiliate_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            if 'amazon' in domain or 'amzn' in domain:
                product_match = re.search(r'/([A-Z0-9]{10})', parsed.path)
                if product_match:
                    return f"https://www.amazon.in/dp/{product_match.group(1)}"
                query_params = parse_qs(parsed.query)
                affiliate_params = ['tag', 'ref', 'linkCode', 'linkId', 'psc', 'keywords']
                for param in affiliate_params:
                    query_params.pop(param, None)
                clean_query = urlencode({k: v[0] for k, v in query_params.items() if v}, doseq=False)
                return urlunparse(parsed._replace(query=clean_query))
            elif 'flipkart' in domain:
                query_params = parse_qs(parsed.query)
                affiliate_params = ['affid', 'affExtParam1', 'affExtParam2', 'pid']
                for param in affiliate_params:
                    query_params.pop(param, None)
                clean_query = urlencode({k: v[0] for k, v in query_params.items() if v}, doseq=False)
                return urlunparse(parsed._replace(query=clean_query))
            elif 'meesho' in domain:
                return url.split('?')[0]
            elif 'myntra' in domain:
                return url.split('?')[0]
            elif 'ajio' in domain:
                return url.split('?')[0]
            elif 'snapdeal' in domain:
                query_params = parse_qs(parsed.query)
                affiliate_params = ['aff_id', 'utm_source', 'utm_medium']
                for param in affiliate_params:
                    query_params.pop(param, None)
                clean_query = urlencode({k: v[0] for k, v in query_params.items() if v}, doseq=False)
                return urlunparse(parsed._replace(query=clean_query))
            return url
        except Exception as e:
            logger.warning(f"Error cleaning URL {url}: {e}")
            return url

class ProductScraper:
    @staticmethod
    def get_platform(url: str) -> str:
        domain = urlparse(url).netloc.lower()
        if 'amazon' in domain:
            return 'amazon'
        elif 'flipkart' in domain:
            return 'flipkart'
        elif 'meesho' in domain:
            return 'meesho'
        elif 'myntra' in domain:
            return 'myntra'
        elif 'ajio' in domain:
            return 'ajio'
        elif 'snapdeal' in domain:
            return 'snapdeal'
        return 'generic'

    @staticmethod
    async def scrape_product(url: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        try:
            platform = ProductScraper.get_platform(url)
            headers = ProductScraper.get_headers(platform)
            await asyncio.sleep(0.5)
            async with session.get(url, headers=headers, timeout=20) as response:
                if response.status != 200:
                    logger.warning(f"HTTP {response.status} for {url}")
                    return {'error': f'Access denied or page not found (HTTP {response.status})'}
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                product_info = {
                    'title': '',
                    'price': '',
                    'original_price': '',
                    'discount': '',
                    'sizes': [],
                    'availability': '',
                    'platform': platform.title(),
                    'pin': '',
                    'gender': '',
                    'quantity': '',
                    'image_url': ''
                }
                if platform in PLATFORM_SELECTORS:
                    selectors = PLATFORM_SELECTORS[platform]
                    product_info['title'] = ProductScraper._extract_with_selectors(soup, selectors.get('title', []))
                    product_info['price'] = ProductScraper._extract_price_with_selectors(soup, selectors.get('price', []))
                    product_info['original_price'] = ProductScraper._extract_price_with_selectors(soup, selectors.get('original_price', []))
                    product_info['discount'] = ProductScraper._extract_with_selectors(soup, selectors.get('discount', []))
                    product_info['availability'] = ProductScraper._extract_with_selectors(soup, selectors.get('availability', []))
                    product_info['sizes'] = ProductScraper._extract_sizes_with_selectors(soup, selectors.get('sizes', []))
                else:
                    product_info.update(ProductScraper._generic_extraction(soup, html))
                product_info['title'] = ProductScraper._clean_title(product_info['title'])
                product_info['gender'] = ProductScraper._detect_gender(product_info['title'])
                product_info['quantity'] = ProductScraper._detect_quantity(product_info['title'])
                product_info['image_url'] = ProductScraper._extract_image(soup, platform)
                if platform == 'meesho':
                    product_info['pin'] = ProductScraper._extract_pin(soup, html) or '110001'
                logger.info(f"Scraped {platform} product: {product_info['title'][:30]}...")
                return product_info
        except asyncio.TimeoutError:
            logger.error(f"Timeout scraping {url}")
            return {'error': 'Timeout while loading page'}
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return {'error': f'Failed to load product: {str(e)}'}

    @staticmethod
    def get_headers(platform: str) -> Dict[str, str]:
        base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        if platform == 'amazon':
            base_headers.update({
                'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"'
            })
        elif platform == 'flipkart':
            base_headers.update({
                'X-User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 FKUA/website/42/website/Desktop'
            })
        return base_headers

    @staticmethod
    def _extract_with_selectors(soup: BeautifulSoup, selectors: List[str]) -> str:
        for selector in selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    text = element.get_text(strip=True) if not selector.startswith('meta') else element.get('content', '').strip()
                    if text and len(text) > 2:
                        return text
            except:
                continue
        return ''

    @staticmethod
    def _extract_price_with_selectors(soup: BeautifulSoup, selectors: List[str]) -> str:
        price_text = ProductScraper._extract_with_selectors(soup, selectors)
        if price_text:
            price_text = re.sub(r'[^\d.]', '', price_text)
            price_match = re.search(r'\d+(?:\.\d{2})?', price_text)
            if price_match:
                return price_match.group(0)
        return ''

    @staticmethod
    def _extract_sizes_with_selectors(soup: BeautifulSoup, selectors: List[str]) -> List[str]:
        sizes = set()
        for selector in selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True).upper()
                    for size_pattern in SIZE_PATTERNS:
                        if size_pattern in text:
                            sizes.add(size_pattern)
            except:
                continue
        return sorted(list(sizes))

    @staticmethod
    def _extract_image(soup: BeautifulSoup, platform: str) -> str:
        image_selectors = {
            'amazon': ['#landingImage', '.a-dynamic-image', '.imgTagWrapper img'],
            'flipkart': ['.q6DClP img', '._396cs4 img', '.CXW8mj img'],
            'meesho': ['[data-testid="product-image"]', '.sc-eCssSg img'],
            'myntra': ['.pdp-image', '.image-grid-image'],
            'ajio': ['.prod-img img', '.main-image'],
            'snapdeal': ['.cloudzoom', '.product-image img'],
            'generic': ['meta[property="og:image"]', '.product-image img', 'img[alt*="product"]']
        }
        selectors = image_selectors.get(platform, image_selectors['generic'])
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                img_url = element.get('content' if selector.startswith('meta') else 'src', '') or element.get('data-src', '')
                if img_url.startswith('http'):
                    return img_url
        return ''

    @staticmethod
    def _generic_extraction(soup: BeautifulSoup, html: str) -> Dict[str, Any]:
        result = {}
        title_selectors = [
            'h1', 'meta[property="og:title"]', 'meta[name="twitter:title"]', 
            'title', '.product-title', '.product-name'
        ]
        result['title'] = ProductScraper._extract_with_selectors(soup, title_selectors)
        price_pattern = r'[₹Rs\.]\s*[\d,]+(?:\.\d{2})?'
        prices = re.findall(price_pattern, html)
        if prices:
            result['price'] = re.sub(r'[^\d]', '', prices[0])
        return result

    @staticmethod
    def _clean_title(title: str) -> str:
        if not title:
            return ''
        remove_patterns = [
            r'\b(Buy|Shop|Online|India|Best|Price|Sale|Discount|Offer|Deal|Exclusive|Limited|Time|Only)\b',
            r'\b(Amazon|Flipkart|Meesho|Myntra|Ajio|Snapdeal|Shopping)\b',
            r'[|\-].*$', r'\([^)]*\)', r'[★☆]+.*$'
        ]
        for pattern in remove_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        title = ' '.join(title.split())
        if len(title) > 60:
            title = title[:60].rsplit(' ', 1)[0] + '...'
        return title.strip()

    @staticmethod
    def _detect_gender(title: str) -> str:
        if not title:
            return ''
        title_lower = title.lower()
        for gender, keywords in GENDER_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return gender
        return ''

    @staticmethod
    def _detect_quantity(title: str) -> str:
        if not title:
            return ''
        title_lower = title.lower()
        for pattern in QUANTITY_KEYWORDS:
            match = re.search(pattern, title_lower, re.IGNORECASE)
            if match:
                return match.group(0).title()
        return ''

    @staticmethod
    def _extract_pin(soup: BeautifulSoup, html: str) -> str:
        pin_selectors = ['input[placeholder*="pin"]', '[data-testid="pincode"]']
        for selector in pin_selectors:
            element = soup.select_one(selector)
            if element:
                value = element.get('value') or element.get('placeholder', '')
                pin_match = re.search(r'\b\d{6}\b', value)
                if pin_match:
                    return pin_match.group(0)
        pin_pattern = r'\b\d{6}\b'
        pins = re.findall(pin_pattern, html)
        for pin in pins:
            if pin.startswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
                return pin
        return ''

class MessageFormatter:
    @staticmethod
    def format_product(product_info: Dict[str, Any], url: str) -> str:
        if product_info.get('error'):
            return f"❌ {product_info['error']}\n\n{url if url else ''}\n\n@reviewcheckk"
        parts = []
        title_parts = []
        if product_info.get('platform'):
            title_parts.append(f"[{product_info['platform']}]")
        if product_info.get('gender'):
            title_parts.append(product_info['gender'])
        if product_info.get('quantity'):
            title_parts.append(product_info['quantity'])
        if product_info.get('title'):
            title_parts.append(product_info['title'])
        if product_info.get('price'):
            price_text = f"@{product_info['price']} rs"
            if product_info.get('original_price'):
                price_text += f" (MRP {product_info['original_price']} rs)"
            if product_info.get('discount'):
                price_text += f" {product_info['discount']} OFF"
            title_parts.append(price_text)
        if title_parts:
            parts.append(' '.join(title_parts))
        if url:
            parts.append(url)
        parts.append('')
        info_parts = []
        if product_info.get('sizes'):
            if len(product_info['sizes']) >= 8:
                info_parts.append('Size - All')
            else:
                info_parts.append(f"Size - {', '.join(product_info['sizes'])}")
        if 'meesho' in (url.lower() if url else '') and product_info.get('pin'):
            info_parts.append(f"Pin - {product_info['pin']}")
        if info_parts:
            parts.extend(info_parts)
            parts.append('')
        parts.append('@reviewcheckk')
        return '\n'.join(parts)

class DealBot:
    def __init__(self):
        self.session = None
        self.processed_messages = set()
        self.rate_limit_delay = 1.0

    async def initialize(self):
        if not self.session:
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)

    async def cleanup(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message or update.channel_post
        if not message:
            return
        message_id = f"{message.chat_id}_{message.message_id}"
        if message_id in self.processed_messages:
            return
        self.processed_messages.add(message_id)
        if len(self.processed_messages) > 1000:
            self.processed_messages.clear()
        await self.initialize()
        text = message.text or message.caption or ''
        links = LinkProcessor.extract_links(text)
        if links:
            logger.info(f"Processing {len(links)} links from chat {message.chat_id}")
            for i, url in enumerate(links[:5]):
                await self._process_single_link(message, url, context)
                if i < len(links[:5]) - 1:
                    await asyncio.sleep(self.rate_limit_delay)
        elif message.photo:
            await self._process_image(message, context)

    async def _process_single_link(self, message: Message, url: str, context: ContextTypes.DEFAULT_TYPE):
        try:
            if LinkProcessor.is_shortened_url(url):
                url = await LinkProcessor.unshorten_url(url, self.session)
            clean_url = LinkProcessor.clean_affiliate_url(url)
            platform = ProductScraper.get_platform(clean_url)
            product_info = await ProductScraper.scrape_product(clean_url, self.session)
            if not product_info.get('title') and message.caption:
                product_info['title'] = ProductScraper._clean_title(message.caption)
            output = MessageFormatter.format_product(product_info, clean_url)
            await self._send_safe_response(message, output, context)
        except Exception as e:
            logger.error(f"Error processing link {url}: {e}")
            error_msg = f"❌ Could not process link\n\n{url}\n\n@reviewcheckk"
            await self._send_safe_response(message, error_msg, context)

    async def _process_image(self, message: Message, context: ContextTypes.DEFAULT_TYPE):
        try:
            photo = message.photo[-1]
            file = await photo.get_file()
            bytearray_ = await file.download_as_bytearray()
            img = Image.open(BytesIO(bytearray_))
            ocr_text = pytesseract.image_to_string(img)
            links = LinkProcessor.extract_links(ocr_text)
            if links:
                for url in links[:5]:
                    await self._process_single_link(message, url, context)
            else:
                product_info = self._extract_info_from_ocr(ocr_text)
                output = MessageFormatter.format_product(product_info, '')
                await self._send_safe_response(message, output, context)
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            error_msg = "❌ Could not process image\n\n@reviewcheckk"
            await self._send_safe_response(message, error_msg, context)

    def _extract_info_from_ocr(self, text: str) -> Dict[str, Any]:
        product_info = {
            'platform': 'Screenshot',
            'title': '',
            'price': '',
            'original_price': '',
            'discount': '',
            'sizes': [],
            'pin': '',
            'gender': '',
            'quantity': ''
        }
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            product_info['title'] = ' '.join(lines[:3])[:100]
        price_match = re.search(r'[₹Rs\.]\s*([\d,]+(?:\.\d{2})?)', text, re.I)
        if price_match:
            product_info['price'] = re.sub(r'[^\d.]', '', price_match.group(1))
        orig_match = re.search(r'(?:MRP|Original)\s*[:₹Rs\.]\s*([\d,]+(?:\.\d{2})?)', text, re.I)
        if orig_match:
            product_info['original_price'] = re.sub(r'[^\d.]', '', orig_match.group(1))
        if product_info.get('price') and product_info.get('original_price'):
            try:
                p = float(product_info['price'])
                o = float(product_info['original_price'])
                if o > p:
                    disc = round((o - p) / o * 100)
                    product_info['discount'] = f"{disc}%"
            except:
                pass
        upper_text = text.upper()
        product_info['sizes'] = [s for s in SIZE_PATTERNS if s in upper_text]
        pin_match = re.search(r'\b\d{6}\b', text)
        if pin_match:
            product_info['pin'] = pin_match.group(0)
        product_info['gender'] = ProductScraper._detect_gender(product_info['title'])
        product_info['quantity'] = ProductScraper._detect_quantity(product_info['title'])
        return product_info

    async def _send_safe_response(self, message: Message, text: str, context: ContextTypes.DEFAULT_TYPE):
        try:
            await message.reply_text(text, disable_web_page_preview=True)
            logger.info(f"Response sent to chat {message.chat_id}")
        except Exception as e:
            try:
                await context.bot.send_message(chat_id=message.chat_id, text=text, disable_web_page_preview=True)
                logger.warning("Sent fallback message")
            except Exception as fallback_e:
                logger.error(f"Failed to send response: {fallback_e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Deal Bot Active!\n\nSend me any product link or screenshot and I'll extract the deal information.\nWorks with shortened links too!\n\nSupported: Amazon, Flipkart, Meesho, Myntra, Ajio, Snapdeal and more!"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    bot = DealBot()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT | filters.CAPTION | filters.PHOTO, bot.process_message))
    application.add_error_handler(error_handler)
    print(f"✅ Bot @{BOT_USERNAME} is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
