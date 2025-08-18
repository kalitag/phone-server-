import re
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ==============================
# CONFIG
# ==============================
BOT_TOKEN = "8327175937:AAGoWZPlDM_UX7efZv6_7vJMHDsrZ3-EyIA"
BOT_USERNAME = "@Easy_uknowbot"

SHORTENERS = [
    "cutt.ly", "fkrt.cc", "amzn.to", "bitli.in", "spoo.me", "wishlink.com", "da.gd"
]

DEFAULT_PIN = "110001"


# ==============================
# LINK CLEANUP
# ==============================
def unshorten_url(url: str) -> str:
    """Expand short URLs to full product URLs"""
    for shortener in SHORTENERS:
        if shortener in url:
            try:
                resp = requests.get(url, allow_redirects=True, timeout=10)
                return resp.url
            except Exception:
                return url
    return url


def clean_affiliate(url: str) -> str:
    """Remove affiliate/ref query params"""
    return re.sub(r"(\?|&)tag=[^&]*", "", url)


# ==============================
# SCRAPER
# ==============================
def scrape_product(url: str):
    """Extract title + price from product page"""
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        title = soup.find("meta", {"property": "og:title"})
        if not title:
            title = soup.find("title")
        title = title["content"] if title and title.has_attr("content") else (title.text if title else "No Title")
        title = re.sub(r"\s+", " ", title).strip()

        # Price pattern
        price_text = soup.text
        price_match = re.findall(r"(₹|Rs\.?)\s?(\d[\d,]*)", price_text)
        price = None
        if price_match:
            price = min([int(p[1].replace(",", "")) for p in price_match])

        return {"title": title, "price": price}
    except Exception as e:
        return {"title": None, "price": None}


# ==============================
# FORMATTER
# ==============================
def format_message(url: str, data: dict) -> str:
    title = data.get("title") or "No Title Found"
    price = data.get("price")
    price_text = f"@{price} rs" if price else ""

    # Default message (Amazon/Flipkart/Myntra)
    msg = f"{title} {price_text}\n{url}\n\n@reviewcheckk"

    # Meesho-specific
    if "meesho" in url:
        msg = f"{title} {price_text}\n{url}\n\nPin - {DEFAULT_PIN}\n\n@reviewcheckk"

    return msg


# ==============================
# HANDLERS
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Bot is active! Send me any product link.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    urls = re.findall(r"https?://\S+", text)
    if not urls:
        await update.message.reply_text("❌ No link found.")
        return

    for url in urls:
        full_url = unshorten_url(url)
        full_url = clean_affiliate(full_url)

        data = scrape_product(full_url)
        msg = format_message(full_url, data)

        await update.message.reply_text(msg)


# ==============================
# MAIN
# ==============================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
