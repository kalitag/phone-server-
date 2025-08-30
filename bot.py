import asyncio
import re
import logging
from urllib.parse import urlparse, parse_qs, urlunparse, unquote
from typing import Optional, List, Dict, Tuple
import requests
from bs4 import BeautifulSoup
from telegram import Update, Message
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatType
import time
import random
from fake_useragent import UserAgent

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class URLResolver:
    """Handle URL unshortening and cleaning"""
    
    SHORTENERS = [
        'amzn.to', 'fkrt.cc', 'spoo.me', 'wishlink.com', 'bitli.in', 
        'da.gd', 'cutt.ly', 'bit.ly', 'tinyurl.com', 'goo.gl', 't.co',
        'short.me', 'u.to', 'ow.ly', 'tiny.cc', 'is.gd', 'extp.in',
        'faym.co', 'myntr.in', 'dl.flipkart.com'
    ]
    
    TRACKING_PARAMS = [
        'tag', 'ref', 'refRID', 'pf_rd_r', 'pf_rd_p', 'pf_rd_m', 
        'pf_rd_t', 'pf_rd_s', 'pf_rd_i', 'utm_source', 'utm_medium', 
        'utm_campaign', 'utm_term', 'utm_content', 'gclid', 'fbclid',
        'mc_cid', 'mc_eid', '_gl', 'igshid', 'si'
    ]
    
    @staticmethod
    def detect_links(text: str) -> List[str]:
        """Extract all URLs from text"""
        url_pattern = r'https?://(?:[-\w.])+(?::[0-9]+)?(?:/(?:[\w/_.\-~%])*)?(?:\?(?:[\w&=%.\-])*)?(?:#(?:[\w.\-])*)?'
        return re.findall(url_pattern, text)
    
    @staticmethod
    def is_shortener(url: str) -> bool:
        """Check if URL is from a shortening service"""
        domain = urlparse(url).netloc.lower()
        return any(shortener in domain for shortener in URLResolver.SHORTENERS)
    
    @staticmethod
    async def unshorten_url(url: str, max_redirects: int = 5) -> str:
        """Resolve shortened URL to final destination with multiple redirect handling"""
        try:
            ua = UserAgent()
            headers = {
                'User-Agent': ua.random,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            def make_request():
                session = requests.Session()
                session.max_redirects = max_redirects
                response = session.get(url, headers=headers, allow_redirects=True, timeout=8, verify=False)
                return response.url
            
            final_url = await asyncio.to_thread(make_request)
            return URLResolver.clean_url(final_url)
            
        except Exception as e:
            logger.warning(f"Failed to unshorten URL {url}: {e}")
            return URLResolver.clean_url(url)
    
    @staticmethod
    def clean_url(url: str) -> str:
        """Remove tracking parameters from URL"""
        try:
            parsed = urlparse(url)
            query_params = parse_qs(parsed.query)
            
            # Remove tracking parameters
            cleaned_params = {
                k: v for k, v in query_params.items() 
                if k not in URLResolver.TRACKING_PARAMS
            }
            
            # Rebuild query string
            if cleaned_params:
                query_string = '&'.join(f"{k}={v[0]}" for k, v in cleaned_params.items())
                cleaned = parsed._replace(query=query_string)
            else:
                cleaned = parsed._replace(query='')
            
            return urlunparse(cleaned)
            
        except Exception:
            return url

class TitleCleaner:
    """Extract and clean product titles with advanced fallback strategies"""
    
    FLUFF_WORDS = [
        'best offer', 'trending', 'stylish', 'buy online', 'india', 'amazon.in',
        'flipkart', 'official store', 'exclusive', 'limited time', 'deal',
        'sale', 'discount', 'offer', 'free shipping', 'cod available',
        'cash on delivery', 'lowest price', 'great indian', 'festival',
        'for parties', 'cool', 'attractive', 'beautiful', 'amazing',
        'super', 'premium', 'high quality', 'branded', 'original',
        'https', 'http', 'www', 'com', 'in'
    ]
    
    CLOTHING_KEYWORDS = [
        'kurta', 'shirt', 'dress', 'top', 'bottom', 'jeans', 'trouser',
        'saree', 'lehenga', 'suit', 'kurti', 'palazzo', 'dupatta',
        'blouse', 'skirt', 'shorts', 'tshirt', 't-shirt', 'hoodie',
        'jacket', 'coat', 'sweater', 'cardigan', 'blazer', 'nighty',
        'tote', 'bag', 'sunscreen', 'lotion', 'cream', 'gel', 'shower'
    ]
    
    GENDER_KEYWORDS = {
        'women': ['women', 'womens', 'ladies', 'girls', 'female', 'girl'],
        'men': ['men', 'mens', 'boys', 'male', 'boy', 'gents'],
        'kids': ['kids', 'child', 'children', 'baby', 'infant'],
        'unisex': ['unisex', 'couple']
    }
    
    QUANTITY_PATTERNS = [
        r'pack of (\d+)', r'set of (\d+)', r'(\d+)\s*pcs?', r'(\d+)\s*pieces?',
        r'(\d+)\s*units?', r'(\d+)\s*kg', r'(\d+)\s*g\b', r'(\d+)\s*ml',
        r'(\d+)\s*l\b', r'combo of (\d+)', r'(\d+)\s*pairs?',
        r'multipack\s*(\d+)', r'(\d+)\s*in\s*1'
    ]
    
    @staticmethod
    async def extract_title_with_fallback(url: str, message_text: str) -> str:
        """Extract title using multiple fallback strategies"""
        
        # Strategy 1: Check for forwarded message patterns
        forwarded_title = TitleCleaner.extract_forwarded_title(message_text)
        if forwarded_title:
            return TitleCleaner.clean_title(forwarded_title)
        
        # Strategy 2: Web scraping with enhanced methods
        scraped_title = await TitleCleaner.extract_title_from_url_enhanced(url)
        if scraped_title and not TitleCleaner.is_nonsense_title(scraped_title):
            return TitleCleaner.clean_title(scraped_title)
        
        # Strategy 3: Extract from URL slug
        slug_title = TitleCleaner.extract_title_from_url_slug(url)
        if slug_title:
            return TitleCleaner.clean_title(slug_title)
        
        # Strategy 4: Clean message text
        message_title = TitleCleaner.extract_title_from_message(message_text)
        if message_title:
            return TitleCleaner.clean_title(message_title)
        
        return ""
    
    @staticmethod
    def extract_forwarded_title(text: str) -> Optional[str]:
        """Extract title from forwarded message patterns"""
        # Pattern 1: "Product Name @price rs"
        title_price_pattern = r'^([^@\n]+?)\s*@\d+\s*rs'
        match = re.search(title_price_pattern, text.strip(), re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Title on line before URL
        lines = text.strip().split('\n')
        for i, line in enumerate(lines):
            if 'http' in line.lower() and i > 0:
                potential_title = lines[i-1].strip()
                if potential_title and not re.search(r'@\d+\s*rs', potential_title):
                    # Filter out noise
                    if not any(noise in potential_title.lower() for noise in ['forwarded from', 'http', 'www']):
                        return potential_title
        
        return None
    
    @staticmethod
    def extract_title_from_url_slug(url: str) -> Optional[str]:
        """Extract product name from URL path/slug"""
        try:
            parsed = urlparse(url)
            path = unquote(parsed.path)
            
            # Common product URL patterns
            patterns = [
                r'/product/([^/]+)',
                r'/p/([^/]+)',
                r'/dp/([^/]+)',
                r'/([^/]+)/p/',
                r'/share/([^/]+)',
                r'/s/p/([^/]+)',
                r'/([^/]+)$'  # Last segment
            ]
            
            for pattern in patterns:
                match = re.search(pattern, path)
                if match:
                    slug = match.group(1)
                    # Convert slug to readable title
                    title = slug.replace('-', ' ').replace('_', ' ')
                    # Remove product IDs (long alphanumeric strings)
                    title = re.sub(r'\b[a-zA-Z0-9]{8,}\b', '', title)
                    title = ' '.join(title.split())
                    
                    if title and len(title) > 3:
                        return title
            
            return None
            
        except Exception:
            return None
    
    @staticmethod
    def extract_title_from_message(text: str) -> Optional[str]:
        """Extract title from message text as last resort"""
        # Remove URLs
        text_no_urls = re.sub(r'https?://[^\s]+', '', text)
        
        # Remove common noise
        for noise in ['forwarded from', '@', 'rs', 'pin', 'size']:
            text_no_urls = re.sub(noise, '', text_no_urls, flags=re.IGNORECASE)
        
        # Clean and validate
        words = text_no_urls.split()
        meaningful_words = [w for w in words if len(w) > 2 and w.lower() not in TitleCleaner.FLUFF_WORDS]
        
        if meaningful_words:
            return ' '.join(meaningful_words[:5])  # Max 5 words
        
        return None
    
    @staticmethod
    async def extract_title_from_url_enhanced(url: str) -> Optional[str]:
        """Enhanced title extraction with multiple user agents and methods"""
        try:
            # Use fake_useragent for better rotation
            ua = UserAgent()
            
            # Domain-specific handling
            domain = urlparse(url).netloc.lower()
            
            # Mobile user agent for mobile-optimized sites
            if any(site in domain for site in ['meesho', 'myntra', 'ajio']):
                user_agent = 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
            else:
                user_agent = ua.random
            
            headers = {
                'User-Agent': user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            # Add referer for some sites
            if 'wishlink' in domain or 'extp' in domain or 'faym' in domain:
                headers['Referer'] = 'https://www.google.com/'
            
            def scrape_title():
                session = requests.Session()
                session.headers.update(headers)
                
                # Add small random delay
                time.sleep(random.uniform(0.5, 1.5))
                
                # Disable SSL verification for problematic sites
                response = session.get(url, timeout=8, allow_redirects=True, verify=False)
                
                # Check status code
                if response.status_code != 200:
                    logger.warning(f"Got status {response.status_code} for {url}")
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Enhanced title extraction with domain-specific selectors
                title_candidates = []
                
                # Universal meta tags
                for meta_prop in ['og:title', 'twitter:title', 'title']:
                    meta_tag = soup.find('meta', attrs={'property': meta_prop}) or \
                               soup.find('meta', attrs={'name': meta_prop})
                    if meta_tag and meta_tag.get('content'):
                        title_candidates.append(meta_tag['content'].strip())
                
                # Page title
                title_tag = soup.find('title')
                if title_tag and title_tag.text:
                    title_candidates.append(title_tag.text.strip())
                
                # Domain-specific selectors
                if 'meesho.com' in domain:
                    selectors = [
                        'span.Text__StyledText-sc-oo0kvp-0',
                        'h1.Typography__H1-sc-10o6omr-0',
                        'div[class*="ProductTitle"]',
                        'span[class*="product-title"]',
                        'h1'
                    ]
                elif 'flipkart.com' in domain or 'fkrt' in domain:
                    selectors = [
                        'span.B_NuCI',
                        'h1.yhB1nd',
                        'div._2XKOHV',
                        'h1[class*="title"]',
                        'span[class*="title"]'
                    ]
                elif 'amazon' in domain or 'amzn.to' in domain:
                    selectors = [
                        'span#productTitle',
                        'h1#title',
                        'h1.a-size-large',
                        'span[id*="title"]'
                    ]
                elif 'myntra' in domain or 'myntr.in' in domain:
                    selectors = [
                        'h1.pdp-title',
                        'h1.pdp-name',
                        'div.pdp-price-info',
                        'h1[class*="product"]'
                    ]
                elif 'wishlink' in domain or 'extp' in domain or 'faym' in domain:
                    # Affiliate sites - try multiple approaches
                    selectors = [
                        'h1', 'h2', 'h3',
                        '.product-title', '.title', '#title',
                        '.product-name', '.item-title',
                        'div[class*="title"]', 'span[class*="title"]',
                        'meta[property="og:title"]'
                    ]
                else:
                    selectors = ['h1', 'h2', '.product-title', '.title']
                
                # Try each selector
                for selector in selectors:
                    try:
                        element = soup.select_one(selector)
                        if element:
                            text = element.get_text(strip=True) if hasattr(element, 'get_text') else str(element)
                            if text and len(text) > 5:
                                title_candidates.append(text)
                    except:
                        continue
                
                # Clean and return best candidate
                valid_titles = []
                for title in title_candidates:
                    if title and not TitleCleaner.is_nonsense_title(title):
                        # Remove common suffixes
                        title = re.sub(r'\s*[-|].*(?:Flipkart|Amazon|Meesho|Myntra).*$', '', title)
                        valid_titles.append(title.strip())
                
                if valid_titles:
                    # Return shortest meaningful title
                    return min(valid_titles, key=lambda x: len(x) if len(x) > 10 else 1000)
                
                return None
            
            return await asyncio.to_thread(scrape_title)
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed for {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract title from {url}: {e}")
            return None
    
    @staticmethod
    def clean_title(raw_title: str) -> str:
        """Clean and format product title according to new rules"""
        if not raw_title:
            return ""
        
        # Remove URLs and domain names
        title = re.sub(r'https?://[^\s]+', '', raw_title)
        title = re.sub(r'www\.[^\s]+', '', title)
        
        # Remove special characters but keep basic punctuation
        title = re.sub(r'[^\w\s\-&().,]', ' ', title)
        
        # Remove fluff words
        for fluff in TitleCleaner.FLUFF_WORDS:
            title = re.sub(r'\b' + re.escape(fluff) + r'\b', '', title, flags=re.IGNORECASE)
        
        # Normalize whitespace
        title = ' '.join(title.split())
        
        # Reject nonsense titles
        if TitleCleaner.is_nonsense_title(title):
            return ""
        
        # Extract components using new rules
        return TitleCleaner.format_with_new_rules(title)
    
    @staticmethod
    def format_with_new_rules(title: str) -> str:
        """Format title according to: [Gender] [Quantity] [Brand] [Product]"""
        words = title.lower().split()
        
        # Extract components
        gender = TitleCleaner.extract_gender(words)
        quantity = TitleCleaner.extract_quantity(' '.join(words))
        brand = TitleCleaner.extract_brand(words)
        product = TitleCleaner.extract_product(words)
        
        # Build final title
        parts = []
        if gender:
            parts.append(gender)
        if quantity:
            parts.append(quantity)
        if brand:
            parts.append(brand)
        if product:
            parts.extend(product.split()[:3])  # Max 3 words for product
        
        # Ensure max 8 words total
        final_parts = parts[:8]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_parts = []
        for part in final_parts:
            part_lower = part.lower()
            if part_lower not in seen:
                seen.add(part_lower)
                unique_parts.append(part.title())
        
        # If we have nothing, return a generic product name
        if not unique_parts:
            return "Product"
        
        return ' '.join(unique_parts)
    
    @staticmethod
    def extract_gender(words: List[str]) -> Optional[str]:
        """Extract gender from words"""
        for gender, keywords in TitleCleaner.GENDER_KEYWORDS.items():
            if any(keyword in words for keyword in keywords):
                return gender.title()
        return None
    
    @staticmethod
    def extract_quantity(text: str) -> Optional[str]:
        """Extract quantity information"""
        for pattern in TitleCleaner.QUANTITY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                quantity = match.group(1) if match.groups() else match.group(0)
                
                # Format based on pattern type
                if 'pack of' in pattern:
                    return f"Pack of {quantity}"
                elif 'set of' in pattern:
                    return f"Set of {quantity}"
                elif 'pcs' in pattern or 'pieces' in pattern:
                    return f"{quantity} Pcs"
                elif 'kg' in pattern:
                    return f"{quantity}kg"
                elif 'g' in pattern and 'kg' not in pattern:
                    return f"{quantity}g"
                elif 'ml' in pattern:
                    return f"{quantity}ml"
                elif 'l' in pattern and 'ml' not in pattern:
                    return f"{quantity}L"
                elif 'combo' in pattern:
                    return f"Combo of {quantity}"
                elif 'pairs' in pattern:
                    return f"{quantity} Pairs"
                elif 'multipack' in pattern:
                    return f"Multipack {quantity}"
                else:
                    return f"{quantity} Pcs"
        
        return None
    
    @staticmethod
    def extract_brand(words: List[str]) -> Optional[str]:
        """Extract brand name (usually first meaningful word)"""
        # Extended brand list
        known_brands = [
            'nike', 'adidas', 'puma', 'reebok', 'boat', 'jbl', 'sony', 
            'samsung', 'apple', 'mi', 'realme', 'oneplus', 'vivo', 'oppo',
            'libas', 'aurelia', 'w', 'biba', 'global desi', 'chemistry',
            'aqualogica', 'dove', 'lakme', 'maybelline', 'loreal', 'nivea'
        ]
        
        # Look for known brands first
        for word in words:
            if word in known_brands:
                return word.title()
        
        # If no known brand, take first meaningful word (not gender/quantity)
        for word in words:
            if (word not in [kw for kw_list in TitleCleaner.GENDER_KEYWORDS.values() for kw in kw_list] 
                and not re.match(r'\d+', word) 
                and len(word) > 2):
                return word.title()
        
        return None
    
    @staticmethod
    def extract_product(words: List[str]) -> str:
        """Extract product name (clothing items or main product)"""
        # Extended product keywords
        product_keywords = TitleCleaner.CLOTHING_KEYWORDS + [
            'watch', 'phone', 'earphones', 'headphones', 'speaker',
            'charger', 'cable', 'powerbank', 'case', 'cover'
        ]
        
        # Find product keywords
        for word in words:
            if word in product_keywords:
                return word.title()
        
        # If not found, extract meaningful product words
        product_words = []
        skip_words = ['for', 'with', 'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at']
        
        for word in words:
            if (len(word) > 2 
                and word not in skip_words
                and word not in [kw for kw_list in TitleCleaner.GENDER_KEYWORDS.values() for kw in kw_list]
                and not re.match(r'\d+', word)):
                product_words.append(word)
        
        # Take last 2-3 meaningful words as product name
        return ' '.join(product_words[-3:]) if product_words else 'Product'
    
    @staticmethod
    def is_nonsense_title(title: str) -> bool:
        """Check if title is nonsense/invalid"""
        if not title or len(title) < 3:
            return True
        
        # Check for lack of vowels
        vowel_count = len([c for c in title.lower() if c in 'aeiou'])
        if vowel_count < len(title) * 0.15:  # Less than 15% vowels
            return True
        
        # Check for repeated characters
        if re.search(r'(.)\1{4,}', title):  # Same char repeated 5+ times
            return True
        
        # Check if it's just a URL or domain
        if re.match(r'^(https?://|www\.)', title.lower()):
            return True
        
        # Check if it contains only noise words
        noise_only = all(word.lower() in TitleCleaner.FLUFF_WORDS for word in title.split())
        if noise_only:
            return True
        
        return False
    
    @staticmethod
    def is_clothing_item(title: str) -> bool:
        """Check if product is clothing item"""
        return any(keyword in title.lower() for keyword in TitleCleaner.CLOTHING_KEYWORDS)

class PriceExtractor:
    """Extract and format prices"""
    
    @staticmethod
    def extract_price(text: str) -> Optional[str]:
        """Extract price from text"""
        # Look for price patterns
        price_patterns = [
            r'@\s*(\d[\d,]*)\s*rs',  # @1299 rs (priority)
            r'(?:₹|Rs?\.?\s*)(\d[\d,]*)',  # ₹1299 or Rs. 1299
            r'(\d[\d,]*)\s*(?:₹|Rs?\.?)',  # 1299₹ or 1299 Rs
            r'price\s*:?\s*(?:₹|Rs?\.?\s*)(\d[\d,]*)',  # price: ₹1299
            r'cost\s*:?\s*(?:₹|Rs?\.?\s*)(\d[\d,]*)',   # cost: ₹1299
        ]
        
        for pattern in price_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                price = matches[0].replace(',', '')
                if price.isdigit() and int(price) > 0:
                    return price
        
        return None
    
    @staticmethod
    def format_price(price: str) -> str:
        """Format price in ReviewCheckk style"""
        if not price:
            return "@rs"
        return f"@{price} rs"

class PinDetector:
    """Detect PIN codes from messages"""
    
    @staticmethod
    def extract_pin(text: str) -> str:
        """Extract 6-digit PIN code from text"""
        # Look for PIN patterns
        pin_patterns = [
            r'pin\s*[-:]?\s*(\d{6})',  # Pin: 110001
            r'\b(\d{6})\b'  # Just 6 digits
        ]
        
        for pattern in pin_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for pin in matches:
                # Validate PIN (should not be all same digits or sequential)
                if len(set(pin)) > 1 and not re.match(r'123456|654321|111111|000000', pin):
                    return pin
        
        return "110001"  # Default PIN for Delhi

class ResponseBuilder:
    """Build formatted responses"""
    
    @staticmethod
    def build_response(title: str, url: str, price: str, is_meesho: bool = False, 
                      size: str = "All", pin: str = "110001") -> str:
        """Build final formatted response"""
        
        if not title:
            # Never return "Unable to extract" - always provide something
            title = "Product"
        
        # Format price
        formatted_price = PriceExtractor.format_price(price)
        
        # Build base response
        response = f"{title} {formatted_price}\n{url}"
        
        # Add Meesho-specific info
        if is_meesho:
            response += f"\nSize - {size}\nPin - {pin}"
        
        return response

class ReviewCheckkBot:
    """Main bot class with channel support"""
    
    def __init__(self, token: str):
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup message handlers for all chat types"""
        # Handle messages from all chat types including channels
        self.application.add_handler(
            MessageHandler(
                filters.TEXT | filters.PHOTO | filters.FORWARDED | filters.ChatType.CHANNEL,
                self.handle_message
            )
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main message handler for all chat types"""
        try:
            # Handle both regular messages and channel posts
            message = update.message or update.channel_post
            
            if not message:
                return
            
            # Check if bot should respond (for groups/channels)
            chat_type = message.chat.type
            
            # In channels, bot automatically processes all messages
            # In groups, bot processes messages with links
            # In private chats, bot processes all messages with links
            
            # Get text from message or caption
            text = self.extract_text(message)
            
            if not text:
                if message.photo:
                    # Only reply with "No title provided" in private chats
                    if chat_type == ChatType.PRIVATE:
                        await message.reply_text("No title provided")
                return
            
            # Extract and process URLs
            urls = URLResolver.detect_links(text)
            
            if not urls:
                return  # No URLs to process
            
            # Process each URL
            responses = []
            for url in urls:
                response = await self.process_url(url, text)
                if response and response != "❌ Unable to extract product info":
                    responses.append(response)
            
            # Send consolidated response
            if responses:
                final_response = '\n\n'.join(responses)
                await message.reply_text(final_response, parse_mode=None)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            # Don't send error messages in channels
            if message and message.chat.type == ChatType.PRIVATE:
                await message.reply_text("❌ Error processing request")
    
    def extract_text(self, message: Message) -> str:
        """Extract text from message or caption"""
        if message.text:
            return message.text
        elif message.caption:
            return message.caption
        elif hasattr(message, 'forward_from_message_id'):
            # Handle forwarded messages
            if message.forward_from:
                return getattr(message.forward_from, 'text', '')
        return ""
    
    async def process_url(self, url: str, message_text: str) -> Optional[str]:
        """Process a single URL and return formatted response"""
        try:
            # Unshorten URL if needed
            if URLResolver.is_shortener(url):
                final_url = await URLResolver.unshorten_url(url)
            else:
                final_url = URLResolver.clean_url(url)
            
            # Extract title using enhanced multi-strategy approach
            clean_title = await TitleCleaner.extract_title_with_fallback(final_url, message_text)
            
            # Always provide a title, never return "Unable to extract"
            if not clean_title:
                # Try one more time with just the URL slug
                slug_title = TitleCleaner.extract_title_from_url_slug(final_url)
                if slug_title:
                    clean_title = TitleCleaner.clean_title(slug_title)
                else:
                    # Generic fallback based on domain
                    domain = urlparse(final_url).netloc.lower()
                    if 'meesho' in domain:
                        clean_title = "Meesho Product"
                    elif 'flipkart' in domain or 'fkrt' in domain:
                        clean_title = "Flipkart Product"
                    elif 'amazon' in domain or 'amzn' in domain:
                        clean_title = "Amazon Product"
                    elif 'myntra' in domain or 'myntr' in domain:
                        clean_title = "Myntra Fashion"
                    else:
                        clean_title = "Product"
            
            # Extract price (prioritize message text)
            price = PriceExtractor.extract_price(message_text)
            
            # Check if it's Meesho
            is_meesho = 'meesho.com' in final_url.lower()
            
            # For Meesho, extract size and pin
            size = "All"
            pin = "110001"
            
            if is_meesho:
                # Extract size from message
                size_patterns = [
                    r'size\s*[-:]?\s*([^\n,]+)',
                    r'sizes?\s+available\s*[-:]?\s*([^\n,]+)',
                    r'\bsize\s+(\w+)\b'
                ]
                
                for pattern in size_patterns:
                    size_match = re.search(pattern, message_text, re.IGNORECASE)
                    if size_match:
                        size = size_match.group(1).strip()
                        break
                
                # Extract PIN
                pin = PinDetector.extract_pin(message_text)
            
            # Build and return response
            return ResponseBuilder.build_response(
                clean_title, final_url, price, is_meesho, size, pin
            )
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            # Return a basic response instead of error
            return f"Product @rs\n{url}"
    
    def run(self):
        """Start the bot"""
        logger.info("Starting Enhanced ReviewCheckk Style Bot...")
        logger.info("Bot will now respond to:")
        logger.info("- Direct messages")
        logger.info("- Group messages with links")
        logger.info("- Channel posts (when bot is admin)")
        logger.info("- Forwarded messages")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Main function"""
    # Bot token
    TOKEN = "8214627280:AAGveHdnt41wfXIaNunu6RBPsHDqMfIZo5E"
    
    # Create and run bot
    bot = ReviewCheckkBot(TOKEN)
    bot.run()

if __name__ == "__main__":
    main()
