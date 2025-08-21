import os
import re
import logging
import asyncio
from typing import List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse

import requests
from telegram import Update, InputMediaPhoto
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"

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
    "wishlink.com"  # Added based on your example
}

SHORTENERS = {
    "amzn.to", "fkrt.it", "fkrt.cc", "spoo.me", "bit.ly", "bitli.in", 
    "cutt.ly", "da.gd", "wishlink.com", "tinyurl.com"
}

# Priority brands
PRIORITY_BRANDS = {
    "nike", "adidas", "puma", "apple", "samsung", "boat", "jbl", 
    "dettol", "vivel", "dove", "lakme", "maybelline", "philips", 
    "realme", "redmi", "oneplus", "levi's", "h&m", "zara", "forever21"
}

class URLResolver:
    @staticmethod
    async def unshorten_url(url: str) -> str:
        """Resolve shortened URLs"""
        try:
            response = await asyncio.to_thread(
                requests.get,
                url,
                timeout=3,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                allow_redirects=True
            )
            return response.url
        except:
            return url

    @staticmethod
    def is_supported_domain(url: str) -> bool:
        """Check if domain is supported"""
        domain = urlparse(url).netloc.lower()
        return any(supported_domain in domain for supported_domain in SUPPORTED_DOMAINS)

    @staticmethod
    def clean_url(url: str) -> str:
        """Remove tracking parameters from URL"""
        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        
        # Parameters to keep (domain specific)
        keep_params = []
        if 'amazon' in parsed.netloc:
            keep_params = ['id', 'qid']
        elif 'flipkart' in parsed.netloc:
            keep_params = ['pid']
        
        # Filter parameters
        filtered_params = {}
        for key, values in query_params.items():
            if (key in keep_params or 
                not any(tracking in key for tracking in ['utm_', 'ref', 'aff', 'pid', 'camp', 'gclid', 'fbclid'])):
                filtered_params[key] = values[0]
        
        # Rebuild URL
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            '&'.join([f"{k}={v}" for k, v in filtered_params.items()]),
            parsed.fragment
        ))

class TitleCleaner:
    @staticmethod
    def extract_title(html: str, url: str, message_text: str) -> str:
        """Extract and clean product title"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Try og:title first
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content']
        else:
            # Try <title>
            title_tag = soup.find('title')
            title = title_tag.text if title_tag else ""
        
        # Fallbacks
        if not title or len(title) < 5:
            title = TitleCleaner._extract_from_url(url) or message_text[:100] or "Product"
        
        return TitleCleaner._clean_title(title)
    
    @staticmethod
    def _extract_from_url(url: str) -> str:
        """Extract product name from URL path"""
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split('/') if p and not p.isdigit()]
        return path_parts[-1].replace('-', ' ').title() if path_parts else ""

    @staticmethod
    def _clean_title(title: str) -> str:
        """Clean and format title"""
        # Remove fluff words
        fluff_words = {'buy', 'online', 'india', 'official', 'store', 'best', 'price', 'deal', 'off'}
        words = [word for word in title.split() if word.lower() not in fluff_words]
        
        # Limit word count and ensure proper casing
        cleaned = ' '.join(words[:8]).title()
        
        # Remove special characters and extra spaces
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

class PriceExtractor:
    @staticmethod
    def extract_price(html: str, message_text: str) -> Optional[str]:
        """Extract price from HTML or message text"""
        # First try message text
        message_price = PriceExtractor._find_price_in_text(message_text)
        if message_price:
            return message_price
        
        # Then try HTML content
        soup = BeautifulSoup(html, 'html.parser')
        price_selectors = [
            'meta[property="og:price:amount"]',
            'span.price',
            'span.product-price',
            'span.offer-price'
        ]
        
        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get('content') or price_element.text
                price = PriceExtractor._find_price_in_text(price_text)
                if price:
                    return price
        
        return None

    @staticmethod
    def _find_price_in_text(text: str) -> Optional[str]:
        """Find price in text using regex"""
        matches = re.findall(r'(?:₹|Rs?\.?\s*)(\d[\d,]*)', text, re.IGNORECASE)
        if matches:
            # Take the first match and remove commas
            return matches[0].replace(',', '')
        return None

class MeeshoHandler:
    @staticmethod
    def extract_size(html: str, message_text: str) -> str:
        """Extract size information for Meesho products"""
        size_patterns = [
            r'\b(S|M|L|XL|XXL|XXXL)\b',
            r'\b(28|30|32|34|36|38|40|42|44)\b'
        ]
        
        for pattern in size_patterns:
            sizes = re.findall(pattern, message_text, re.IGNORECASE)
            if sizes:
                return f"Size - {', '.join(set(sizes))}"
        
        return "Size - All"

    @staticmethod
    def extract_pin(message_text: str) -> str:
        """Extract PIN code from message text"""
        pin_match = re.search(r'\b(\d{6})\b', message_text)
        return f"Pin - {pin_match.group(1) if pin_match else '110001'}"

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
        
        if not urls:
            await message.reply_text("❌ No product links found")
            return
        
        # Process each URL
        for url in set(urls):  # Remove duplicates
            await process_single_url(url, message, context)
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await update.effective_message.reply_text("❌ Error processing your message")

async def process_single_url(url: str, message, context):
    """Process a single product URL"""
    try:
        # Resolve and clean URL
        resolver = URLResolver()
        if any(shortener in url for shortener in SHORTENERS):
            url = await resolver.unshorten_url(url)
        
        if not resolver.is_supported_domain(url):
            await message.reply_text("❌ Unsupported or invalid product link")
            return
        
        clean_url = resolver.clean_url(url)
        
        # Fetch product page
        response = await asyncio.to_thread(
            requests.get, clean_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            timeout=3
        )
        response.raise_for_status()
        
        # Extract product information
        html_content = response.text
        title = TitleCleaner.extract_title(html_content, clean_url, message.text or message.caption or "")
        price = PriceExtractor.extract_price(html_content, message.text or message.caption or "") or "rs"
        
        # Build response
        if "meesho.com" in clean_url:
            size = MeeshoHandler.extract_size(html_content, message.text or message.caption or "")
            pin = MeeshoHandler.extract_pin(message.text or message.caption or "")
            response_text = f"{title} @{price}\n{clean_url}\n{size}\n{pin}\n\n@reviewcheckk"
        else:
            response_text = f"{title} @{price}\n{clean_url}\n\n@reviewcheckk"
        
        # Send response
        if message.photo:
            # Reuse the original photo with new caption
            await message.reply_photo(
                photo=message.photo[-1].file_id,
                caption=response_text,
                parse_mode=ParseMode.HTML
            )
        else:
            await message.reply_text(response_text, parse_mode=ParseMode.HTML)
            
    except Exception as e:
        logger.error(f"Error processing URL {url}: {e}")
        await message.reply_text("❌ Unable to extract product info")

def main():
    """Start the bot"""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is required")
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add message handler
    application.add_handler(MessageHandler(
        filters.TEXT | filters.PHOTO | filters.FORWARDED, 
        handle_message
    ))
    
    # Start polling
    application.run_polling()

if __name__ == "__main__":
    main()
