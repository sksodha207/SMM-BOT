import telebot
import qrcode
import re
import time
import requests
from PIL import Image, ImageDraw


# =============== CONFIG =================

BOT_TOKEN = "8209196902:AAHnUvlY0GCM4FKZr3TFGRRth1d6jG50eVY"

UPI_VPA = "sksodha207@okicici"
PAYEE_NAME = "SHADOW"

ADMIN_IDS = {8582102081}

SMM_API_URL = "https://mahadevsmmpanel.in/api/v2"
SMM_API_KEY = "5662d90a6d4affac7c9a71a5c58a0b66ed1274b1"

bot = telebot.TeleBot(BOT_TOKEN)


# ========= MEMORY STORAGE =========

users = {}
orders = {}
user_state = {}
temp_service = {}
pending_topups = {}


def set_state(uid, s):
    user_state[uid] = s


def get_state(uid):
    return user_state.get(uid)


def clear_state(uid):
    user_state.pop(uid, None)


def get_balance(uid):
    return users.get(uid, {"balance": 0})["balance"]


def add_balance(uid, amt):
    users.setdefault(uid, {"balance": 0})
    users[uid]["balance"] += amt


def is_admin(uid):
    return uid in ADMIN_IDS



# =========================================
#   CLEAN PANEL HTML DESCRIPTION TEXT
# =========================================

def clean_description(text):

    if not text:
        return "No description provided."

    text = re.sub(r"<.*?>", "", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)

    return text.strip()



# =========================================
#      FETCH ONLY INSTAGRAM SERVICES
# =========================================

def fetch_instagram_services():
    try:
        res = requests.post(
            SMM_API_URL,
            data={"key": SMM_API_KEY, "action": "services"}
        ).json()

        filtered = {}

        for s in res:
            name = s.get("name","").lower()
            cat = s.get("category","").lower()

            if ("insta" in name) or ("instagram" in name) or ("insta" in cat):

                filtered[s["service"]] = {
                    "name": s.get("name"),
                    "rate": float(s.get("rate", 0)),
                    "min": s.get("min", "N/A"),
                    "max": s.get("max", "N/A"),
                    "category": s.get("category", "Instagram"),
                    "desc": clean_description(s.get("description", ""))
                }

        print(f"Loaded {len(filtered)} Instagram services only")
        return filtered

    except Exception as e:
        print("SERVICE FETCH ERROR →", e)
        return {}



services = fetch_instagram_services()



# =========================================
#     PAGINATION
# =========================================

def chunk_services(per_page=25):
    items = list(services.items())
    pages = []

    for i in range(0, len(items), per_page):
        pages.append(dict(items[i:i+per_page]))

    return pages


service_pages = chunk_services()



# =========================================
#            PANEL ORDER API
# =========================================

def create_smm_order(service_id, link, qty):
    try:
        return requests.post(
            SMM_API_URL,
            data={
                "key": SMM_API_KEY,
                "action": "add",
                "service": service_id,
                "link": link,
                "quantity": qty
            }
        ).json()

    except Exception as e:
        print("SMM API ERROR →", e)
        return None



# =========================================
#        QR PAYMENT GENERATOR
# =========================================

def make_qr(amount, order_id):

    upi = (
        f"upi://pay?pa={UPI_VPA}"
        f"&pn={PAYEE_NAME}"
        f"&am={amount}"
        f"&cu=INR"
        f"&tn=Wallet%20{order_id}"
    )

    qr = qrcode.QRCode(box_size=12, border=2)
    qr.add_data(upi)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    file = f"qr_{order_id}.png"
    img.save(file)

    return file



# =========================================
#                MAIN MENU
# =========================================

def main_menu(cid):

    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🛒 Instagram Services", "💰 Wallet")
    kb.add("👤 Profile")

    bot.send_message(
        cid,
        "🔥 Instagram SMM Panel Bot\nChoose option 👇",
        reply_markup=kb
    )



@bot.message_handler(commands=["start"])
def start(message):

    uid = message.from_user.id
    users.setdefault(uid, {"balance": 0})

    clear_state(uid)
    main_menu(message.chat.id)



# =========================================
#                PROFILE
# =========================================

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def profile(message):

    uid = message.from_user.id

    bot.send_message(
        message.chat.id,
        f"👤 Profile\n\n"
        f"🆔 `{uid}`\n"
        f"💰 Balance: ₹{get_balance(uid)}",
        parse_mode="Markdown"
    )



# =========================================
#                WALLET
# =========================================

@bot.message_handler(func=lambda m: m.text == "💰 Wallet")
def wallet(message):

    uid = message.from_user.id
    clear_state(uid)

    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Add Balance", "⬅ Back")

    bot.send_message(
        message.chat.id,
        f"💰 Wallet Balance: ₹{get_balance(uid)}",
        reply_markup=kb
    )



# =========================================
#        ADD BALANCE (PENDING MODE)
# =========================================

@bot.message_handler(func=lambda m: m.text == "➕ Add Balance")
def ask_amount(message):

    uid = message.from_user.id
    set_state(uid, "await_add_amount")

    bot.send_message(
        message.chat.id,
        "💰 Enter amount to add (₹):"
    )



@bot.message_handler(func=lambda m: get_state(m.from_user.id) == "await_add_amount")
def create_topup(message):

    uid = message.from_user.id

    try:
        amount = float(message.text)
    except:
        return bot.reply_to(message, "❌ Enter a valid number")

    if amount <= 0:
        return bot.reply_to(message, "❌ Amount must be greater than 0")

    topup_id = int(time.time())

    pending_topups[topup_id] = {
        "user": uid,
        "amount": amount,
        "status": "PENDING"
    }

    qr_file = make_qr(amount, topup_id)

    clear_state(uid)

    # send QR to user
    bot.send_photo(
        message.chat.id,
        open(qr_file, "rb"),
        caption=
        f"🧾 *Top-Up Request Created*\n\n"
        f"🔑 Order ID: `{topup_id}`\n"
        f"💰 Amount: ₹{amount}\n\n"
        f"📌 Pay using UPI & send screenshot\n"
        f"⏳ Status: *Pending Verification*",
        parse_mode="Markdown"
    )

    # ======================
    # ADMIN AUTO NOTIFY 🚨
    # ======================
    for admin in ADMIN_IDS:
        bot.send_message(
            admin,
            f"🆕 *New Top-Up Request*\n\n"
            f"👤 User: `{uid}`\n"
            f"🧾 ID: `{topup_id}`\n"
            f"💰 Amount: ₹{amount}\n"
            f"⏳ Status: PENDING\n\n"
            f"✔ Approve:\n/approve {topup_id}",
            parse_mode="Markdown"
        )



# =========================================
#        ADMIN — PENDING LIST
# =========================================

@bot.message_handler(commands=["pending"])
def show_pending(message):

    if message.from_user.id not in ADMIN_IDS:
        return

    txt = "⏳ *Pending Top-Ups*\n\n"

    found = False

    for tid, t in pending_topups.items():
        if t["status"] == "PENDING":
            found = True
            txt += (
                f"🧾 ID: `{tid}`\n"
                f"👤 User: `{t['user']}`\n"
                f"💰 Amount: ₹{t['amount']}`\n"
                f"✔ /approve {tid}\n\n"
            )

    if not found:
        txt = "👍 No pending top-ups"

    bot.reply_to(message, txt, parse_mode="Markdown")



# =========================================
#        ADMIN — APPROVE PAYMENT
# =========================================

@bot.message_handler(commands=["approve"])
def approve_topup(message):

    if message.from_user.id not in ADMIN_IDS:
        return

    parts = message.text.split()

    if len(parts) < 2:
        return bot.reply_to(message, "Usage:\n/approve topup_id")

    topup_id = int(parts[1])

    if topup_id not in pending_topups:
        return bot.reply_to(message, "❌ Invalid Top-Up ID")

    data = pending_topups[topup_id]

    if data["status"] == "APPROVED":
        return bot.reply_to(message, "⚠ Already approved")

    add_balance(data["user"], data["amount"])
    data["status"] = "APPROVED"

    bot.send_message(
        data["user"],
        f"✅ ₹{data['amount']} added to your wallet!"
    )

    bot.reply_to(
        message,
        f"🟢 Top-Up Approved\n"
        f"User: {data['user']}\n"
        f"Amount: ₹{data['amount']}"
    )



# ---------- BACK BUTTON ----------

@bot.message_handler(func=lambda m: m.text == "⬅ Back")
def back_btn(message):
    start(message)



# =========================================
#          SHOW INSTAGRAM SERVICES
# =========================================

@bot.message_handler(func=lambda m: m.text == "🛒 Instagram Services")
def service_list(message):

    if not services:
        return bot.send_message(message.chat.id, "⚠ No Instagram services found")

    show_service_page(message.chat.id, 0)



def show_service_page(chat_id, page):

    page = max(0, min(page, len(service_pages)-1))

    txt = f"📌 Instagram Services\n📄 Page {page+1}/{len(service_pages)}\n\n"

    mapping = {}
    idx = 1

    for sid, s in service_pages[page].items():
        txt += f"{idx}. {s['name']} — ₹{s['rate']} / 1k\n"
        mapping[idx] = sid
        idx += 1

    txt += "\nSend service number to continue."

    temp_service[chat_id] = {"map": mapping, "page": page}

    set_state(chat_id, "choose_service")

    kb = telebot.types.InlineKeyboardMarkup()

    if page > 0:
        kb.add(telebot.types.InlineKeyboardButton("⬅ Prev", callback_data=f"page_{page-1}"))

    if page < len(service_pages)-1:
        kb.add(telebot.types.InlineKeyboardButton("Next ➡", callback_data=f"page_{page+1}"))

    bot.send_message(chat_id, txt, reply_markup=kb)



@bot.callback_query_handler(func=lambda c: c.data.startswith("page_"))
def change_page(c):

    page = int(c.data.split("_")[1])

    bot.delete_message(c.message.chat.id, c.message.message_id)

    show_service_page(c.message.chat.id, page)



# =========================================
#      SERVICE SELECT
# =========================================

@bot.message_handler(func=lambda m: get_state(m.from_user.id) == "choose_service")
def choose_service(message):

    uid = message.from_user.id

    clean = re.sub(r"\D", "", message.text)

    if not clean.isdigit():
        return bot.reply_to(message, "❌ Enter a valid service number")

    num = int(clean)

    mapping = temp_service[uid]["map"]

    if num not in mapping:
        return bot.reply_to(message, "⚠ Invalid service")

    sid = mapping[num]
    service = services[sid]

    temp_service[uid] = {"service": sid}

    set_state(uid, "enter_link")

    bot.send_message(
        message.chat.id,
        f"📌 *{service['name']}*\n"
        f"💰 Rate: ₹{service['rate']} / 1k\n"
        f"🔢 Min: {service['min']} | Max: {service['max']}\n\n"
        f"🔗 Send link / username",
        parse_mode="Markdown"
    )



# =========================================
#      LINK → QTY → ORDER
# =========================================

@bot.message_handler(func=lambda m: get_state(m.from_user.id) == "enter_link")
def take_link(message):

    uid = message.from_user.id
    temp_service[uid]["link"] = message.text

    set_state(uid, "enter_quantity")

    bot.send_message(message.chat.id, "🔢 Enter quantity")



@bot.message_handler(func=lambda m: get_state(m.from_user.id) == "enter_quantity")
def place_order(message):

    uid = message.from_user.id

    if not message.text.isdigit():
        return bot.reply_to(message, "❌ Enter numbers only")

    qty = int(message.text)

    sid = temp_service[uid]["service"]
    service = services[sid]

    cost = round((service["rate"] / 1000) * qty, 4)

    if get_balance(uid) < cost:
        clear_state(uid)
        return bot.send_message(
            message.chat.id,
            f"⚠ Insufficient Balance\n"
            f"Order Cost: ₹{cost}\n"
            f"Your Balance: ₹{get_balance(uid)}"
        )

    add_balance(uid, -cost)

    link = temp_service[uid]["link"]

    bot.send_message(message.chat.id, "⏳ Placing order…")

    res = create_smm_order(sid, link, qty)

    if not res or "order" not in res:
        add_balance(uid, cost)
        clear_state(uid)
        return bot.send_message(message.chat.id, "🔴 Panel Error — Refunded")

    oid = int(time.time())

    orders[oid] = {
        "user": uid,
        "service": service["name"],
        "qty": qty,
        "amount": cost,
        "panel_order_id": res["order"],
        "status": "ACTIVE"
    }

    bot.send_message(
        message.chat.id,
        f"🟢 Order Placed\n\n"
        f"🧾 Order ID: {oid}\n"
        f"📌 {service['name']}\n"
        f"🔢 Qty: {qty}\n"
        f"💰 Cost: ₹{cost}"
    )

    clear_state(uid)



print("Bot Running…")

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
    except Exception as e:
        print("Polling error →", e)
        time.sleep(3)