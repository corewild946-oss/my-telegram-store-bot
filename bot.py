import telebot
import google.generativeai as genai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import os
import re
from dotenv import load_dotenv

load_dotenv()

# --- သင့်ရဲ့ အချက်အလက်များ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
ADMIN_USERNAME = "@NyeinChanKoKo24" # သင့်ရဲ့ Admin Telegram Username ကို ဒီမှာထည့်ပါ

# --- Shared & Private အကောင့် စီမံခန့်ခွဲမှု စနစ် ---
INVENTORY = {
    "Capcut_Shared": {
        "display_name": "Capcut Pro (Shared Account)",
        "type": "shared",
        "price": 15000, # Device ၁ ခုစာ ဈေးနှုန်း
        "details": "Device တစ်ခုစာ ဈေးနှုန်းဖြစ်ပါသည်။",
        "login_instructions": "Capcut App ကိုဖွင့်ပြီး ပေးထားသော Email နှင့် Password ကို ထည့်သွင်း အသုံးပြုပါ။ (သတ်မှတ် Device အရေအတွက်သာ သုံးပေးပါရန်)",
        "accounts": [
            # total_slots = ရောင်းချမည့် စုစုပေါင်း Device, used_slots = ရောင်းပြီးသား Device
            {"credentials": "Email: capcut_share1@gmail.com | Pass: 111111", "total_slots": 3, "used_slots": 0},
            {"credentials": "Email: capcut_share2@gmail.com | Pass: 222222", "total_slots": 3, "used_slots": 0}
        ]
    },
    "Capcut_Private": {
        "display_name": "Capcut Pro (Private Account)",
        "type": "private",
        "price": 40000, 
        "details": "ကိုယ်ပိုင် Private အကောင့် (Device 3 ခုစာ တစ်ခါတည်းပါဝင်သည်)",
        "login_instructions": "Capcut တွင် လော့အင်ဝင်ပြီး စိတ်ကြိုက် Password ပြောင်းလဲ အသုံးပြုနိုင်ပါသည်။",
        "accounts": [
            "Email: capcut_priv1@gmail.com | Pass: private123",
            "Email: capcut_priv2@gmail.com | Pass: private456"
        ]
    }
}

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Customer မှာယူမှုများကို မှတ်သားထားမည့်နေရာ (Product Key နှင့် အရေအတွက်)
user_orders = {}

# လက်ကျန် အရေအတွက်ကို တွက်ချက်ပေးမည့် Function
def get_stock(product_key):
    item = INVENTORY.get(product_key)
    if not item: return 0
    
    if item["type"] == "shared":
        # Shared ဆိုလျှင် အကောင့်အားလုံးထဲမှ ရောင်းရန်ကျန်သော Device အရေအတွက်ကို ပေါင်းပြမည်
        return sum(acc["total_slots"] - acc["used_slots"] for acc in item["accounts"])
    else:
        # Private ဆိုလျှင် ကျန်ရှိသော အကောင့်အရေအတွက်ကို ပြမည်
        return len(item["accounts"])

# AI အတွက် Stock အခြေအနေကို စာသားပြောင်းပေးမည့် Function
def get_inventory_context():
    context = "လက်ရှိ ဆိုင်တွင်ရနိုင်သော ပစ္စည်းစာရင်းများ:\n"
    for key, info in INVENTORY.items():
        stock_count = get_stock(key)
        stock_status = f"ရနိုင်သည် (လက်ကျန် {stock_count} ခု)" if stock_count > 0 else "ကုန်နေသည် (Out of stock)"
        context += f"- Product ID: [{key}] | နာမည်: {info['display_name']} | ဈေးနှုန်း: {info['price']} ကျပ် | အကြောင်းအရာ: {info['details']} | အခြေအနေ: {stock_status}\n"
    return context

system_prompt = f"""
မင်းက Software တွေရောင်းပေးတဲ့ Telegram Bot လေးပါ။ နာမည်က 'Software Store Bot' ပါ။ 
Admin ရဲ့ Username က {ADMIN_USERNAME} ပါ။
{get_inventory_context()}

အရေးကြီး စည်းကမ်းချက်များ:
၁။ သဘာဝကျကျ စကားပြောပါ: Customer က "ဟိုင်း" လိုမျိုး နှုတ်ဆက်ရင် သဘာဝကျကျ ပြန်နှုတ်ဆက်ပါ။ ပစ္စည်းစာရင်းတွေ အတင်းချမပြပါနဲ့။
၂။ အရေအတွက် တွက်ချက်ပေးပါ: Customer က Shared Account ကို Device ၂ ခုစာ လိုချင်တယ်ဆိုရင် ဈေးနှုန်းကို အလိုအလျောက် မြှောက်ပြီး (၁၅၀၀၀ x ၂ = ၃၀၀၀၀ ကျပ်) တွက်ပေးပါ။ Private Account ဆိုပါက အကောင့်တစ်ခုလုံး ဈေးဖြစ်၍ မြှောက်ရန်မလိုပါ။ 
၃။ Admin နှင့် ဆက်သွယ်ရန်: Error သို့မဟုတ် အခြားကိစ္စများအတွက် "အသေးစိတ် ပြောပြပေးပါ" ဟုဖြေပြီး မင်း၏စာသားအဆုံးတွင် `[SUPPORT]` ဟု လျှို့ဝှက်ထည့်ပါ။
၄။ ဝယ်ယူရန် သေချာပါက: ကျသင့်ငွေကို KPay (09123456789 - U Ba) သို့ လွှဲရန်ပြောပြီး ပြေစာ(Screenshot) ပို့ရန်ပြောပါ။ 
၅။ (အလွန်အရေးကြီးသည်) ဝယ်ယူရန်သေချာပါက စာ၏အဆုံးတွင် `[ORDER: Product ID | အရေအတွက်]` ဟု မဖြစ်မနေ ထည့်ရေးပေးပါ။ အရေအတွက်မှာ ဂဏန်းသက်သက်သာ ဖြစ်ရမည်။ 
(ဥပမာ Shared 2 ခုဝယ်လျှင် - [ORDER: Capcut_Shared | 2])
(ဥပမာ Private 1 ခုဝယ်လျှင် - [ORDER: Capcut_Private | 1])
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "မင်္ဂလာပါဗျာ။ Software Store မှ ကြိုဆိုပါတယ်။ ဘယ်လို Software မျိုးကို စုံစမ်းချင်တာလဲဗျ။")

@bot.message_handler(commands=['reply'])
def admin_reply_to_user(message):
    if str(message.chat.id) != ADMIN_CHAT_ID: return
    try:
        parts = message.text.split(' ', 2)
        bot.send_message(parts[1], f"👨‍💻 **Admin မှ အကြောင်းပြန်စာ:**\n\n{parts[2]}", parse_mode="Markdown")
        bot.reply_to(message, "✅ Customer ထံသို့ စာပို့ပြီးပါပြီ။")
    except Exception as e:
        bot.reply_to(message, "❌ Command မှားနေပါတယ်။ Format: `/reply UserID စာသား`")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if str(message.chat.id) == ADMIN_CHAT_ID and message.text.startswith('/'): return
        
    try:
        prompt = system_prompt + "\nCustomer စာ: " + message.text
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Order ထဲမှ Product ID နှင့် အရေအတွက်(Qty) ကို ဆွဲထုတ်ခြင်း
        match_order = re.search(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', response_text)
        if match_order:
            product_key = match_order.group(1).strip()
            qty = int(match_order.group(2).strip())
            user_orders[message.chat.id] = {"product": product_key, "qty": qty}
            response_text = re.sub(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', '', response_text).strip()
            
        if "[SUPPORT]" in response_text:
            response_text = response_text.replace("[SUPPORT]", "").strip()
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ **Support အကြောင်းကြားစာ:**\nCustomer ID: `{message.chat.id}`\n\n**စာ:** {message.text}\n\n*(ပြန်စာပို့ရန် `/reply {message.chat.id} စာသား` ဖြင့် ပို့ပါ)*", parse_mode="Markdown")
            
        bot.reply_to(message, response_text)
    except Exception as e:
        bot.reply_to(message, "ခဏလေးစောင့်ပေးပါဗျ။ အင်တာနက် အနည်းငယ် နှေးနေပါတယ်။")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name
    order_info = user_orders.get(user_id)
    
    if not order_info:
        bot.reply_to(message, "ကျေးဇူးပြု၍ ဝယ်ယူမည့် ပစ္စည်းအမည်နှင့် အရေအတွက်ကို အရင်ဆုံး ပြောပြပေးပါဗျ။ (ဥပမာ - Capcut Shared Device ၂ ခု ဝယ်မယ်)")
        return

    product_key = order_info["product"]
    qty = order_info["qty"]
    display_name = INVENTORY.get(product_key, {}).get("display_name", product_key)
    
    markup = InlineKeyboardMarkup()
    btn_approve = InlineKeyboardButton("Approve (လက်ခံမည်)", callback_data=f"app|{user_id}")
    btn_reject = InlineKeyboardButton("Reject (ငြင်းပယ်မည်)", callback_data=f"rej|{user_id}")
    markup.add(btn_approve, btn_reject)
    
    admin_caption = f"📦 **ငွေလွှဲပြေစာ ဝင်ထားပါသည်**\nCustomer: @{username} (ID: `{user_id}`)\nဝယ်ယူသည့် ပစ္စည်း: {display_name}\nအရေအတွက်: {qty} ခုစာ"
    bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=admin_caption, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီဗျ။ Admin မှ စစ်ဆေးပြီးတာနဲ့ အကောင့်ကို ချက်ချင်း ပို့ပေးပါမယ်။")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data.split('|')
    action = data[0]
    customer_id = int(data[1])
    order_info = user_orders.get(customer_id)
    
    if not order_info:
        bot.send_message(ADMIN_CHAT_ID, "⚠️ Order အချက်အလက် ရှာမတွေ့တော့ပါ။ Bot Restart ကျသွားခြင်း ဖြစ်နိုင်ပါသည်။")
        return

    product_key = order_info["product"]
    qty = order_info["qty"]
    item = INVENTORY.get(product_key)
    
    if not item: return

    if action == "app":
        assigned_account = None
        
        # Shared Account ဖြတ်တောက်ခြင်း Logic
        if item["type"] == "shared":
            for acc in item["accounts"]:
                avail = acc["total_slots"] - acc["used_slots"]
                if avail >= qty:
                    acc["used_slots"] += qty # ဝယ်သွားသည့် အရေအတွက်အတိုင်း Slot နှုတ်မည်
                    assigned_account = acc["credentials"]
                    break
                    
        # Private Account ဖြတ်တောက်ခြင်း Logic
        elif item["type"] == "private":
            if len(item["accounts"]) >= qty:
                assigned_accounts_list = [item["accounts"].pop(0) for _ in range(qty)]
                assigned_account = "\n\n".join(assigned_accounts_list)

        if assigned_account:
            # Customer ထံ အကောင့်ပေးပို့ခြင်း
            instructions = item["login_instructions"]
            success_msg = f"✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။\n\n**သင့်ရဲ့ အကောင့်အချက်အလက်:**\n`{assigned_account}`\n\n**အသုံးပြုနည်း:**\n{instructions}\n\nအဆင်မပြေတာရှိရင် ပြန်လည်မေးမြန်းနိုင်ပါတယ်ဗျ။"
            bot.send_message(customer_id, success_msg, parse_mode="Markdown")
            
            # Admin ထံ စာရင်းရှင်းတမ်း Report ပြန်ပို့ခြင်း
            rem_stock = get_stock(product_key)
            report_msg = f"✅ **Customer သို့ အကောင့်ပို့ပြီးပါပြီ**\nCustomer ID: `{customer_id}`\nပစ္စည်း: {item['display_name']}\nDevice/အရေအတွက်: {qty}\n\nပေးလိုက်သော အကောင့်:\n`{assigned_account}`\n\n📦 **လက်ကျန် Stock: {rem_stock} ခု ကျန်ပါသေးသည်**"
            bot.edit_message_caption(report_msg, chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id, parse_mode="Markdown")
            
            # Order ပြီးဆုံးသွားသဖြင့် မှတ်ထားသည်ကို ဖျက်မည်
            del user_orders[customer_id]
        else:
            bot.edit_message_caption(f"⚠️ Approve ပေးသော်လည်း **{item['display_name']}** အတွက် Stock မလုံလောက်တော့ပါ။ \nCustomer ထံသို့ အကောင့်သစ် Manual သွားပို့ပေးပါ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)
            bot.send_message(customer_id, "✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။ သင့်အကောင့်ကို Admin မှ ခဏအတွင်း လာရောက်ပို့ပေးပါမည်။")
            
    elif action == "rej":
        bot.send_message(customer_id, "❌ ငွေလွှဲမှု မှားယွင်းနေပါသဖြင့် Admin မှ ပယ်ဖျက်လိုက်ပါတယ်။ ငွေလွှဲမှတ်တမ်းကို ပြန်စစ်ပေးပါဗျ။")
        bot.edit_message_caption("❌ ငြင်းပယ် (Reject) လုပ်ပြီးပါပြီ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)

# --- ၂၄ နာရီ အလုပ်လုပ်စေရန် Web Server အပိုင်း ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7 with Advanced Inventory!"

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)