import logging
import re
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8327175937:AAGoWZPlDM_UX7efZv6_7vJMHDsrZ3-EyIA"
PIN_DEFAULT = "110001"
CHANNEL_TAG = "@reviewcheckk"

SHORTENERS = ["cutt.ly", "fkrt.cc", "amzn.to", "bitli.in", "spoo.me", "da.gd", "wishlink.com"]

# =========================
# LOGGING
# =========================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================
# HELPERS
# =========================
def unshorten_url(url: str) -> str:
    try:
        s = requests.Session()
        s.max_redirects = 5
        resp = s.head(url, allow_redirects=True, timeout=10)
        return resp.url
    except:
        return url

def clean_title(title: str) -> str:
    if not title:
        return ""
    title = re.sub(r"Buy.*?Online|Latest Prices?|at Best Price.*", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    words = []
    for w in title.split():
        if w not in words:
            words.append(w)
    return " ".join(words)

def extract_price(text: str) -> str:
    prices = re.findall(r"(?:₹|Rs\.?|INR)?\s?([\d,]+)", text)
    if not prices:
        return ""
    nums = [int(p.replace(",", "")) for p in prices if p]
    if not nums:
        return ""
    return str(min(nums))

def scrape_product(url: str) -> dict:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, "lxml")

        title = ""
        if soup.find("title"):
            title = soup.find("title").text
        og = soup.find("meta", {"property": "og:title"})
        if og and og.get("content"):
            title = og["content"]

        clean = clean_title(title)

        price = extract_price(soup.get_text())

        return {"title": clean, "price": price}
    except Exception as e:
        logger.error(f"Scrape error: {e}")
        return {"title": "", "price": ""}

def format_message(url: str, data: dict) -> str:
    title = data.get("title", "")
    price = data.get("price", "")

    if "meesho.com" in url:
        # Meesho style
        msg = f"{title} @{price} rs\n{url}\n\nPin - {PIN_DEFAULT}\n\n{CHANNEL_TAG}"
    elif any(k in url for k in ["amazon.", "amzn."]):
        msg = f"{title} from @{price} rs\n{url}\n\n{CHANNEL_TAG}"
    elif "flipkart" in url:
        msg = f"{title} from @{price} rs\n{url}\n\n{CHANNEL_TAG}"
    elif "myntra" in url:
        msg = f"{title} from @{price} rs\n{url}\n\n{CHANNEL_TAG}"
    else:
        msg = f"{title} @{price} rs\n{url}\n\n{CHANNEL_TAG}"

    return msg.strip()

# =========================
# HANDLERS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Bot is live and ready!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if not text:
        return

    urls = re.findall(r'(https?://\S+)', text)
    if not urls:
        return

    for url in urls:
        # unshorten if needed
        if any(s in url for s in SHORTENERS):
            url = unshorten_url(url)

        # scrape product
        data = scrape_product(url)
        if not data["title"]:
            await update.message.reply_text("❌ Unable to extract product info.")
            continue

        msg = format_message(url, data)
        await update.message.reply_text(msg)

# =========================
# MAIN
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("🤖 Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
