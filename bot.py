import telebot
import google.generativeai as genai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import os
import re

# --- (၁) သင့်ရဲ့ အချက်အလက်များ ---
TELEGRAM_BOT_TOKEN = "8782930465:AAGvPwcenVM6vQ2qTBh7f4hgjCex9hkfkL0"
GEMINI_API_KEY = "AIzaSyDiliSEq0iK__zWTs___KyZU2WW2_R3034"
ADMIN_CHAT_ID = "1590595729" 

# --- (၂) ဒီနေရာမှာ မိမိရောင်းမည့် ပစ္စည်းနှင့် "အကောင့်များ (Accounts)" ကို ထည့်ပါ ---
INVENTORY = {
    "Capcut Pro": {
        "price": "၁၅၀၀၀ ကျပ်",
        "duration": "၁ လစာ",
        "details": "Device တစ်ခုစာ",
        "in_stock": True,
        # Customer ကို Auto ပို့ပေးမည့် အကောင့်/Code များ (ရောင်းပြီးတာနဲ့ ဒီထဲကနေ အလိုလို လျော့သွားပါမည်)
        "accounts": [
            "Email: capcut1@gmail.com | Pass: 111111",
            "Email: capcut2@gmail.com | Pass: 222222",
            "Code: CAPCUT-PREMIUM-XYZ123"
        ]
    },
    "Picsart Pro": {
        "price": "၁၀၀၀၀ ကျပ်",
        "duration": "၁ လစာ",
        "details": "Device တစ်ခုစာ",
        "in_stock": True,
        "accounts": [
            "Email: picsart1@gmail.com | Pass: 12345"
        ]
    },
}

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Customer ဘာဝယ်လဲဆိုတာ ယာယီမှတ်ထားမည့် နေရာ
user_orders = {}

def get_inventory_context():
    context = "လက်ရှိ ဆိုင်တွင်ရနိုင်သော ပစ္စည်းစာရင်းများ:\n"
    for item, info in INVENTORY.items():
        stock_status = "ရနိုင်သည်" if info['in_stock'] else "ကုန်နေသည် (Out of stock)"
        context += f"- {item}: {info['duration']} {info['price']} ({info['details']}) | အခြေအနေ: {stock_status}\n"
    return context

system_prompt = f"""
မင်းက Software တွေရောင်းပေးတဲ့ Telegram Bot လေးပါ။ နာမည်က 'Software Store Bot' ပါ။
{get_inventory_context()}
စည်းကမ်းချက်များ:
၁။ အထက်ပါ ပစ္စည်းစာရင်းတွင် 'ရနိုင်သည်' ဟု ပြထားသော software များကိုသာ ရောင်းပါ။
၂။ 'ကုန်နေသည်' ဟု ပြထားသော software များကို မေးလာလျှင် လက်ရှိမှာ မရနိုင်သေးကြောင်း ယဉ်ကျေးစွာ ငြင်းပါ။
၃။ Customer က ဝယ်မည်ဟု သေချာလျှင် ကျသင့်ငွေကို KPay (09123456789 - U Ba) သို့ လွှဲရန်ပြောပြီး၊ ပြေစာ (Screenshot) ပို့ပေးရန် ပြောပါ။
၄။ (အလွန်အရေးကြီးသည်) Customer ကို ငွေလွှဲရန် ပြောသည့်စာသား၏ အဆုံးတွင် `[ORDER: ပစ္စည်းနာမည်]` ဟု မဖြစ်မနေ ထည့်ရေးပေးပါ။ ဥပမာ - [ORDER: Capcut Pro] သို့မဟုတ် [ORDER: Picsart Pro]
"""

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "မင်္ဂလာပါဗျာ။ Software Store မှ ကြိုဆိုပါတယ်။ ဘယ်လို Software မျိုးကို စုံစမ်းချင်တာလဲဗျ။")

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        prompt = system_prompt + "\nCustomer စာ: " + message.text
        response = model.generate_content(prompt)
        response_text = response.text
        
        # AI ဆီမှ Customer ဝယ်မည့် ပစ္စည်းနာမည်ကို ဆွဲထုတ်ခြင်း
        match = re.search(r'\[ORDER:\s*(.*?)\]', response_text)
        if match:
            product = match.group(1).strip()
            user_orders[message.chat.id] = product  # Customer ဘာဝယ်လဲ မှတ်ထားလိုက်ပြီ
            response_text = re.sub(r'\[ORDER:\s*(.*?)\]', '', response_text).strip() # Customer မမြင်အောင် ဖျက်လိုက်သည်
            
        bot.reply_to(message, response_text)
    except Exception as e:
        bot.reply_to(message, "ခဏလေးစောင့်ပေးပါဗျ။ အင်တာနက် အနည်းငယ် နှေးနေပါတယ်။")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name
    
    # မှတ်ထားသည့် Customer ဝယ်မည့်ပစ္စည်းကို ပြန်ယူခြင်း
    product_name = user_orders.get(user_id, "Unknown")
    
    markup = InlineKeyboardMarkup()
    # callback data တွင် Customer ID နှင့် Product Name တွဲပို့ပေးသည်
    btn_approve = InlineKeyboardButton("Approve (လက်ခံမည်)", callback_data=f"app|{user_id}|{product_name}")
    btn_reject = InlineKeyboardButton("Reject (ငြင်းပယ်မည်)", callback_data=f"rej|{user_id}|{product_name}")
    markup.add(btn_approve, btn_reject)
    
    bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=f"📦 Customer @{username} မှ ငွေလွှဲထားပါသည်။\nဝယ်ယူမည့်ပစ္စည်း - {product_name}", reply_markup=markup)
    bot.reply_to(message, "ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီဗျ။ Admin မှ စစ်ဆေးပြီးတာနဲ့ အကောင့်ကို အလိုအလျောက် ပို့ပေးပါမယ်။")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data.split('|')
    action = data[0]
    customer_id = data[1]
    product_name = data[2]
    
    if action == "app":
        # Admin က Approve ပေးလျှင် INVENTORY ထဲရှိ 'accounts' စာရင်းမှ ပထမဆုံးတစ်ခုကို ယူမည်
        accounts_list = INVENTORY.get(product_name, {}).get("accounts", [])
        
        if accounts_list:
            # ပထမဆုံး အကောင့်ကိုထုတ်ယူပြီး စာရင်းထဲမှ ဖျက်လိုက်သည် (.pop(0) ၏သဘောတရား)
            account_details = accounts_list.pop(0) 
            
            success_msg = f"✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။ ဝယ်ယူမှုအတွက် ကျေးဇူးတင်ပါတယ်ဗျ။\n\nသင့်ရဲ့ အကောင့်အချက်အလက်မှာ အောက်ပါအတိုင်းဖြစ်ပါတယ်:\n\n`{account_details}`\n\nအဆင်မပြေတာရှိရင် ပြန်လည်မေးမြန်းနိုင်ပါတယ်ဗျ။"
            bot.send_message(customer_id, success_msg)
            
            bot.edit_message_caption(f"✅ Customer ဆီသို့ {product_name} အကောင့် ပို့ပေးပြီးပါပြီ။\n(လက်ကျန် အကောင့်: {len(accounts_list)} ခု)", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)
        else:
            # အကောင့်ကုန်နေပါက Admin ဆီ သတိပေးစာပို့မည်
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ သတိပြုရန် - {product_name} အတွက် ပို့ပေးစရာ အကောင့်မရှိတော့ပါ။ Customer ထံသို့ Manual သွားပို့ပေးပါ။")
            bot.edit_message_caption(f"⚠️ Approve ပေးပြီးသော်လည်း Stock မရှိ၍ Auto မပို့နိုင်ပါ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)
            bot.send_message(customer_id, "✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။ သင့်အကောင့်ကို Admin မှ ခဏအတွင်း လာရောက်ပို့ပေးပါမည်။")
            
    elif action == "rej":
        bot.send_message(customer_id, "❌ ငွေလွှဲမှု မှားယွင်းနေပါသဖြင့် Admin မှ ပယ်ဖျက်လိုက်ပါတယ်။ ငွေလွှဲမှတ်တမ်းကို ပြန်စစ်ပေးပါဗျ။")
        bot.edit_message_caption("❌ ငြင်းပယ် (Reject) လုပ်ပြီးပါပြီ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)

# --- ၂၄ နာရီ အလုပ်လုပ်စေရန် Web Server အပိုင်း ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)