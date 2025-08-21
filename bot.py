#!/usr/bin/env python3
"""
ReviewCheckk Telegram Bot
Automated e-commerce deal posting bot with clean, uniform formatting
"""

import os
import re
import asyncio
import logging
from typing import List, Optional, Tuple, Dict
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from datetime import datetime
import html

import requests
from bs4 import BeautifulSoup
from telegram import Update, Message
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get('8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s', '')
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

# Constants
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
REQUEST_TIMEOUT = 3.0
MAX_TITLE_WORDS = 8

# Known brands (expandable)
KNOWN_BRANDS = {
    'nike', 'adidas', 'puma', 'reebok', 'apple', 'samsung', 'boat', 'jbl', 
    'dettol', 'vivel', 'dove', 'lakme', 'maybelline', 'philips', 'realme', 
    'redmi', 'oneplus', 'xiaomi', 'vivo', 'oppo', 'lenovo', 'dell', 'hp',
    'asus', 'acer', 'sony', 'lg', 'panasonic', 'haier', 'whirlpool',
    'bajaj', 'havells', 'crompton', 'usha', 'pigeon', 'prestige',
    'wildcraft', 'skybags', 'american tourister', 'vip', 'aristocrat'
}

# URL shorteners
URL_SHORTENERS = {
    'amzn.to', 'fkrt.cc', 'spoo.me', 'bitli.in', 'cutt.ly', 'da.gd',
    'wishlink.com', 'bit.ly', 'tinyurl.com', 'ow.ly', 'short.link',
    'smarturl.it', 'go2l.ink', 'x.co', 't.co', 'goo.gl', 'rebrand.ly'
}

# E-commerce domains
ECOMMERCE_DOMAINS = {
    'amazon.in', 'amazon.com', 'flipkart.com', 'meesho.com', 'myntra.com',
    'ajio.com', 'snapdeal.com', 'shopclues.com', 'paytmmall.com',
    'tatacliq.com', 'nykaa.com', 'purplle.com', 'firstcry.com',
    'bigbasket.com', 'grofers.com', 'blinkit.com', '1mg.com',
    'netmeds.com', 'pharmeasy.in', 'lenskart.com'
}

# Tracking parameters to remove
TRACKING_PARAMS = {
    'tag', 'ref', 'ref_', 'affiliate', 'aff_id', 'pid', 'utm_source',
    'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'gclid',
    'fbclid', 'camp', 'ascsubtag', 'linkCode', 'linkId', 'camp',
    'creative', 'creativeASIN', 'cvosrc', 'refRID', 'th', 'psc'
}


class URLResolver:
    """Handles URL detection, unshortening, and sanitization"""
    
    @staticmethod
    def extract_urls(text: str) -> List[str]:
        """Extract all URLs from text"""
        if not text:
            return []
        
        # Comprehensive URL regex
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, text)
        
        # Clean up URLs
        cleaned_urls = []
        for url in urls:
            # Remove trailing punctuation
            url = re.sub(r'[.,;:!?)]+$', '', url)
            cleaned_urls.append(url)
        
        return cleaned_urls
    
    @staticmethod
    async def unshorten_url(url: str) -> str:
        """Unshorten URL by following redirects"""
        try:
            # Check if URL needs unshortening
            domain = urlparse(url).netloc.lower()
            if domain not in URL_SHORTENERS:
                return url
            
            # Use asyncio.to_thread for non-blocking requests
            def make_request():
                response = requests.get(
                    url,
                    headers={'User-Agent': USER_AGENT},
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True
                )
                return response.url
            
            final_url = await asyncio.to_thread(make_request)
            logger.info(f"Unshortened: {url} -> {final_url}")
            return final_url
            
        except Exception as e:
            logger.error(f"Failed to unshorten {url}: {e}")
            return url
    
    @staticmethod
    def clean_url(url: str) -> str:
        """Remove tracking parameters from URL"""
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            
            # Keep only non-tracking parameters
            cleaned_params = {
                k: v for k, v in params.items() 
                if k.lower() not in TRACKING_PARAMS
            }
            
            # Rebuild URL
            new_query = urlencode(cleaned_params, doseq=True)
            cleaned_url = urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
            
            return cleaned_url
        except Exception as e:
            logger.error(f"Failed to clean URL {url}: {e}")
            return url
    
    @staticmethod
    def is_ecommerce_url(url: str) -> bool:
        """Check if URL is from supported e-commerce site"""
        domain = urlparse(url).netloc.lower()
        return any(ecom in domain for ecom in ECOMMERCE_DOMAINS)


class TitleCleaner:
    """Handles title extraction and cleaning"""
    
    @staticmethod
    async def extract_title_from_page(url: str) -> Optional[str]:
        """Extract title from webpage"""
        try:
            def fetch_page():
                response = requests.get(
                    url,
                    headers={'User-Agent': USER_AGENT},
                    timeout=REQUEST_TIMEOUT
                )
                return response.text
            
            html_content = await asyncio.to_thread(fetch_page)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try different title sources
            # 1. Open Graph title
            og_title = soup.find('meta', property='og:title')
            if og_title and og_title.get('content'):
                return og_title['content']
            
            # 2. Page title
            if soup.title and soup.title.string:
                return soup.title.string
            
            # 3. First H1
            h1 = soup.find('h1')
            if h1 and h1.get_text(strip=True):
                return h1.get_text(strip=True)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to extract title from {url}: {e}")
            return None
    
    @staticmethod
    def clean_title(title: str, is_clothing: bool = False) -> str:
        """Clean and format title according to rules"""
        if not title:
            return "Product"
        
        # Remove HTML entities
        title = html.unescape(title)
        
        # Remove site names and common fluff
        remove_patterns = [
            r'\s*-\s*Buy.*$', r'\s*\|.*$', r'Amazon\.in.*$', r'Flipkart.*$',
            r'Best.*Deal', r'Sale.*$', r'Offer.*$', r'Discount.*$',
            r'Trending.*$', r'Stylish.*$', r'Official Store.*$',
            r'Buy Online.*$', r'India.*$', r'\(.*?\)', r'\[.*?\]'
        ]
        
        for pattern in remove_patterns:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)
        
        # Remove special characters but keep alphanumeric and spaces
        title = re.sub(r'[^\w\s-]', ' ', title)
        title = re.sub(r'\s+', ' ', title)
        
        # Extract key components
        words = title.split()
        
        # Find brand
        brand = None
        for word in words[:3]:  # Check first 3 words for brand
            if word.lower() in KNOWN_BRANDS:
                brand = word
                break
        
        # Find quantity
        quantity = None
        quantity_pattern = r'\b(\d+(?:ml|g|kg|l|pcs|pc|pack|packs|set|sets))\b'
        quantity_match = re.search(quantity_pattern, title, re.IGNORECASE)
        if quantity_match:
            quantity = quantity_match.group(1)
        
        # Find gender for clothing
        gender = None
        if is_clothing:
            gender_words = ['men', 'women', 'boys', 'girls', 'kids', 'unisex']
            for word in words:
                if word.lower() in gender_words:
                    gender = word.capitalize()
                    break
        
        # Reconstruct title
        clean_words = []
        
        if brand:
            clean_words.append(brand.capitalize())
        
        if is_clothing and gender:
            clean_words.append(gender)
        
        if quantity:
            clean_words.append(quantity)
        
        # Add product type words (limit to key words)
        product_words = []
        skip_words = {'for', 'with', 'and', 'or', 'the', 'a', 'an', 'in', 'on', 'at'}
        
        for word in words:
            if len(product_words) >= 3:  # Limit product description
                break
            if word.lower() not in skip_words and word not in clean_words:
                if word.lower() not in KNOWN_BRANDS:
                    product_words.append(word.capitalize())
        
        clean_words.extend(product_words)
        
        # Limit to MAX_TITLE_WORDS
        clean_words = clean_words[:MAX_TITLE_WORDS]
        
        final_title = ' '.join(clean_words)
        
        # Validate title
        if not TitleCleaner.is_valid_title(final_title):
            return "Product"
        
        return final_title
    
    @staticmethod
    def is_valid_title(title: str) -> bool:
        """Check if title is valid and not nonsense"""
        if not title or len(title) < 3:
            return False
        
        # Check for vowels
        if not re.search(r'[aeiouAEIOU]', title):
            return False
        
        # Check for repeated characters
        if re.search(r'(.)\1{4,}', title):
            return False
        
        return True


class PriceExtractor:
    """Handles price extraction from various sources"""
    
    @staticmethod
    def extract_price_from_text(text: str) -> Optional[str]:
        """Extract price from text"""
        if not text:
            return None
        
        # Price patterns
        patterns = [
            r'(?:₹|Rs?\.?\s*)(\d+(?:,\d+)*)',
            r'(\d+(?:,\d+)*)\s*(?:₹|Rs?\.?)',
            r'@\s*(\d+(?:,\d+)*)',
            r'price[:\s]+(\d+(?:,\d+)*)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = match.group(1).replace(',', '')
                return price
        
        return None
    
    @staticmethod
    async def extract_price_from_page(url: str) -> Optional[str]:
        """Extract price from webpage"""
        try:
            def fetch_page():
                response = requests.get(
                    url,
                    headers={'User-Agent': USER_AGENT},
                    timeout=REQUEST_TIMEOUT
                )
                return response.text
            
            html_content = await asyncio.to_thread(fetch_page)
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Try different price sources
            # Look for price in meta tags
            price_meta = soup.find('meta', {'property': 'product:price:amount'})
            if price_meta and price_meta.get('content'):
                return price_meta['content'].replace(',', '')
            
            # Look for price in common classes
            price_classes = ['price', 'cost', 'amount', 'price-now']
            for cls in price_classes:
                price_elem = soup.find(class_=re.compile(cls, re.I))
                if price_elem:
                    price_text = price_elem.get_text()
                    price = PriceExtractor.extract_price_from_text(price_text)
                    if price:
                        return price
            
            # Search in full text
            full_text = soup.get_text()
            return PriceExtractor.extract_price_from_text(full_text)
            
        except Exception as e:
            logger.error(f"Failed to extract price from {url}: {e}")
            return None


class PinDetector:
    """Handles PIN code detection for Meesho"""
    
    @staticmethod
    def extract_pin(text: str) -> str:
        """Extract 6-digit PIN from text"""
        if not text:
            return "110001"
        
        # Look for 6-digit number
        pin_match = re.search(r'\b(\d{6})\b', text)
        if pin_match:
            return pin_match.group(1)
        
        return "110001"  # Default PIN


class ResponseBuilder:
    """Builds formatted responses according to ReviewCheckk style"""
    
    @staticmethod
    def build_response(
        title: str,
        price: Optional[str],
        url: str,
        is_meesho: bool = False,
        sizes: Optional[str] = None,
        pin: str = "110001"
    ) -> str:
        """Build formatted response message"""
        
        # Format price
        if price:
            # Check if it's a range
            if '-' in price or 'to' in price.lower():
                # Extract lower bound
                numbers = re.findall(r'\d+', price)
                if numbers:
                    price_str = f"from @{numbers[0]} rs"
                else:
                    price_str = "@ rs"
            else:
                price_str = f"@{price} rs"
        else:
            price_str = "@ rs"
        
        # Build message
        lines = [
            f"{title} {price_str}",
            url
        ]
        
        if is_meesho:
            # Add Size line
            if sizes:
                lines.append(f"Size - {sizes}")
            else:
                lines.append("Size - All")
            
            # Add Pin line
            lines.append(f"Pin - {pin}")
        
        # Add signature
        lines.append("")  # Blank line
        lines.append("@reviewcheckk")
        
        return "\n".join(lines)


class ReviewCheckkBot:
    """Main bot class"""
    
    def __init__(self):
        self.url_resolver = URLResolver()
        self.title_cleaner = TitleCleaner()
        self.price_extractor = PriceExtractor()
        self.pin_detector = PinDetector()
        self.response_builder = ResponseBuilder()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "👋 Welcome to ReviewCheckk Bot!\n\n"
            "Send me product links from Amazon, Flipkart, Meesho, and other e-commerce sites.\n"
            "I'll format them into clean deal posts.\n\n"
            "Just send or forward messages with product links!"
        )
    
    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await update.message.reply_text(
            "📖 How to use:\n\n"
            "1. Send me a product link (text or with photo)\n"
            "2. Include price if you want (e.g., @299)\n"
            "3. For Meesho, include PIN code if needed\n\n"
            "Supported sites: Amazon, Flipkart, Meesho, Myntra, Ajio, and more!\n\n"
            "I'll create a clean formatted post ending with @reviewcheckk"
        )
    
    async def process_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process incoming messages for product links"""
        try:
            message = update.message
            if not message:
                return
            
            # Extract text from message or caption
            text = message.text or message.caption or ""
            
            # If it's a forwarded message, get its text/caption
            if message.forward_from or message.forward_from_chat:
                if message.text:
                    text = message.text
                elif message.caption:
                    text = message.caption
            
            # Extract URLs
            urls = self.url_resolver.extract_urls(text)
            
            if not urls:
                # Check if user sent a photo without caption
                if message.photo and not text:
                    await message.reply_text("No title provided")
                return
            
            # Process each URL
            for url in urls:
                await self.process_url(message, url, text)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await message.reply_text("❌ An error occurred while processing your request")
    
    async def process_url(self, message: Message, url: str, original_text: str):
        """Process a single URL"""
        try:
            # Unshorten URL
            final_url = await self.url_resolver.unshorten_url(url)
            
            # Check if it's an e-commerce URL
            if not self.url_resolver.is_ecommerce_url(final_url):
                await message.reply_text("❌ Unsupported or invalid product link")
                return
            
            # Clean URL (remove tracking params)
            final_url = self.url_resolver.clean_url(final_url)
            
            # Check if it's Meesho
            is_meesho = 'meesho.com' in final_url.lower()
            
            # Extract title
            title = await self.title_cleaner.extract_title_from_page(final_url)
            if not title:
                # Fallback to URL segments
                path = urlparse(final_url).path
                segments = [s for s in path.split('/') if s and not s.isdigit()]
                if segments:
                    title = ' '.join(segments[-2:])
                else:
                    title = "Product"
            
            # Determine if clothing
            is_clothing = any(word in title.lower() for word in 
                            ['shirt', 'jeans', 'dress', 'trouser', 'pant', 'top', 
                             'kurta', 'saree', 'lehenga', 'jacket', 'sweater'])
            
            # Clean title
            title = self.title_cleaner.clean_title(title, is_clothing)
            
            # Extract price
            price = self.price_extractor.extract_price_from_text(original_text)
            if not price:
                price = await self.price_extractor.extract_price_from_page(final_url)
            
            # For Meesho, extract sizes and PIN
            sizes = None
            pin = "110001"
            if is_meesho:
                # Extract sizes from page if needed
                # Simple implementation - can be enhanced
                sizes = "All"
                
                # Extract PIN from message
                pin = self.pin_detector.extract_pin(original_text)
            
            # Build response
            response = self.response_builder.build_response(
                title=title,
                price=price,
                url=final_url,
                is_meesho=is_meesho,
                sizes=sizes,
                pin=pin
            )
            
            # Send response
            await message.reply_text(response, parse_mode=None)
            
        except Exception as e:
            logger.error(f"Error processing URL {url}: {e}")
            await message.reply_text("❌ Unable to extract product info")


def main():
    """Main function to run the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Initialize bot
    bot = ReviewCheckkBot()
    
    # Add handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help))
    application.add_handler(MessageHandler(filters.ALL, bot.process_message))
    
    # Start bot
    logger.info("Starting ReviewCheckk Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
