import io
import logging
import re
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image, ImageDraw, ImageFont
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


BOT_TOKEN = "" 
GROUP_CHAT_ID =      

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

latest_prices_numeric = {}
previous_prices_numeric = {}

def get_iran_time():
    iran_tz = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(iran_tz)

def fetch_crypto_prices(dollar_price):
    """استعلام تضمینی کریپتو از بایننس بدون بلاک شدن روی هاست خارجی"""
    crypto = {}
    try:
       
        res = requests.get("https://api.binance.com/api/v3/ticker/price?symbols=[%22BTCUSDT%22,%22ETHUSDT%22]", timeout=5)
        if res.status_code == 200:
            data = {item['symbol']: float(item['price']) for item in res.json()}
            btc_usd = data.get("BTCUSDT", 0)
            eth_usd = data.get("ETHUSDT", 0)

           
            crypto["usdt"] = dollar_price
            if dollar_price > 0:
                crypto["btc"] = int(btc_usd * dollar_price)
                crypto["eth"] = int(eth_usd * dollar_price)
    except Exception as e:
        logging.warning(f"خطا در دریافت بایننس: {e}")
        try:
            cg_res = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=usd", timeout=5)
            if cg_res.status_code == 200:
                cg_data = cg_res.json()
                btc_usd = cg_data.get("bitcoin", {}).get("usd", 0)
                eth_usd = cg_data.get("ethereum", {}).get("usd", 0)
                crypto["usdt"] = dollar_price
                if dollar_price > 0:
                    crypto["btc"] = int(btc_usd * dollar_price)
                    crypto["eth"] = int(eth_usd * dollar_price)
        except Exception:
            pass
            
    return crypto

def fetch_market_data():
    global latest_prices_numeric, previous_prices_numeric
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://bonbast.com/",
    }

    market = {"gold": {}, "currencies": {}, "crypto": {}}
    current_raw = {}

    try:
        page = session.get("https://bonbast.com", headers=headers, timeout=8)
        match = re.search(r'param:\s*["\']([^"\']+)["\']', page.text)
        if match:
            param = match.group(1)
            res = session.post(
                "https://bonbast.com/json",
                headers={**headers, "X-Requested-With": "XMLHttpRequest"},
                data={"param": param},
                timeout=8
            )
            if res.status_code == 200:
                raw = res.json()
                for key in ["usd1", "eur1", "gbp1", "kwd1", "chf1", "aed1", "qar1", "cad1", "aud1", "jpy1", "gol18", "emami1", "azadi1"]:
                    val = raw.get(key)
                    if val and val.isdigit():
                        current_raw[key] = int(val)
    except Exception as e:
        logging.warning(f"خطا در بن‌بست: {e}")
    dollar_val = current_raw.get("usd1", latest_prices_numeric.get("usd1", 0))
    cryptos = fetch_crypto_prices(dollar_val)
    current_raw.update(cryptos)
    if current_raw:
        if latest_prices_numeric:
            previous_prices_numeric = latest_prices_numeric.copy()
        latest_prices_numeric = current_raw.copy()
    def format_item(key):
        curr = latest_prices_numeric.get(key)
        if not curr:
            return "در حال دریافت..."
        prev = previous_prices_numeric.get(key)
        badge = "⚪️"
        if prev and prev > 0:
            diff = curr - prev
            pct = (diff / prev) * 100
            if diff > 0:
                badge = f"🟢 +{pct:.1f}%"
            elif diff < 0:
                badge = f"🔴 {pct:.1f}%"
        return f"{curr:,} تومان  {badge}"

    market["gold"] = {
        "🪙 سکه تمام امامی": format_item("emami1"),
        "🪙 سکه بهار آزادی": format_item("azadi1"),
        "✨ طلای ۱۸ عیار (هر گرم)": format_item("gol18"),
    }

    market["currencies"] = {
        "🇰🇼 دینار کویت": format_item("kwd1"),
        "🇬🇧 پوند انگلیس": format_item("gbp1"),
        "🇨🇭 فرانک سوئیس": format_item("chf1"),
        "🇪🇺 یورو": format_item("eur1"),
        "🇺🇸 دلار آمریکا": format_item("usd1"),
        "🇨🇦 دلار کانادا": format_item("cad1"),
        "🇦🇺 دلار استرالیا": format_item("aud1"),
        "🇦🇪 درهم امارات": format_item("aed1"),
        "🇶🇦 ریال قطر": format_item("qar1"),
        "🇯🇵 صد ین ژاپن": format_item("jpy1"),
    }

    market["crypto"] = {
        "💎 تتر (USDT)": format_item("usdt"),
        "🪙 بیت‌کوین (BTC)": format_item("btc"),
        "🔷 اتریوم (ETH)": format_item("eth"),
    }

    return market

def build_price_text():
    m = fetch_market_data()
    now_ir = get_iran_time().strftime("%H:%M - %Y/%m/%d")

    text = "📊 **تابلوی جامع بازار طلا، ارز و کریپتو**\n"
    text += f"⏰ *زمان:* `{now_ir}`\n"
    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "🥇 **طلا و مسکوکات:**\n"
    for k, v in m["gold"].items():
        text += f"{k}:  `{v}`\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "🌍 **۱۰ ارز شاخص جهان:**\n"
    for k, v in m["currencies"].items():
        text += f"{k}:  `{v}`\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "⚡️ **رمزارزها (معادل تومان):**\n"
    for k, v in m["crypto"].items():
        text += f"{k}:  `{v}`\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💡 *برای تبدیل ارز، مقدار را ارسال کنید (مثلاً: `100 usd`)*"
    return text

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔄 به‌روزرسانی لحظه‌ای", callback_data="refresh"),
            InlineKeyboardButton("📸 دریافت پوستر تصویری", callback_data="poster"),
        ],
        [
            InlineKeyboardButton("🧮 راهنمای ماشین‌حساب", callback_data="calc_help"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def generate_poster_image():
    img = Image.new("RGB", (800, 950), color=(18, 24, 38))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    draw.rectangle([(20, 20), (780, 80)], fill=(30, 41, 59))
    draw.text((280, 40), "IRAN LIVE MARKET RATES", fill=(255, 215, 0), font=font)

    y = 100
    sections = [
        ("--- GOLD & COINS ---", [
            ("Emami Coin", latest_prices_numeric.get("emami1", 0)),
            ("Azadi Coin", latest_prices_numeric.get("azadi1", 0)),
            ("18K Gold (Gram)", latest_prices_numeric.get("gol18", 0)),
        ]),
        ("--- TOP 10 CURRENCIES ---", [
            ("Kuwaiti Dinar (KWD)", latest_prices_numeric.get("kwd1", 0)),
            ("British Pound (GBP)", latest_prices_numeric.get("gbp1", 0)),
            ("Swiss Franc (CHF)", latest_prices_numeric.get("chf1", 0)),
            ("Euro (EUR)", latest_prices_numeric.get("eur1", 0)),
            ("US Dollar (USD)", latest_prices_numeric.get("usd1", 0)),
            ("Canadian Dollar (CAD)", latest_prices_numeric.get("cad1", 0)),
            ("Australian Dollar (AUD)", latest_prices_numeric.get("aud1", 0)),
            ("UAE Dirham (AED)", latest_prices_numeric.get("aed1", 0)),
            ("Qatari Rial (QAR)", latest_prices_numeric.get("qar1", 0)),
            ("100 Japanese Yen (JPY)", latest_prices_numeric.get("jpy1", 0)),
        ]),
        ("--- TOP CRYPTO (TOMAN) ---", [
            ("Tether (USDT)", latest_prices_numeric.get("usdt", 0)),
            ("Bitcoin (BTC)", latest_prices_numeric.get("btc", 0)),
            ("Ethereum (ETH)", latest_prices_numeric.get("eth", 0)),
        ])
    ]

    for title, items in sections:
        draw.text((40, y), title, fill=(56, 189, 248), font=font)
        y += 25
        for name, price in items:
            p_text = f"{price:,} Toman" if price else "N/A"
            draw.text((50, y), f"{name:<28} : {p_text}", fill=(241, 245, 249), font=font)
            y += 22
        y += 15

    draw.text((260, 910), "Automated Update by Telegram Bot", fill=(148, 163, 184), font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    return buf

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ در حال استعلام آخرین نرخ‌های بازار...")
    text = build_price_text()
    await msg.edit_text(text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "refresh":
        text = build_price_text()
        try:
            await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=get_main_keyboard())
        except Exception:
            pass

    elif query.data == "poster":
        await query.message.reply_chat_action("upload_photo")
        photo = generate_poster_image()
        now_ir = get_iran_time().strftime("%H:%M")
        await query.message.reply_photo(
            photo=photo,
            caption=f"📸 پوستر اختصاصی بازار آزاد ایران (ساعت {now_ir})"
        )

    elif query.data == "calc_help":
        help_text = (
            "🧮 **راهنمای ماشین‌حساب هوشمند تبدیل ارز:**\n\n"
            "کافیست در ربات بنویسید:\n"
            "• `100 usd` یا `100 دلار`\n"
            "• `50 eur` یا `50 یورو`\n"
            "• `2.5 طلا` یا `5 گرم طلا`\n"
            "• `0.05 btc` یا `200 usdt`"
        )
        await query.message.reply_text(help_text, parse_mode="Markdown")

async def calculator_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    pattern = r"^(\d+(?:\.\d+)?)\s*([a-zA-Z\u0600-\u06FF]+)$"
    match = re.match(pattern, text)

    if not match:
        return

    amount = float(match.group(1))
    unit = match.group(2)

    rates_map = {
        "usd": ("usd1", "دلار آمریکا"),
        "دلار": ("usd1", "دلار آمریکا"),
        "eur": ("eur1", "یورو"),
        "یورو": ("eur1", "یورو"),
        "gbp": ("gbp1", "پوند"),
        "پوند": ("gbp1", "پوند"),
        "kwd": ("kwd1", "دینار کویت"),
        "دینار": ("kwd1", "دینار کویت"),
        "aed": ("aed1", "درهم"),
        "درهم": ("aed1", "درهم"),
        "qar": ("qar1", "ریال قطر"),
        "طلا": ("gol18", "گرم طلای ۱۸ عیار"),
        "سکه": ("emami1", "سکه امامی"),
        "usdt": ("usdt", "تتر"),
        "تتر": ("usdt", "تتر"),
        "btc": ("btc", "بیت‌کوین"),
        "بیتکوین": ("btc", "بیت‌کوین"),
        "eth": ("eth", "اتریوم"),
    }

    if unit in rates_map:
        key, fa_name = rates_map[unit]
        unit_price = latest_prices_numeric.get(key)
        if unit_price:
            total = int(amount * unit_price)
            ans = (
                f"🧮 **محاسبه تبدیل ارز:**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"مقدار: `{amount:g}` {fa_name}\n"
                f"نرخ واحد: `{unit_price:,} تومان`\n"
                f"💰 **مجموع نهایی:** `{total:,} تومان`"
            )
            await update.message.reply_text(ans, parse_mode="Markdown")

async def send_group_update(context: ContextTypes.DEFAULT_TYPE):
    iran_hour = get_iran_time().hour

    if iran_hour >= 23 or iran_hour < 9:
        logging.info("ساعت استراحت بازار - ارسال به گروه انجام نشد.")
        return

    text = build_price_text()
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
        logging.info("پیام به گروه ارسال شد.")
    except Exception as e:
        logging.error(f"خطا در ارسال به گروه: {e}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(button_click))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, calculator_handler))

    app.job_queue.run_repeating(send_group_update, interval=7200, first=10)

    print("ربات با ظاهر مرتب و کریپتوی فعال بالا آمد...")
    app.run_polling()

if __name__ == "__main__":
    main()