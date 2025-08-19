import os
import re
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlunparse
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv("8465346144:AAG9x6C3OCOpUhVz3-qEK1wBlACOdb0Bz_s")

async def unshorten_url(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as resp:
                return str(resp.url)
    except:
        return url

def clean_url(url: str) -> str:
    parsed = urlparse(url)
    clean = parsed._replace(query="")  # remove affiliate tags
    return urlunparse(clean)

async def extract_info(url: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                html = await resp.text()
                soup = BeautifulSoup(html, "lxml")

                # title
                title = soup.find("title").get_text(strip=True) if soup.find("title") else "Unknown Product"
                title = re.sub(r"Buy|Online|at.*?Flipkart|Amazon\.in|Meesho.*", "", title, flags=re.I)
                title = " ".join(title.split()[:8])  # keep short

                # price
                price = None
                for tag in soup.find_all(["span", "div"]):
                    text = tag.get_text(strip=True)
                    if re.match(r"₹?\d{2,6}", text):
                        price = re.sub(r"[₹,]", "", text)
                        break

                return title, price
    except:
        return None, None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a product link and I’ll format it like ReviewCheckk ✅")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    urls = re.findall(r'(https?://\S+)', text)

    if not urls:
        await update.message.reply_text("❌ No link found")
        return

    for url in urls:
        full_url = await unshorten_url(url)
        clean = clean_url(full_url)
        title, price = await extract_info(clean)

        if not title:
            await update.message.reply_text("❌ Unable to extract product info")
            return

        # Format output
        response = f"{title}"
        if price:
            response += f" @{price} rs"
        response += f"\n{clean}\n\n"

        # Meesho special
        if "meesho.com" in clean:
            response += "Size - All\nPin - 110001\n\n"

        response += "@reviewcheckk"

        await update.message.reply_text(response)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
