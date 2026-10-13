import asyncio
import time
import sqlite3
import threading
import telebot
from telebot import types
from pasarguard import PasarguardAPI, Tools, UserCreate, UserStatus


BOT_TOKEN = ""
ADMIN_ID =                       
PANEL_URL = "https://lx.devfreedomnet.com"  
PANEL_USER = ""                    
PANEL_PASS = ""
CARD_NUMBER = "6219861866170052"       
CARD_NAME = "محمدمهدی سرفراز"


#  پلن‌های فروش
PLANS = {
    "plan_1": {"name": "پلن 1 ماهه - 20 گیگابایت", "days": 30, "gb": 20, "price": "80,000"},
    "plan_2": {"name": "پلن 1 ماهه - 30 گیگابایت", "days": 30, "gb": 30, "price": "120,000"},
    "plan_3": {"name": "پلن 1 ماهه - 40 گیگابایت", "days": 30, "gb": 40, "price": "160,000"},
    "plan_4": {"name": "پلن 3 ماهه - 40 گیگابایت", "days": 90, "gb": 40, "price": "150,000"},
    "plan_5": {"name": "پلن 3 ماهه - 60 گیگابایت", "days": 90, "gb": 60, "price": "220,000"},
    "plan_6": {"name": "پلن 6 ماهه - 120 گیگابایت", "days": 180, "gb": 120, "price": "440,000"},
    "plan_7": {"name": "پلن 6 ماهه - 240 گیگابایت", "days": 180, "gb": 240, "price": "800,000"},
}

def safe_format(val):
    try:
        clean_num = int(str(val).replace(",", "").replace("،", "").strip())
        return f"{clean_num:,}"
    except Exception:
        return str(val)

def safe_int(val):
    try:
        return int(str(val).replace(",", "").replace("،", "").strip())
    except Exception:
        return 0

bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}
pending_receipts = {}
db_lock = threading.Lock()

def get_db():
    conn = sqlite3.connect("bot_database.db", timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    username TEXT,
                    balance INTEGER DEFAULT 0,
                    created_at INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    config_name TEXT,
                    plan_name TEXT,
                    sub_url TEXT,
                    created_at INTEGER
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS test_users (
                    user_id INTEGER PRIMARY KEY,
                    created_at INTEGER
                )
            """)
            conn.commit()

init_db()

def register_user_if_not_exists(user):
    with db_lock:
        with get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, first_name, username, balance, created_at) VALUES (?, ?, ?, 0, ?)",
                (user.id, user.first_name, user.username or "", int(time.time()))
            )
            conn.commit()

def get_user_balance(user_id):
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return safe_int(row["balance"]) if row else 0

def update_user_balance(user_id, amount):
    with db_lock:
        with get_db() as conn:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (safe_int(amount), user_id))
            conn.commit()

def save_service(user_id, config_name, plan_name, sub_url):
    with db_lock:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO services (user_id, config_name, plan_name, sub_url, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, config_name, plan_name, sub_url, int(time.time()))
            )
            conn.commit()

async def _async_create_user(username, data_limit_bytes, days, note):
    async with PasarguardAPI(
        base_url=PANEL_URL,
        verify=True,
        timeout=25.0,
    ) as api:
        token = await api.get_token(
            username=PANEL_USER,
            password=PANEL_PASS,
        )
        user = await api.create_user_in_all_groups(
            UserCreate(
                username=username,
                data_limit=data_limit_bytes,
                expire=Tools.days(days),
                status=UserStatus.ACTIVE,
                note=note,
            ),
            token=token.access_token,
        )
        return user.subscription_url

def create_pasarguard_user(username, data_limit_bytes, days, note="خریداری شده از ربات"):
    try:
        sub_url = asyncio.run(_async_create_user(username, data_limit_bytes, days, note))
        return sub_url, None
    except Exception as e:
        return None, str(e)

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_buy = types.KeyboardButton("🤝 خرید اشتراک")
    btn_my_services = types.KeyboardButton("📁 سرویس‌های من")
    btn_renew = types.KeyboardButton("♻️ تمدید سرویس")
    btn_test = types.KeyboardButton("🛡 اکانت تست")
    btn_wallet = types.KeyboardButton("🏛 کیف پول + شارژ")
    btn_support = types.KeyboardButton("📞 پشتیبانی")
    
    markup.add(btn_buy)
    markup.add(btn_my_services, btn_renew)
    markup.add(btn_test, btn_wallet)
    markup.add(btn_support)
    return markup

@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_states.pop(message.from_user.id, None)
    register_user_if_not_exists(message.from_user)
    welcome_text = (
        f"سلام <b>{message.from_user.first_name}</b> عزیز، خوش آمدید! 🌸\n\n"
        f"لطفاً از منوی زیر گزینه مورد نظرتان را انتخاب نمایید:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

#  خرید اشتراک
@bot.message_handler(func=lambda msg: msg.text and "خرید اشتراک" in msg.text)
def show_shop_plans(message):
    user_states.pop(message.from_user.id, None)
    register_user_if_not_exists(message.from_user)
    
    markup = types.InlineKeyboardMarkup()
    for plan_id, plan in PLANS.items():
        btn_text = f"{plan['name']} - {safe_format(plan['price'])} تومان"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"select_plan_{plan_id}"))
    bot.send_message(message.chat.id, "لطفاً یکی از پلن‌های زیر را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("select_plan_"))
def ask_config_name(call):
    plan_id = call.data.replace("select_plan_", "")
    user_states[call.from_user.id] = {"action": "entering_config_name", "plan_id": plan_id}
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "لطفاً یک <b>نام دلخواه انگلیسی</b> برای کانفیگ خود وارد کنید (فقط حروف و اعداد انگلیسی):",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("action") == "entering_config_name")
def confirm_purchase_with_balance(message):
    cfg_name = message.text.strip().replace(" ", "_")
    user_id = message.from_user.id
    plan_id = user_states[user_id]["plan_id"]
    plan = PLANS[plan_id]
    
    price = safe_int(plan["price"])
    current_balance = get_user_balance(user_id)
    
    if current_balance < price:
        shortage = price - current_balance
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💰 شارژ کیف پول", callback_data="wallet_deposit"))
        
        err_text = (
            f"❌ <b>موجودی کیف پول شما کافی نیست.</b>\n\n"
            f"🔹 قیمت پلن: <b>{safe_format(price)} تومان</b>\n"
            f"⭐ موجودی فعلی: <b>{safe_format(current_balance)} تومان</b>\n"
            f"⚠️ کسری موجودی: <b>{safe_format(shortage)} تومان</b>\n\n"
            f"برای خرید، ابتدا موجودی خود را افزایش دهید."
        )
        bot.send_message(message.chat.id, err_text, reply_markup=markup, parse_mode="HTML")
        user_states.pop(user_id, None)
        return

    user_states[user_id] = {
        "action": "confirm_instant_buy",
        "plan_id": plan_id,
        "config_name": cfg_name
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ بله، خرید و ساخت آنی", callback_data="confirm_buy_now"))
    markup.add(types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_action"))

    confirm_msg = (
        f"<b>پیش‌فاکتور خرید اشتراک:</b>\n\n"
        f"📦 پلن انتخابی: <b>{plan['name']}</b>\n"
        f"📝 نام کانفیگ: <code>{cfg_name}</code>\n"
        f"💰 مبلغ کسر از کیف پول: <b>{safe_format(price)} تومان</b>\n"
        f"⭐ موجودی شما: <b>{safe_format(current_balance)} تومان</b>\n\n"
        f"آیا مایلید اشتراک بلافاصله برای شما ساخته شود؟"
    )
    bot.send_message(message.chat.id, confirm_msg, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "confirm_buy_now")
def process_instant_buy(call):
    user_id = call.from_user.id
    state = user_states.get(user_id, {})
    
    if state.get("action") != "confirm_instant_buy":
        bot.answer_callback_query(call.id, "این سفارش منقضی شده است.")
        return

    plan = PLANS[state["plan_id"]]
    cfg_name = state["config_name"]
    price = safe_int(plan["price"])
    
    current_bal = get_user_balance(user_id)
    if current_bal < price:
        bot.answer_callback_query(call.id, "موجودی کافی نیست.")
        return

    bot.edit_message_text("⏳ در حال ساخت اشتراک در پنل، لطفاً چند لحظه صبر کنید...", chat_id=call.message.chat.id, message_id=call.message.message_id)

    update_user_balance(user_id, -price)

    gb_bytes = plan["gb"] * 1024 * 1024 * 1024
    sub_url, error = create_pasarguard_user(cfg_name, gb_bytes, plan["days"], note=f"خرید کاربر {user_id}")

    if sub_url:
        save_service(user_id, cfg_name, plan["name"], sub_url)
        user_states.pop(user_id, None)

        success_text = (
            f"🎉 <b>اشتراک شما با موفقیت ساخته شد!</b>\n\n"
            f"👤 <b>نام اشتراک:</b> <code>{cfg_name}</code>\n"
            f"📦 <b>مشخصات:</b> {plan['gb']} گیگابایت | {plan['days']} روز\n\n"
            f"🔗 <b>لینک اتصال اختصاصی شما:</b>\n<code>{sub_url}</code>\n\n"
            f"💡 <i>لینک بالا را در نرم‌افزار خود وارد نمایید. همچنین در بخش «سرویس‌های من» همیشه در دسترس است.</i>"
        )
        bot.send_message(call.message.chat.id, success_text, parse_mode="HTML")
    else:
        update_user_balance(user_id, price)
        bot.send_message(call.message.chat.id, f"❌ خطایی در پنل رخ داد و هزینه به کیف پول شما برگشت داده شد:\n<code>{error}</code>", parse_mode="HTML")

#  کیف پول و شارژ 
@bot.message_handler(func=lambda msg: msg.text and "کیف پول" in msg.text)
def show_wallet(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    register_user_if_not_exists(message.from_user)
    
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT balance, created_at FROM users WHERE user_id = ?", (user_id,))
            u = c.fetchone()
            c.execute("SELECT COUNT(*) as count FROM services WHERE user_id = ?", (user_id,))
            service_count = c.fetchone()["count"]

    balance = safe_int(u["balance"]) if u else 0
    created_at = u["created_at"] if u else int(time.time())
    reg_date = time.strftime("%Y/%m/%d", time.localtime(created_at))
    
    wallet_info = (
        f"🍀 <b>اطلاعات حساب کاربری شما:</b>\n\n"
        f"🪪 <b>آیدی عددی:</b> <code>{user_id}</code>\n"
        f"👤 <b>نام:</b> {message.from_user.first_name}\n"
        f"⌛️ <b>زمان ثبت‌نام:</b> {reg_date}\n"
        f"⭐ <b>موجودی کیف پول:</b> <b>{safe_format(balance)} تومان</b>\n"
        f"🛒 <b>تعداد سرویس‌های فعال:</b> {service_count} عدد\n"
        f"🔖 <b>گروه کاربری:</b> عادی\n"
    )
    
    markup = types.InlineKeyboardMarkup()
    btn_deposit = types.InlineKeyboardButton("💰 افزایش موجودی", callback_data="wallet_deposit")
    markup.add(btn_deposit)
    
    bot.send_message(message.chat.id, wallet_info, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "wallet_deposit")
def ask_deposit_amount(call):
    user_states[call.from_user.id] = {"action": "entering_deposit_amount"}
    bot.answer_callback_query(call.id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("↩️ انصراف", callback_data="cancel_action"))
    
    msg_text = (
        f"💸 <b>مبلغ را به تومان وارد کنید:</b>\n"
        f"✅ حداقل مبلغ ۱,۰۰۰ و حداکثر ۲,۰۰۰,۰۰۰ تومان می‌باشد."
    )
    bot.send_message(call.message.chat.id, msg_text, reply_markup=markup, parse_mode="HTML")

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("action") == "entering_deposit_amount")
def get_deposit_amount(message):
    try:
        amount = safe_int(message.text)
        if amount < 1000 or amount > 2000000:
            bot.send_message(message.chat.id, "⚠️ مبلغ باید بین ۱,۰۰۰ تا ۲,۰۰۰,۰۰۰ تومان باشد. دوباره وارد کنید:")
            return
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ لطفاً مبلغ را فقط به صورت عدد انگلیسی بنویسید:")
        return

    user_states[message.from_user.id] = {"action": "choosing_payment_method", "amount": amount}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 کارت به کارت", callback_data=f"pay_c2c_{amount}"))
    markup.add(types.InlineKeyboardButton("↩️ انصراف", callback_data="cancel_action"))
    
    bot.send_message(message.chat.id, "💵 <b>روش پرداخت خود را انتخاب نمایید:</b>", reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_c2c_"))
def show_card_details(call):
    amount = safe_int(call.data.replace("pay_c2c_", ""))
    user_states[call.from_user.id] = {"action": "waiting_for_receipt", "amount": amount}
    bot.answer_callback_query(call.id)
    
    exact_rial = (amount * 10) + (int(time.time()) % 900) + 100
    
    card_text = (
        f"برای تایید سریع لطفاً دقیقاً مبلغ مشخص شده واریز شود. ⚠️\n\n"
        f"برای افزایش موجودی، مبلغ <b>{safe_format(exact_rial)} ریال</b> ({safe_format(amount)} تومان) را به شماره حساب زیر واریز کنید 👇\n\n"
        f"====================\n"
        f"<code>{CARD_NUMBER}</code>\n"
        f"<b>{CARD_NAME}</b>\n"
        f"====================\n\n"
        f"💰 <i>دقیقاً مبلغ ذکر شده را واریز فرمایید.</i>\n"
        f"‼️ <i>امکان برداشت وجه از کیف پول نیست.</i>\n\n"
        f"📸 پس از واریز، روی دکمه زیر زده و <b>تصویر فیش</b> را ارسال کنید:"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ پرداخت کردم | ارسال رسید", callback_data="ready_to_send_photo"))
    bot.send_message(call.message.chat.id, card_text, reply_markup=markup, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "ready_to_send_photo")
def ask_for_receipt_photo(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, "لطفاً همین الان تصویر رسید واریزی خود را ارسال فرمایید:")

# دریافت تصویر فیش 
@bot.message_handler(content_types=['photo'])
def handle_receipt_photo(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    
    if state.get("action") != "waiting_for_receipt":
        bot.reply_to(message, "اگر قصد افزایش موجودی دارید، ابتدا از بخش «کیف پول + شارژ» اقدام نمایید.")
        return

    amount = safe_int(state["amount"])
    receipt_id = f"rcp_{user_id}_{int(time.time())}"
    
    pending_receipts[receipt_id] = {
        "user_id": user_id,
        "amount": amount,
        "username": message.from_user.username or "ندارد"
    }

    photo_file_id = message.photo[-1].file_id

    markup = types.InlineKeyboardMarkup()
    btn_ok = types.InlineKeyboardButton("✅ تایید و شارژ حساب", callback_data=f"adm_ok_{receipt_id}")
    btn_no = types.InlineKeyboardButton("❌ رد رسید", callback_data=f"adm_no_{receipt_id}")
    markup.add(btn_ok, btn_no)

    admin_text = (
        f"🔔 <b>درخواست افزایش موجودی جدید</b>\n\n"
        f"👤 کاربر: @{message.from_user.username or 'ندارد'} (آیدی: <code>{user_id}</code>)\n"
        f"💰 مبلغ: <b>{safe_format(amount)} تومان</b>"
    )

    bot.send_photo(ADMIN_ID, photo_file_id, caption=admin_text, reply_markup=markup, parse_mode="HTML")
    bot.reply_to(message, "✅ فیش شما ارسال شد. پس از تایید مدیریت، موجودی شما به صورت آنی افزایش خواهد یافت.")
    user_states.pop(user_id, None)

@bot.callback_query_handler(func=lambda call: call.data.startswith("adm_ok_") or call.data.startswith("adm_no_"))
def admin_receipt_action(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "دسترسی نامعتبر.")
        return

    action, rcp_id = call.data.split("_")[1], "_".join(call.data.split("_")[2:])
    
    if rcp_id not in pending_receipts:
        bot.answer_callback_query(call.id, "این سفارش قبلاً تعیین وضعیت شده است.")
        return

    item = pending_receipts.pop(rcp_id)
    target_id = item["user_id"]
    amount = safe_int(item["amount"])

    if action == "ok":
        update_user_balance(target_id, amount)
        new_bal = get_user_balance(target_id)
        bot.edit_message_caption(f"✅ فیش تایید شد. موجودی کاربر <b>{safe_format(amount)} تومان</b> افزایش یافت.", chat_id=ADMIN_ID, message_id=call.message.message_id, parse_mode="HTML")
        
        user_alert = (
            f"🎉 <b>حساب شما شارژ شد!</b>\n\n"
            f"💰 مبلغ شارژ شده: <b>{safe_format(amount)} تومان</b>\n"
            f"⭐ موجودی کل جدید: <b>{safe_format(new_bal)} تومان</b>\n\n"
            f"اکنون می‌توانید از دکمه «خرید اشتراک» سفارش خود را ثبت کنید."
        )
        bot.send_message(target_id, user_alert, parse_mode="HTML")

    elif action == "no":
        bot.edit_message_caption("❌ فیش واریزی توسط شما رد شد.", chat_id=ADMIN_ID, message_id=call.message.message_id)
        bot.send_message(target_id, "❌ متاسفانه فیش واریزی شما جهت افزایش موجودی تایید نشد. در صورت وجود مشکل به پشتیبانی پیام دهید.")

# سرویس‌های من 
@bot.message_handler(func=lambda msg: msg.text and "سرویس" in msg.text and "من" in msg.text)
def show_my_services(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM services WHERE user_id = ? ORDER BY id DESC", (user_id,))
            rows = c.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "شما در حال حاضر هیچ سرویس فعالی ندارید.")
        return

    text = "📁 <b>لیست اشتراک‌های فعال شما:</b>\n\n"
    for r in rows:
        text += (
            f"🔹 <b>نام:</b> <code>{r['config_name']}</code>\n"
            f"📦 <b>پلن:</b> {r['plan_name']}\n"
            f"🔗 <b>لینک اتصال:</b>\n<code>{r['sub_url']}</code>\n"
            f"──────────────────\n"
        )
    bot.send_message(message.chat.id, text, parse_mode="HTML")

# تمدید سرویس 
@bot.message_handler(func=lambda msg: msg.text and "تمدید" in msg.text)
def renew_service_menu(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT config_name FROM services WHERE user_id = ?", (user_id,))
            rows = c.fetchall()

    if not rows:
        bot.send_message(message.chat.id, "سرویسی جهت تمدید برای شما یافت نشد.")
        return

    markup = types.InlineKeyboardMarkup()
    for r in rows:
        markup.add(types.InlineKeyboardButton(f"تمدید {r['config_name']}", callback_data=f"renew_{r['config_name']}"))
    bot.send_message(message.chat.id, "سرویس مورد نظر جهت تمدید را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("renew_"))
def process_renew(call):
    cfg_name = call.data.replace("renew_", "")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"جهت تمدید اشتراک <b>{cfg_name}</b> لطفاً به پشتیبانی پیام دهید تا بدون تغییر لینک، سرویس شما تمدید گردد.", parse_mode="HTML")

# اکانت تست رایگان 
@bot.message_handler(func=lambda msg: msg.text and "اکانت تست" in msg.text)
def handle_test_account(message):
    user_id = message.from_user.id
    user_states.pop(user_id, None)
    
    with db_lock:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM test_users WHERE user_id = ?", (user_id,))
            already_used = c.fetchone()

    if already_used:
        bot.send_message(message.chat.id, "❌ شما قبلاً یک‌بار اکانت تست رایگان دریافت کرده‌اید و امکان دریافت مجدد وجود ندارد.")
        return

    wait_msg = bot.send_message(message.chat.id, "⏳ در حال ساخت اکانت تست رایگان، لطفاً چند ثانیه صبر کنید...")
    test_user = f"test_{user_id}_{int(time.time()) % 1000}"
    test_bytes = 200 * 1024 * 1024  # 200 مگابایت

    sub_url, error = create_pasarguard_user(test_user, test_bytes, 1, note=f"اکانت تست {user_id}")

    if sub_url:
        with db_lock:
            with get_db() as conn:
                conn.execute("INSERT OR IGNORE INTO test_users (user_id, created_at) VALUES (?, ?)", (user_id, int(time.time())))
                conn.commit()

        bot.delete_message(message.chat.id, wait_msg.message_id)
        reply = (
            f"🎁 <b>اکانت تست رایگان شما آماده شد!</b>\n\n"
            f"🔹 مشخصات: ۲۰۰ مگابایت | ۱ روز مهلت استفاده\n"
            f"🔹 نام اشتراک: <code>{test_user}</code>\n\n"
            f"🔗 <b>لینک اتصال:</b>\n<code>{sub_url}</code>"
        )
        bot.send_message(message.chat.id, reply, parse_mode="HTML")
    else:
        bot.edit_message_text(f"❌ خطا در ساخت تست: {error}", chat_id=message.chat.id, message_id=wait_msg.message_id)

# پشتیبانی 
@bot.message_handler(func=lambda msg: msg.text and "پشتیبانی" in msg.text)
def support_cmd(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "جهت ارتباط با واحد پشتیبانی، لطفاً به آیدی @mohamadsarfaraz پیام دهید.")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_action")
def cancel_action_handler(call):
    user_states.pop(call.from_user.id, None)
    bot.answer_callback_query(call.id, "عملیات لغو شد.")
    bot.delete_message(call.message.chat.id, call.message.message_id)


print("Bot started successfully...")
bot.infinity_polling()