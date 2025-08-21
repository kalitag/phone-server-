import os
import re
import logging
import asyncio
from typing import List, Optional, Tuple, Set, Dict, Any
from urllib.parse import urlparse, parse_qs, urlunparse, quote
import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from bs4 import BeautifulSoup
import html

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s")

# Handle ALLOWED_CHAT_IDS with proper error handling
ALLOWED_CHAT_IDS = None
try:
    allowed_chats = os.environ.get("ALLOWED_CHAT_IDS")
    if allowed_chats:
        ALLOWED_CHAT_IDS = set(map(int, allowed_chats.split(',')))
except (ValueError, TypeError) as e:
    logger.warning(f"Error parsing ALLOWED_CHAT_IDS: {e}. All chats will be allowed.")

# Supported domains and shorteners
SUPPORTED_DOMAINS = {
    "amazon.in", "flipkart.com", "meesho.com", "myntra.com", "ajio.com",
    "snapdeal.com", "nykaa.com", "purplle.com", "firstcry.com", "tatacliq.com",
    "wishlink.com"
}

SHORTENERS = {
    "amzn.to", "fkrt.it", "fkrt.cc", "spoo.me", "bit.ly", "bitli.in", 
    "cutt.ly", "da.gd", "wishlink.com", "tinyurl.com", "t.c", "goo.gl",
    "shorte.st", "ow.ly", "tiny.cc", "is.gd", "cli.gs", "yep.it", "pic.gd",
    "v.gd", "tr.im", "qr.net", "1url.com", "t.co", "bit.do", "u.to", "j.mp",
    "b.link", "tiny.pl", "cutt.us", "x.co", "prettylinkpro.com", "clicky.me",
    "shorl.com", "short.io", "share.url", "link.tl", "shrtco.de", "riz.gy",
    "tinyurl.com", "short.cm", "klck.me", "q.gs", "viralurl.com", "zzb.bz",
    "link.zip", "shrunken.com", "spoo.me"
}

# Priority brands - must be lowercase for case-insensitive matching
PRIORITY_BRANDS = {
    "nike", "adidas", "puma", "apple", "samsung", "boat", "jbl", 
    "dettol", "vivel", "dove", "lakme", "maybelline", "philips", 
    "realme", "redmi", "oneplus", "levi's", "h&m", "zara", "forever21",
    "lee", "wrangler", "us polo", "allen solly", "van heusen", "peter england",
    "arrow", "woodland", "bata", "liberty", "red tape", "metro", "max",
    "pepe jeans", "flying machine", "killer", "being human", "fabindia",
    "biba", "w", "global desi", "anouk", "soch", "manyavar", "raymond",
    "blackberrys", "john players", "fastrack", "titan", "sonata", "casio",
    "fossil", "skmei", "noise", "boAt", "ptron", "realme", "oppo", "vivo",
    "xiaomi", "oneplus", "motorola", "lenovo", "asus", "hp", "dell", "canon",
    "nikon", "lg", "sony", "whirlpool", "lg", "samsung", "ifb", "voltas",
    "lloyd", "carrier", "blue star", "havells", "philips", "crompton", "bajaj",
    "usha", "prestige", "pigeon", "butterfly", "milton", "tupperware", "signoraware"
}

# Fluff words to remove from titles
FLUFF_WORDS = {
    'buy', 'shop', 'online', 'india', 'official', 'store', 'best', 'price', 
    'deal', 'off', 'sale', 'discount', 'offer', 'amazon', 'flipkart', 'meesho',
    'myntra', 'ajio', 'snapdeal', 'nykaa', 'purplle', 'firstcry', 'tatacliq',
    'wishlink', 'store', 'shopping', 'website', 'site', 'app', 'check', 'now',
    'hurry', 'limited', 'time', 'stock', 'available', 'new', 'latest', 'trending',
    'popular', 'bestseller', 'bestselling', 'hot', 'featured', 'special', 'only',
    'just', 'lowest', 'cheap', 'affordable', 'premium', 'quality', 'genuine',
    'authentic', 'original', 'branded', 'style', 'fashion', 'collection', 'design',
    'perfect', 'ideal', 'great', 'excellent', 'amazing', 'awesome', 'wonderful',
    'nice', 'good', 'perfect', 'unique', 'exclusive', 'free', 'shipping', 'delivery',
    'cod', 'cash', 'on', 'exchange', 'return', 'warranty', 'guarantee', 'assured',
    'trusted', 'rated', 'reviews', 'ratings', 'stars', 'verified', 'certified'
}

# Gender keywords
GENDER_KEYWORDS = {'men', 'women', 'boys', 'girls', 'kids', 'unisex', 'mens', 'womens'}

class URLResolver:
    @staticmethod
    async def unshorten_url(url: str) -> str:
        """Resolve shortened URLs with proper error handling"""
        try:
            # Skip if already a full URL
            parsed = urlparse(url)
            if parsed.netloc.replace('www.', '') not in SHORTENERS:
                return url
                
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=3,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                allow_redirects=True
            )
            return response.url
        except Exception as e:
            logger.warning(f"Failed to unshorten URL {url}: {e}")
            return url

    @staticmethod
    def is_supported_domain(url: str) -> bool:
        """Check if domain is supported"""
        try:
            domain = urlparse(url).netloc.lower()
            domain = domain.replace('www.', '')
            return any(supported_domain in domain for supported_domain in SUPPORTED_DOMAINS)
        except:
            return False

    @staticmethod
    def clean_url(url: str) -> str:
        """Remove tracking parameters from URL"""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            
            # Parameters to keep (domain specific)
            keep_params = []
            if 'amazon' in parsed.netloc:
                keep_params = ['id', 'qid', 'keywords']
            elif 'flipkart' in parsed.netloc:
                keep_params = ['pid', 'marketplace']
            elif 'meesho' in parsed.netloc:
                keep_params = ['id', 'search']
            elif 'myntra' in parsed.netloc:
                keep_params = ['id', 'p']
            
            # Filter parameters
            filtered_params = {}
            for key, values in query_params.items():
                if (key in keep_params or 
                    not any(tracking in key.lower() for tracking in 
                    ['utm_', 'ref', 'aff', 'pid', 'camp', 'gclid', 'fbclid', 
                     'tracking', 'source', 'medium', 'term', 'content', 'cid'])):
                    filtered_params[key] = values[0]
            
            # Rebuild URL
            clean_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                '&'.join([f"{k}={v}" for k, v in filtered_params.items()]),
                parsed.fragment
            ))
            
            return clean_url
        except Exception as e:
            logger.warning(f"Error cleaning URL {url}: {e}")
            return url

class TitleCleaner:
    @staticmethod
    def extract_title(html_content: str, url: str, message_text: str) -> str:
        """Extract and clean product title with multiple fallbacks"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try multiple sources in priority order
            title = None
            
            # 1. Try og:title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                title = og_title['content']
            
            # 2. Try twitter:title
            if not title:
                twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
                if twitter_title and twitter_title.get('content'):
                    title = twitter_title['content']
            
            # 3. Try <title> tag
            if not title:
                title_tag = soup.find('title')
                if title_tag:
                    title = title_tag.get_text()
            
            # 4. Try h1 with common product title classes
            if not title:
                for selector in ['h1', '.product-title', '.title', '.productName', 
                                '[data-qa="product-title"]', '.pdp-title', '.pdp-name']:
                    title_el = soup.select_one(selector)
                    if title_el:
                        title = title_el.get_text()
                        if title and len(title) > 10:
                            break
            
            # 5. Fallback to URL or message text
            if not title or len(title.strip()) < 5:
                title = TitleCleaner._extract_from_url(url) or message_text[:100]
            
            # Clean the title
            return TitleCleaner._clean_title(title, url)
            
        except Exception as e:
            logger.error(f"Error extracting title: {e}")
            return TitleCleaner._extract_from_url(url) or "Product"

    @staticmethod
    def _extract_from_url(url: str) -> str:
        """Extract product name from URL path"""
        try:
            parsed = urlparse(url)
            path_parts = [p for p in parsed.path.split('/') if p and not p.isdigit()]
            if path_parts:
                # Take the last meaningful part
                last_part = path_parts[-1]
                # Replace hyphens with spaces and title case
                return last_part.replace('-', ' ').replace('_', ' ').title()
            return ""
        except:
            return ""

    @staticmethod
    def _clean_title(raw_title: str, url: str = "") -> str:
        """Clean and format title according to rules"""
        try:
            # Decode HTML entities
            title = html.unescape(raw_title)
            
            # Remove extra spaces and special characters but keep basic punctuation
            title = re.sub(r'[^\w\s\-\.&+]', ' ', title)
            title = re.sub(r'\s+', ' ', title).strip()
            
            # Convert to lowercase for processing
            lower_title = title.lower()
            
            # Remove site names and fluff words
            words = []
            for word in title.split():
                lower_word = word.lower()
                # Skip fluff words and site names
                if (lower_word not in FLUFF_WORDS and 
                    not any(site in lower_word for site in SUPPORTED_DOMAINS) and
                    len(lower_word) > 1):  # Skip single letters except for sizes
                    words.append(word)
            
            # Reconstruct title
            title = ' '.join(words)
            
            # Extract and prioritize brand
            brand = TitleCleaner._extract_brand(title, url)
            if brand:
                # Remove brand from title to avoid duplication
                title = re.sub(re.escape(brand), '', title, flags=re.IGNORECASE).strip()
                # Place brand at the beginning
                title = f"{brand.title()} {title}"
            
            # Extract quantity and place it appropriately
            quantity = TitleCleaner._extract_quantity(title)
            if quantity:
                # Remove quantity from title to avoid duplication
                title = re.sub(re.escape(quantity), '', title, flags=re.IGNORECASE).strip()
                # Place quantity after brand for non-clothing, after gender for clothing
                if any(gender in title.lower() for gender in GENDER_KEYWORDS):
                    # Find position of gender term and insert quantity after it
                    words = title.split()
                    for i, word in enumerate(words):
                        if word.lower() in GENDER_KEYWORDS:
                            words.insert(i+1, quantity)
                            title = ' '.join(words)
                            break
                    else:
                        title = f"{title} {quantity}"
                else:
                    title = f"{title} {quantity}"
            
            # Limit word count (6-8 words)
            words = title.split()
            if len(words) > 8:
                title = ' '.join(words[:8])
            
            # Final cleanup
            title = re.sub(r'\s+', ' ', title).strip()
            
            # Validate title isn't nonsense
            if not TitleCleaner._is_valid_title(title):
                # Fallback to URL extraction
                url_title = TitleCleaner._extract_from_url(url)
                if url_title and TitleCleaner._is_valid_title(url_title):
                    title = url_title
                else:
                    title = "Quality Product"
            
            return title
            
        except Exception as e:
            logger.error(f"Error cleaning title '{raw_title}': {e}")
            return "Product"

    @staticmethod
    def _extract_brand(title: str, url: str = "") -> Optional[str]:
        """Extract brand from title or URL"""
        try:
            # Check against priority brands (case insensitive)
            lower_title = title.lower()
            for brand in PRIORITY_BRANDS:
                if brand.lower() in lower_title:
                    return brand
            
            # Try to extract from URL
            if url:
                parsed = urlparse(url)
                domain = parsed.netloc.lower()
                for brand in PRIORITY_BRANDS:
                    if brand.lower() in domain:
                        return brand
            
            # Try to extract from title (first significant word)
            words = title.split()
            if words and len(words[0]) > 2 and words[0].isalpha():
                return words[0]
                
            return None
        except:
            return None

    @staticmethod
    def _extract_quantity(text: str) -> Optional[str]:
        """Extract quantity information from text"""
        patterns = [
            r'\b(\d+(?:ml|g|kg|l|pcs|pc|pack|packs|set|sets))\b',
            r'\b(pack of \d+)\b',
            r'\b(\d+\s*[x×]\s*\d+\s*[a-zA-Z]*)\b',
            r'\b(combo of \d+)\b',
            r'\b(bundle of \d+)\b',
            r'\b(\d+\s*-\s*pack)\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None

    @staticmethod
    def _is_valid_title(title: str) -> bool:
        """Validate that title isn't nonsense"""
        if not title or len(title) < 3:
            return False
            
        # Check for repeated characters (like "aaaaa")
        if re.search(r'(.)\1{3,}', title.lower()):
            return False
            
        # Check for at least one vowel in first few words
        words = title.split()[:3]
        if words:
            has_vowel = any(any(vowel in word.lower() for vowel in 'aeiou') for word in words)
            if not has_vowel:
                return False
                
        # Check for reasonable word lengths
        for word in title.split():
            if len(word) > 20:  # Unusually long word
                return False
                
        return True

class PriceExtractor:
    @staticmethod
    def extract_price(html_content: str, message_text: str) -> Optional[str]:
        """Extract price from HTML or message text with priority to message"""
        try:
            # First try message text (highest priority)
            message_price = PriceExtractor._find_price_in_text(message_text)
            if message_price:
                return message_price
            
            # Then try HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try multiple selectors and patterns
            price_selectors = [
                'meta[property="og:price:amount"]',
                'meta[property="product:price:amount"]',
                'span.price', 
                'span.product-price',
                'span.offer-price',
                'span.selling-price',
                '.pdp-price',
                '[data-qa="product-price"]',
                '.productPrice',
                '.price'
            ]
            
            for selector in price_selectors:
                try:
                    price_elements = soup.select(selector)
                    for element in price_elements:
                        price_text = element.get('content') or element.get_text()
                        price = PriceExtractor._find_price_in_text(price_text)
                        if price:
                            return price
                except:
                    continue
            
            # Try JSON-LD data
            json_ld = soup.find('script', type='application/ld+json')
            if json_ld:
                try:
                    import json
                    data = json.loads(json_ld.string)
                    if isinstance(data, dict) and 'offers' in data:
                        offers = data['offers']
                        if isinstance(offers, dict) and 'price' in offers:
                            return str(offers['price']).split('.')[0]  # Remove decimals
                        elif isinstance(offers, list) and offers and 'price' in offers[0]:
                            return str(offers[0]['price']).split('.')[0]
                except:
                    pass
                    
            return None
            
        except Exception as e:
            logger.error(f"Error extracting price: {e}")
            return None

    @staticmethod
    def _find_price_in_text(text: str) -> Optional[str]:
        """Find price in text using regex"""
        try:
            # Handle price ranges (take the lower price)
            range_pattern = r'(?:₹|Rs?\.?\s*)(\d[\d,]*)\s*(?:-|to|–)\s*(?:₹|Rs?\.?\s*)(\d[\d,]*)'
            range_match = re.search(range_pattern, text, re.IGNORECASE)
            if range_match:
                return range_match.group(1).replace(',', '')
            
            # Find single price
            matches = re.findall(r'(?:₹|Rs?\.?\s*)(\d[\d,]*)', text, re.IGNORECASE)
            if matches:
                # Take the first match and remove commas
                return matches[0].replace(',', '')
                
            return None
        except:
            return None

class MeeshoHandler:
    @staticmethod
    def extract_size(html_content: str, message_text: str) -> str:
        """Extract size information for Meesho products"""
        try:
            # First check message text
            size_patterns = [
                r'\b(S|M|L|XL|XXL|XXXL|2XL|3XL|4XL)\b',
                r'\b(28|30|32|34|36|38|40|42|44)\b',
                r'\b(one\s*size|onesize|os)\b',
                r'\b(regular|free\s*size)\b'
            ]
            
            sizes_found = set()
            for pattern in size_patterns:
                sizes = re.findall(pattern, message_text, re.IGNORECASE)
                if sizes:
                    sizes_found.update(s.upper() for s in sizes)
            
            if sizes_found:
                return f"Size - {', '.join(sorted(sizes_found))}"
            
            # Then check HTML content
            soup = BeautifulSoup(html_content, 'html.parser')
            size_selectors = ['.size-variant', '.size-button', '.size', '.variant']
            
            for selector in size_selectors:
                try:
                    size_elements = soup.select(selector)
                    for element in size_elements:
                        size_text = element.get_text().strip()
                        if re.match(r'^\b(S|M|L|XL|XXL|XXXL|2XL|3XL|4XL|\d{2})\b$', size_text, re.IGNORECASE):
                            sizes_found.add(size_text.upper())
                except:
                    continue
            
            if sizes_found:
                return f"Size - {', '.join(sorted(sizes_found))}"
            
            return "Size - All"
            
        except Exception as e:
            logger.error(f"Error extracting size: {e}")
            return "Size - All"

    @staticmethod
    def extract_pin(message_text: str) -> str:
        """Extract PIN code from message text"""
        try:
            # Look for 6-digit PIN codes
            pin_match = re.search(r'\b(\d{6})\b', message_text)
            if pin_match:
                return f"Pin - {pin_match.group(1)}"
            
            return "Pin - 110001"
        except:
            return "Pin - 110001"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages"""
    # Check if chat is allowed
    if ALLOWED_CHAT_IDS and update.effective_chat.id not in ALLOWED_CHAT_IDS:
        logger.warning(f"Chat ID {update.effective_chat.id} not in allowed list")
        return
    
    try:
        # Extract text and entities from message
        message = update.effective_message
        text = message.text or message.caption or ""
        entities = message.entities or message.caption_entities or []
        
        # Find all URLs in the message
        urls = []
        for entity in entities:
            if entity.type == "url" or entity.type == "text_link":
                url = entity.url if hasattr(entity, 'url') else text[entity.offset:entity.offset + entity.length]
                urls.append(url)
        
        # Also look for URLs in plain text
        text_urls = re.findall(r'https?://\S+', text)
        urls.extend(text_urls)
        
        # Remove duplicates
        urls = list(set(urls))
        
        if not urls:
            # Check if this is a photo without caption but might have text in the image
            if message.photo:
                await message.reply_photo(
                    photo=message.photo[-1].file_id,
                    caption="No product link provided\n\n@reviewcheckk"
                )
            else:
                await message.reply_text("❌ No product links found")
            return
        
        # Process each URL
        processed_count = 0
        for url in urls:
            success = await process_single_url(url, message, context)
            if success:
                processed_count += 1
                
        if processed_count == 0:
            await message.reply_text("❌ Unsupported or invalid product link")
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.effective_message.reply_text("❌ Error processing your message")

async def process_single_url(url: str, message, context) -> bool:
    """Process a single product URL and return success status"""
    try:
        # Resolve and clean URL
        resolver = URLResolver()
        original_url = url
        
        # Unshorten if needed
        if any(shortener in url for shortener in SHORTENERS):
            url = await resolver.unshorten_url(url)
        
        # Check if supported domain
        if not resolver.is_supported_domain(url):
            logger.warning(f"Unsupported domain: {url}")
            return False
        
        # Clean URL (remove tracking parameters)
        clean_url = resolver.clean_url(url)
        
        # Fetch product page
        response = await asyncio.to_thread(
            requests.get, clean_url, 
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            timeout=3
        )
        response.raise_for_status()
        
        # Extract product information
        html_content = response.text
        message_text = message.text or message.caption or ""
        
        title = TitleCleaner.extract_title(html_content, clean_url, message_text)
        price = PriceExtractor.extract_price(html_content, message_text) or "rs"
        
        # Build response
        if "meesho.com" in clean_url:
            size = MeeshoHandler.extract_size(html_content, message_text)
            pin = MeeshoHandler.extract_pin(message_text)
            response_text = f"{title} @{price}\n{clean_url}\n{size}\n{pin}\n\n@reviewcheckk"
        else:
            response_text = f"{title} @{price}\n{clean_url}\n\n@reviewcheckk"
        
        # Send response
        if message.photo:
            # Reuse the original photo with new caption
            await message.reply_photo(
                photo=message.photo[-1].file_id,
                caption=response_text
            )
        else:
            await message.reply_text(response_text)
            
        return True
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error processing URL {url}: {e}")
        await message.reply_text("❌ Unable to fetch product information")
    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        await message.reply_text("❌ Unable to extract product info")
    
    return False

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add message handler
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.CAPTION | filters.FORWARDED, 
        handle_message
    ))
    
    # Start polling
    logger.info("Bot started")
    application.run_polling()

if __name__ == "__main__":
    main()
