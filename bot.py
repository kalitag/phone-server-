import logging
import re
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8327175937:AAGoWZPlDM_UX7efZv6_7vJMHDsrZ3-EyIA"
DEFAULT_PIN = "110001"
CHANNEL_TAG = "@reviewcheckk"

# --- LOGGER ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# --- HELPERS ---
def clean_url(url: str) -> str:
    try:
        r = requests.head(url, allow_redirects=True, timeout=8)
        return r.url
    except:
        return url

def extract_title_price(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string if soup.title else "Product"
        title = re.sub(r"\s+", " ", title).strip()

        price = None
        match = re.search(r"₹\s?(\d+)", r.text)
        if match:
            price = match.group(1)

        return title, price
    except Exception as e:
        logging.error(f"Parse error: {e}")
        return "Product", None

def format_message(title: str, price: str, url: str):
    msg = f"{title}"
    if price:
        msg += f" @{price} rs"
    msg += f"\n{url}\n"
    msg += f"Size - All\nPin - {DEFAULT_PIN}\n\n{CHANNEL_TAG}"
    return msg

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Bot active! Send any product link.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    urls = re.findall(r"https?://\S+", text)
    if not urls:
        await update.message.reply_text("❌ No link found.")
        return
    for url in urls:
        full_url = clean_url(url)
        title, price = extract_title_price(full_url)
        msg = format_message(title, price, full_url)
        await update.message.reply_text(msg)

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.run_polling()

if __name__ == "__main__":
    main()
        # Shortened URLs
        for shortener in SHORTENERS:
            pattern = rf'(?:https?://)?(?:{re.escape(shortener)})/[^\s<>"{{}}|\\^`\[\]]+'
            found = re.findall(pattern, text, re.IGNORECASE)
            for url in found:
                if not url.startswith('http'):
                    url = 'https://' + url
                urls.append(url)
        
        # Clean and deduplicate
        cleaned_urls = []
        seen = set()
        for url in urls:
            url = re.sub(r'[.,;:!?\)\]]+$', '', url).strip()
            if url and url not in seen and len(url) > 10:
                cleaned_urls.append(url)
                seen.add(url)
        
        return cleaned_urls
    
    @staticmethod
    def is_shortened_url(url: str) -> bool:
        """Check if URL is shortened"""
        try:
            domain = urlparse(url).netloc.lower()
            return any(shortener in domain for shortener in SHORTENERS)
        except:
            return False
    
    @staticmethod
    async def unshorten_url(url: str, session: aiohttp.ClientSession) -> str:
        """Unshorten URL"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.head(url, allow_redirects=True, timeout=10, headers=headers) as response:
                return str(response.url)
        except:
            try:
                async with session.get(url, allow_redirects=True, timeout=10, headers=headers) as response:
                    return str(response.url)
            except:
                return url
    
    @staticmethod
    def clean_affiliate_url(url: str) -> str:
        """Clean affiliate parameters from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Amazon cleaning
            if 'amazon' in domain:
                asin_match = re.search(r'/dp/([A-Z0-9]{10})', parsed.path)
                if asin_match:
                    return f"https://www.amazon.in/dp/{asin_match.group(1)}"
            
            # Flipkart cleaning
            elif 'flipkart' in domain:
                pid_match = re.search(r'/p/[^/]+/([^/?]+)', parsed.path)
                if pid_match:
                    return f"https://www.flipkart.com/product/p/{pid_match.group(1)}"
            
            # Remove tracking parameters
            query_params = parse_qs(parsed.query)
            clean_params = {}
            tracking_keywords = ['utm_', 'ref', 'tag', 'affiliate', 'fbclid', 'gclid']
            
            for key, value in query_params.items():
                if not any(kw in key.lower() for kw in tracking_keywords):
                    clean_params[key] = value[0]
            
            clean_query = urlencode(clean_params)
            return urlunparse(parsed._replace(query=clean_query))
            
        except:
            return url

class MessageParser:
    """Parse product info from messages and OCR text"""
    
    @staticmethod
    def extract_info(text: str) -> Dict[str, Any]:
        """Extract product info from text"""
        info = {
            'title': '',
            'price': '',
            'brand': '',
            'gender': '',
            'quantity': '',
            'pin': ''
        }
        
        # Extract price
        price_patterns = [
            r'@\s*(\d+)\s*rs',
            r'₹\s*(\d+(?:,\d+)*)',
            r'Rs\.?\s*(\d+(?:,\d+)*)',
            r'(\d+)\s*rs\b'
        ]
        
        for pattern in price_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price_str = match.group(1).replace(',', '')
                try:
                    price_num = int(price_str)
                    if 10 <= price_num <= 1000000:
                        info['price'] = str(price_num)
                        break
                except:
                    continue
        
        # Extract PIN (6 digits)
        pin_match = re.search(r'\b([1-9]\d{5})\b', text)
        if pin_match:
            info['pin'] = pin_match.group(1)
        
        # Extract brand
        text_lower = text.lower()
        for brand in KNOWN_BRANDS:
            if brand.lower() in text_lower:
                info['brand'] = brand
                break
        
        # Extract gender
        for gender, patterns in GENDER_KEYWORDS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    info['gender'] = gender
                    break
            if info['gender']:
                break
        
        # Extract quantity
        for pattern in QUANTITY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                info['quantity'] = match.group(1) if match.groups() else match.group(0)
                break
        
        # Extract title (clean text)
        title = re.sub(r'https?://[^\s]+', '', text)
        title = re.sub(r'@\s*\d+\s*rs', '', title, flags=re.IGNORECASE)
        title = re.sub(r'₹\s*\d+', '', title)
        title = re.sub(r'\b\d{6}\b', '', title)
        title = ' '.join(title.split())
        
        if title and len(title) > 3:
            info['title'] = title[:80].strip()
        
        return info

class ProductScraper:
    """Scrape product information"""
    
    @staticmethod
    def detect_platform(url: str) -> str:
        """Detect platform from URL"""
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
        else:
            return 'generic'
    
    @staticmethod
    async def scrape_product(url: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Scrape product info"""
        info = {
            'title': '',
            'price': '',
            'sizes': [],
            'brand': '',
            'gender': '',
            'quantity': '',
            'pin': ''
        }
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                platform = ProductScraper.detect_platform(url)
                
                # Title extraction
                title_selectors = {
                    'amazon': ['#productTitle', 'span#productTitle', '.a-size-large'],
                    'flipkart': ['.B_NuCI', '._35KyD6', 'h1.yhB1nd'],
                    'meesho': ['[data-testid="product-title"]', '.product-title', 'h1'],
                    'myntra': ['.pdp-name', '.pdp-title', 'h1.pdp-name'],
                    'ajio': ['.prod-name', '.product-name', 'h1']
                }
                
                selectors = title_selectors.get(platform, ['h1', '.product-title'])
                for selector in selectors:
                    element = soup.select_one(selector)
                    if element:
                        title = element.get_text(strip=True)
                        if title:
                            info['title'] = ProductScraper._clean_title(title)
                            break
                
                # Price extraction
                price_patterns = [
                    r'₹\s*(\d+(?:,\d+)*)',
                    r'"price"[:\s]*"?(\d+(?:,\d+)*)',
                    r'Rs\.?\s*(\d+(?:,\d+)*)'
                ]
                
                for pattern in price_patterns:
                    match = re.search(pattern, html, re.IGNORECASE)
                    if match:
                        price_str = match.group(1).replace(',', '')
                        try:
                            price_num = int(price_str)
                            if 10 <= price_num <= 1000000:
                                info['price'] = str(price_num)
                                break
                        except:
                            continue
                
                # Meesho specific
                if platform == 'meesho':
                    # Extract sizes
                    size_pattern = r'\b(XS|S|M|L|XL|XXL|XXXL|2XL|3XL)\b'
                    sizes = list(set(re.findall(size_pattern, html, re.IGNORECASE)))
                    if sizes:
                        info['sizes'] = sorted(sizes)
                    
                    # Extract PIN
                    pin_matches = re.findall(r'\b([1-9]\d{5})\b', html)
                    if pin_matches:
                        info['pin'] = pin_matches[0]
                
                # Extract brand from title or page
                if info['title']:
                    for brand in KNOWN_BRANDS:
                        if brand.lower() in info['title'].lower():
                            info['brand'] = brand
                            break
                
                # Extract gender
                if info['title']:
                    for gender, patterns in GENDER_KEYWORDS.items():
                        for pattern in patterns:
                            if re.search(pattern, info['title'], re.IGNORECASE):
                                info['gender'] = gender
                                break
                        if info['gender']:
                            break
                
                # Extract quantity
                if info['title']:
                    for pattern in QUANTITY_PATTERNS:
                        match = re.search(pattern, info['title'], re.IGNORECASE)
                        if match:
                            info['quantity'] = match.group(1) if match.groups() else match.group(0)
                            break
                
        except Exception as e:
            logger.error(f"Scraping failed: {e}")
        
        return info
    
    @staticmethod
    def _clean_title(title: str) -> str:
        """Clean and format title"""
        if not title:
            return ''
        
        # Remove platform names and noise
        noise_patterns = [
            r'\s*-\s*Amazon\.in.*$',
            r'\s*:\s*Amazon\.in.*$',
            r'\s*\|\s*Flipkart\.com.*$',
            r'\s*-\s*Buy.*$',
            r'Buy\s+.*?online.*?$',
            r'\s*\|\s*Myntra.*$',
            r'\s*-\s*Meesho.*$',
            r'\s*Online in India.*$',
            r'\s*Best Price.*$'
        ]
        
        for pattern in noise_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Remove extra whitespace
        title = ' '.join(title.split())
        
        # Limit length
        if len(title) > 60:
            title = title[:60].rsplit(' ', 1)[0]
        
        return title.strip()

class DealFormatter:
    """Format deals according to specification"""
    
    @staticmethod
    def format_deal(product_info: Dict[str, Any], clean_url: str, platform: str = '') -> str:
        """Format product info into specified structure"""
        
        if not platform:
            platform = ProductScraper.detect_platform(clean_url)
        
        # Prepare components
        components = []
        title = product_info.get('title', '').strip()
        
        # Remove duplicates and clean title
        words_used = set()
        
        # Add brand
        brand = product_info.get('brand', '').strip()
        if brand:
            components.append(brand)
            words_used.update(brand.lower().split())
        
        # Add gender
        gender = product_info.get('gender', '').strip()
        if gender and gender.lower() not in words_used:
            components.append(gender)
            words_used.add(gender.lower())
        
        # Add quantity
        quantity = product_info.get('quantity', '').strip()
        if quantity:
            components.append(quantity)
        
        # Clean title - remove already used words
        if title:
            title_words = []
            for word in title.split():
                if word.lower() not in words_used:
                    title_words.append(word)
            title = ' '.join(title_words).strip()
            
            if title:
                components.append(title)
        
        # Add price
        price = product_info.get('price', '').strip()
        if price:
            components.append(f"@{price} rs")
        
        # Build message
        lines = []
        
        # First line: components
        if components:
            lines.append(' '.join(components))
        else:
            lines.append('Product Deal')
        
        # Second line: URL
        lines.append(clean_url)
        
        # Empty line
        lines.append('')
        
        # Meesho specific
        if platform == 'meesho':
            # Size
            sizes = product_info.get('sizes', [])
            if sizes and len(sizes) >= 5:
                lines.append('Size - All')
            elif sizes:
                lines.append(f"Size - {', '.join(sizes)}")
            else:
                lines.append('Size - All')
            
            # PIN (no empty line between size and pin)
            pin = product_info.get('pin', '110001')
            lines.append(f"Pin - {pin}")
            
            # Empty line after meesho info
            lines.append('')
        
        # Channel tag
        lines.append('@reviewcheckk')
        
        return '\n'.join(lines)

class DealBot:
    """Main bot class"""
    
    def __init__(self):
        self.session = None
        self.processed_messages = set()
    
    async def initialize(self):
        """Initialize session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()
    
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process incoming messages"""
        try:
            message = update.message or update.channel_post
            if not message:
                return
            
            # Prevent duplicate processing
            message_id = f"{message.chat_id}_{message.message_id}"
            if message_id in self.processed_messages:
                return
            self.processed_messages.add(message_id)
            
            # Memory management
            if len(self.processed_messages) > 100:
                self.processed_messages = set(list(self.processed_messages)[-50:])
            
            await self.initialize()
            
            # Get text and photo
            text = message.text or message.caption or ''
            photo_id = message.photo[-1].file_id if message.photo else None
            
            # OCR if photo present
            ocr_text = ''
            if photo_id:
                try:
                    file = await context.bot.get_file(photo_id)
                    image_data = await file.download_as_bytearray()
                    ocr_text = await ImageOCR.extract_text_from_image(bytes(image_data))
                    logger.info(f"OCR extracted: {ocr_text[:100]}")
                except Exception as e:
                    logger.error(f"OCR failed: {e}")
            
            # Combine text sources
            combined_text = f"{text} {ocr_text}".strip()
            
            # Extract links
            links = SmartLinkProcessor.extract_all_links(combined_text)
            
            if not links:
                return
            
            logger.info(f"Found {len(links)} links")
            
            # Process each link
            results = []
            for url in links:
                try:
                    # Unshorten if needed
                    if SmartLinkProcessor.is_shortened_url(url):
                        url = await SmartLinkProcessor.unshorten_url(url, self.session)
                    
                    # Clean URL
                    clean_url = SmartLinkProcessor.clean_affiliate_url(url)
                    
                    # Extract manual info from text
                    manual_info = MessageParser.extract_info(combined_text)
                    
                    # Scrape product info
                    scraped_info = await ProductScraper.scrape_product(clean_url, self.session)
                    
                    # Merge info (manual overrides scraped for empty fields)
                    product_info = scraped_info.copy()
                    for key, value in manual_info.items():
                        if value and not product_info.get(key):
                            product_info[key] = value
                    
                    # Detect platform
                    platform = ProductScraper.detect_platform(clean_url)
                    
                    # Format message
                    formatted_message = DealFormatter.format_deal(product_info, clean_url, platform)
                    results.append((formatted_message, photo_id))
                    
                except Exception as e:
                    logger.error(f"Error processing link: {e}")
                    error_msg = f"Product Deal\n{url}\n\n@reviewcheckk"
                    results.append((error_msg, photo_id))
            
            # Send results
            for msg, img_id in results:
                try:
                    if img_id:
                        # Send with image
                        await context.bot.send_photo(
                            update.effective_chat.id,
                            photo=img_id,
                            caption=msg if len(msg) < 1024 else None
                        )
                        if len(msg) >= 1024:
                            await context.bot.send_message(
                                update.effective_chat.id,
                                text=msg
                            )
                    else:
                        # Send text only
                        await context.bot.send_message(
                            update.effective_chat.id,
                            text=msg
                        )
                except Exception as e:
                    logger.error(f"Failed to send: {e}")
                    
        except Exception as e:
            logger.error(f"Error in process_message: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle start command"""
    await update.message.reply_text(
        "🤖 *Deal Bot Active!*\n\n"
        "Send product links with or without images.\n"
        "Supports: Amazon, Flipkart, Meesho, Myntra, Ajio\n\n"
        "@reviewcheckk",
        parse_mode=ParseMode.MARKDOWN
    )

def main():
    """Main function"""
    print("🚀 Starting Deal Bot...")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize bot
    bot = DealBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(
        filters.TEXT | filters.CAPTION | filters.PHOTO, 
        bot.process_message
    ))
    
    # Run bot
    print(f"✅ Bot @{BOT_USERNAME} is running...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
