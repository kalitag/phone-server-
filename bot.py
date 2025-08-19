import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode
import re

TOKEN = "8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s"

supported_domains = ['amazon.in', 'flipkart.com', 'meesho.com', 'myntra.com', 'ajio.com', 'snapdeal.com', 'wishlink.com']

affiliate_params = {
    'amazon.in': ['tag', 'ref', 'psc', 'keywords', 'sr', 'qid'],
    'flipkart.com': ['affid', 'affExtParam1', 'affExtParam2', 's_kwcid', 'cmpid'],
    'meesho.com': ['ref', 'utm_source', 'utm_medium', 'utm_campaign'],
    'myntra.com': ['utm_source', 'utm_medium', 'utm_campaign', 'rf'],
    'ajio.com': ['utm_source', 'utm_medium', 'utm_campaign'],
    'snapdeal.com': ['aff_id', 'utm_source', 'utm_medium', 'utm_campaign'],
    'wishlink.com': ['utm_source', 'utm_medium', 'utm_campaign', 'ref'],
}

junk_words = set(['buy', 'online', 'best', 'price', 'in', 'india', 'offer', 'deals', 'stylish', 'fashionable', 'new', 'latest', 'deal', 'at', 'on', 'for', 'with', '-', '|'])

def get_domain_type(netloc):
    netloc = netloc.lower().replace('www.', '')
    if 'amazon' in netloc:
        return 'amazon'
    if 'flipkart' in netloc:
        return 'flipkart'
    if 'meesho' in netloc:
        return 'meesho'
    if 'myntra' in netloc:
        return 'myntra'
    if 'ajio' in netloc:
        return 'ajio'
    if 'snapdeal' in netloc:
        return 'snapdeal'
    return None

def is_supported(netloc):
    netloc = netloc.lower().replace('www.', '')
    return netloc in supported_domains

async def unshorten_and_clean(url):
    async with aiohttp.ClientSession() as session:
        async with session.head(url, allow_redirects=True, timeout=5) as resp:
            final_url = str(resp.url)
    parsed = urlparse(final_url)
    domain = parsed.netloc.lower().replace('www.', '')
    params = parse_qs(parsed.query)
    to_remove = affiliate_params.get(domain, ['utm_source', 'utm_medium', 'utm_campaign', 'ref', 'tag', 'aff', 'cid'])
    for p in list(params.keys()):
        if p.lower() in [t.lower() for t in to_remove]:
            del params[p]
    new_query = urlencode(params, doseq=True)
    cleaned = parsed._replace(query=new_query).geturl()
    return cleaned

async def extract_title_price_brand(soup, domain_type):
    # Title
    title_tag = soup.find('meta', property='og:title') or soup.find('title')
    title = title_tag['content'].strip() if title_tag and 'content' in title_tag.attrs else (title_tag.text.strip() if title_tag else None)
    if not title:
        if domain_type == 'amazon':
            title = soup.find('span', id='productTitle').text.strip() if soup.find('span', id='productTitle') else None
        elif domain_type == 'flipkart':
            title = soup.find('span', class_='B_NuCI').text.strip() if soup.find('span', class_='B_NuCI') else None
        # Add more if needed
    if not title:
        return None, None, None

    # Brand
    brand = None
    brand_meta = soup.find('meta', property='product:brand')
    if brand_meta:
        brand = brand_meta['content'].strip()
    elif domain_type == 'amazon':
        brand_tag = soup.find('a', id='bylineInfo')
        brand = brand_tag.text.strip() if brand_tag else None
    elif domain_type == 'flipkart':
        brand_tag = soup.find('span', class_='G6XhRU')
        brand = brand_tag.text.strip() if brand_tag else None
    # For others, perhaps from title

    # Price
    price_meta = soup.find('meta', property='product:price:amount') or soup.find('meta', property='og:price:amount')
    price = price_meta['content'] if price_meta else None
    if not price:
        if domain_type == 'amazon':
            price_tag = soup.find('span', class_='a-offscreen')
            price = price_tag.text if price_tag else None
        elif domain_type == 'flipkart':
            price_tag = soup.find('div', class_='_30jeq3')
            price = price_tag.text if price_tag else None
        elif domain_type == 'meesho':
            price_tag = soup.find('span', class_='sc-dcJsrY')  # Approximate, may need adjustment
            price = price_tag.text if price_tag else None
        elif domain_type == 'myntra':
            price_tag = soup.find('span', class_='pdp-price')
            price = price_tag.text if price_tag else None
        elif domain_type == 'ajio':
            price_tag = soup.find('div', class_='prod-sp')
            price = price_tag.text if price_tag else None
        elif domain_type == 'snapdeal':
            price_tag = soup.find('span', class_='payBlkBig')
            price = price_tag.text if price_tag else None
    if price:
        price = re.sub(r'[^0-9]', '', price)
        try:
            price = int(price)
        except:
            price = None
    return title, price, brand

def clean_title(title, brand, is_meesho, original_title):
    title_lower = title.lower()
    words = re.split(r'\s+', title_lower)
    cleaned_words = [w.capitalize() for w in words if w not in junk_words]
    unique_words = []
    seen = set()
    for w in cleaned_words:
        if w not in seen:
            unique_words.append(w)
            seen.add(w)
    short = unique_words[:8]

    if brand:
        brand_cap = brand.capitalize()
        if short and short[0] != brand_cap:
            short = [brand_cap] + short[:7]

    is_clothing = any(word in title_lower for word in ['shirt', 'pant', 'kurta', 'saree', 'handbag', 'shoe', 't-shirt', 'jeans', 'dress', 'top', 'bottom', 'jacket'])

    gender = next((w for w in short if w.lower() in ['men', 'women', 'girls', 'boys']), None)

    if is_clothing and brand and gender:
        short = [brand.capitalize(), gender] + [w for w in short if w not in [brand.capitalize(), gender]]

    if is_meesho:
        quantity = None
        for i, w in enumerate(unique_words):
            if w.lower() == 'pack' and i+2 < len(unique_words) and unique_words[i+1].lower() == 'of':
                quantity = 'Pack of ' + unique_words[i+2]
                break
        if gender:
            short = [gender] + [w for w in short if w != gender]
        if quantity:
            short = [quantity] + [w for w in short if w not in quantity.split()]

    return ' '.join(short[:8])

async def process_link(url):
    try:
        cleaned_url = await unshorten_and_clean(url)
        parsed = urlparse(cleaned_url)
        netloc = parsed.netloc
        if not is_supported(netloc):
            return "❌ Unsupported or invalid product link"
        domain_type = get_domain_type(netloc)
        async with aiohttp.ClientSession() as session:
            async with session.get(cleaned_url, timeout=5) as resp:
                if resp.status != 200:
                    return "❌ Unable to extract product info"
                html = await resp.text()
        soup = BeautifulSoup(html, 'lxml')
        title, price, brand = await extract_title_price_brand(soup, domain_type)
        if not title or not price:
            return "❌ Unable to extract product info"
        is_meesho = domain_type == 'meesho'
        clean_t = clean_title(title, brand, is_meesho, title)
        price_str = f"@{price} rs"
        output = f"[{clean_t}] {price_str}\n[{cleaned_url}]"
        if is_meesho:
            output += "\nSize - All\nPin - 110001"
        output += "\n\n@reviewcheckk"
        return output
    except:
        return "❌ Unable to extract product info"

async def message_handler(message: Message):
    text = message.text or message.caption or ''
    urls = re.findall(r'https?://\S+', text)
    if not urls:
        return
    reply = await process_link(urls[0])
    await message.reply(reply, disable_web_page_preview=True)

async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.message()(message_handler)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
