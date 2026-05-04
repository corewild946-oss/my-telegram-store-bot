import telebot
import google.generativeai as genai
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import threading
import os
import re
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

load_dotenv()

# --- အချက်အလက်များ ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
ADMIN_USERNAME = "@NyeinChanKoKo24" # သင့်ရဲ့ Admin Username လေး ပြင်ထည့်ပါဗျ

# --- Google Sheets ချိတ်ဆက်ခြင်း ---
SHEET_ID = '1kw8MLCSk9d_38Vmxet3BM4cwAqUL4Qy50diFNWeFw7o'
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

# Customer မှတ်တမ်း
user_orders = {}

# Google Sheet မှ Data များကို ဆွဲယူခြင်း
def get_inventory_from_sheet():
    records = sheet.get_all_records()
    context = "လက်ရှိ ဆိုင်တွင်ရနိုင်သော ပစ္စည်းစာရင်းများ:\n"
    has_items = False
    
    for row in records:
        try:
            pid = str(row.get('ProductID', '')).strip()
            if not pid: continue
            name = str(row.get('Name', ''))
            price = str(row.get('Price', ''))
            
            total_slots = int(row.get('Total_Slots', 0)) if str(row.get('Total_Slots', '')).strip() else 0
            used_slots = int(row.get('Used_Slots', 0)) if str(row.get('Used_Slots', '')).strip() else 0
            
            avail = total_slots - used_slots
            if avail > 0:
                context += f"- Product ID: [{pid}] | နာမည်: {name} | ဈေးနှုန်း: {price} ကျပ် | လက်ကျန်: {avail} ခု\n"
                has_items = True
        except Exception as e:
            continue
            
    if not has_items:
        context += "လက်ရှိတွင် ပစ္စည်းများ မရှိသေးပါ။"
    return context, records

# --- 1. /start Command ---
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "မင်္ဂလာပါဗျာ။ Software Store မှ ကြိုဆိုပါတယ်။ ဘာများ ကူညီပေးရမလဲဗျ။")

# --- 2. Admin Command: လက်ကျန်စစ်ရန် ---
@bot.message_handler(commands=['stock'])
def admin_check_stock(message):
    if str(message.chat.id) != ADMIN_CHAT_ID: return
    context, _ = get_inventory_from_sheet()
    bot.reply_to(message, f"📊 **လက်ရှိ Database မှ စာရင်း:**\n\n{context}", parse_mode="Markdown")

# --- 3. Admin Command: Customer ကို Bot မှတစ်ဆင့် စာပြန်ရန် (Fail-safe Fallback) ---
@bot.message_handler(commands=['reply'])
def admin_reply_to_user(message):
    if str(message.chat.id) != ADMIN_CHAT_ID: return
    try:
        parts = message.text.split(' ', 2)
        user_id = parts[1]
        reply_text = parts[2]
        bot.send_message(user_id, f"👨‍💻 **Admin မှ အကြောင်းပြန်စာ:**\n\n{reply_text}", parse_mode="Markdown")
        bot.reply_to(message, "✅ Customer ထံသို့ အောင်မြင်စွာ ပို့ပြီးပါပြီ။")
    except Exception as e:
        bot.reply_to(message, "❌ Command မှားနေပါတယ်။ Format: `/reply UserID စာသား` အတိုင်း ရိုက်ပါ။")

# --- 4. AI Chat & Error Handling ---
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if str(message.chat.id) == ADMIN_CHAT_ID and message.text.startswith('/'): return
        
    try:
        inv_context, _ = get_inventory_from_sheet()
        system_prompt = f"""
        မင်းက Software တွေရောင်းပေးတဲ့ Telegram Bot လေးပါ။ 
        Admin ရဲ့ Username က {ADMIN_USERNAME} ပါ။
        {inv_context}
        
        စည်းကမ်းချက်များ:
        ၁။ သဘာဝကျကျ စကားပြောပါ။ အရေအတွက်များလျှင် ဈေးနှုန်းကို မြှောက်တွက်ပေးပါ။
        ၂။ Customer ဘက်မှ အကောင့်ဝင်မရခြင်း၊ Error တက်ခြင်းများ ပြောလာပါက အဆုံးတွင် `[SUPPORT]` ဟု လျှို့ဝှက်ထည့်ပါ။
        ၃။ ဝယ်ယူရန်သေချာပါက KPay (09123456789 - U Ba) သို့ ငွေလွှဲပြေစာ တောင်းပါ။
        ၄။ (အရေးကြီး) ဝယ်ရန်သေချာပါက စာ၏အဆုံးတွင် `[ORDER: Product ID | အရေအတွက်]` ဟု အင်္ဂလိပ်ဂဏန်းသက်သက်ဖြင့်သာ မဖြစ်မနေ ထည့်ရေးပေးပါ။ 
        (ဥပမာ - [ORDER: Capcut_Shared | 2])
        """
        
        prompt = system_prompt + "\nCustomer စာ: " + message.text
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Order ထုတ်ယူခြင်း
        match_order = re.search(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', response_text)
        if match_order:
            product_key = match_order.group(1).strip()
            qty = int(match_order.group(2).strip())
            user_orders[message.chat.id] = {"product": product_key, "qty": qty}
            response_text = re.sub(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', '', response_text).strip()
            
        # Support Ticket
        if "[SUPPORT]" in response_text:
            response_text = response_text.replace("[SUPPORT]", "").strip()
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ **အကောင့်ပြဿနာ/Support:**\nCustomer ID: `{message.chat.id}`\nစာ: {message.text}\n\n*(ဤ Customer ထံသို့ ပြန်စာပို့ရန် အောက်ပါ Command ကို သုံးပါ)*\n`/reply {message.chat.id} `", parse_mode="Markdown")
            
        bot.reply_to(message, response_text)
        
    except Exception as e:
        # AI Error တက်ပါက သင့်ထံ ချက်ချင်း အကြောင်းကြားမည့်အပိုင်း (Fail-safe)
        error_msg = f"🔴 **Bot Error Alert:**\nCustomer (ID: `{message.chat.id}`) နှင့် စကားပြောနေစဉ် Error တက်သွားပါသည်။\n\n**Customer စာ:** {message.text}\n**အကြောင်းရင်း:** `{str(e)}`\n\n*(Customer ထံသို့ ကိုယ်တိုင်ဝင်ဖြေရန် အောက်ပါ Command ကို Copy ကူးပြီး ပို့ပါ)*\n`/reply {message.chat.id} ` "
        bot.send_message(ADMIN_CHAT_ID, error_msg, parse_mode="Markdown")
        
        # Customer ထံသို့ အကြောင်းကြားမည့်အပိုင်း
        bot.reply_to(message, "🙏 ဆာဗာ အနည်းငယ် ချို့ယွင်းနေလို့ပါ။ ကျွန်တော် Admin ကို တိုက်ရိုက် အကြောင်းကြားပေးထားပါတယ်။ ခဏလေးစောင့်ပေးပါခင်ဗျာ။ Admin မှ ဒီကနေတစ်ဆင့် ပြန်လည်ဖြေကြားပေးပါလိမ့်မယ်။")

# --- 5. ပြေစာ (Screenshot) လက်ခံသည့်အပိုင်း ---
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.chat.id
    username = message.from_user.username or message.from_user.first_name
    order_info = user_orders.get(user_id)
    
    if not order_info:
        bot.reply_to(message, "ကျေးဇူးပြု၍ ဝယ်ယူမည့် ပစ္စည်းအမည် နှင့် အရေအတွက်ကို အရင်ဆုံး ပြောပြပေးပါဗျ။ (ဥပမာ - Capcut Pro ကို ၂ ခု ဝယ်မယ်)")
        return

    product_key = order_info["product"]
    qty = order_info["qty"]
    
    markup = InlineKeyboardMarkup()
    btn_approve = InlineKeyboardButton("Approve (လက်ခံမည်)", callback_data=f"app|{user_id}")
    btn_reject = InlineKeyboardButton("Reject (ငြင်းပယ်မည်)", callback_data=f"rej|{user_id}")
    markup.add(btn_approve, btn_reject)
    
    admin_caption = f"📦 **ငွေလွှဲပြေစာ ဝင်ထားပါသည်**\nCustomer: @{username} (ID: `{user_id}`)\nဝယ်ယူသည့် Product ID: {product_key}\nအရေအတွက်: {qty} ခုစာ"
    bot.send_photo(ADMIN_CHAT_ID, message.photo[-1].file_id, caption=admin_caption, reply_markup=markup, parse_mode="Markdown")
    bot.reply_to(message, "ငွေလွှဲပြေစာ လက်ခံရရှိပါပြီဗျ။ Admin မှ စစ်ဆေးပြီးတာနဲ့ အကောင့်ကို ချက်ချင်း ပို့ပေးပါမယ်။")

# --- 6. Admin မှ လက်ခံ/ငြင်းပယ် လုပ်သည့်အပိုင်း (Google Sheet နှင့် ချိတ်ဆက်ဖြတ်တောက်ခြင်း) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data.split('|')
    action = data[0]
    customer_id = int(data[1])
    
    order_info = user_orders.get(customer_id)
    if not order_info:
        bot.send_message(ADMIN_CHAT_ID, "⚠️ Order အချက်အလက် ရှာမတွေ့တော့ပါ။ Customer ထံသို့ Manual စာပို့ပေးပါ။")
        return

    product_key = order_info["product"]
    qty = order_info["qty"]
    
    if action == "app":
        try:
            # Google Sheet ထဲမှ Product ကို သွားရှာခြင်း
            cell = sheet.find(product_key)
            row_idx = cell.row
            row_data = sheet.row_values(row_idx)
            
            # ဒေတာများ ဆွဲထုတ်ခြင်း (A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8)
            name = row_data[1] if len(row_data) > 1 else product_key
            total_slots = int(row_data[4]) if len(row_data) > 4 and str(row_data[4]).strip() else 0
            used_slots = int(row_data[5]) if len(row_data) > 5 and str(row_data[5]).strip() else 0
            account_details = row_data[6] if len(row_data) > 6 else "အချက်အလက် မရှိပါ"
            instructions = row_data[7] if len(row_data) > 7 else "Login ဝင်၍ အသုံးပြုပါ။"

            avail = total_slots - used_slots
            
            if avail >= qty:
                # Stock လုံလောက်လျှင် Database (Excel) တွင် Used_Slots ကို ပေါင်းထည့်မည်
                new_used = used_slots + qty
                sheet.update_cell(row_idx, 6, new_used) # Column F ကို Update လုပ်သည်
                
                # Customer ထံသို့ အကောင့်ပေးပို့ခြင်း
                success_msg = f"✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။ ဝယ်ယူအားပေးမှုအတွက် ကျေးဇူးတင်ပါတယ်ဗျ။\n\n**သင့်ရဲ့ အကောင့်အချက်အလက်:**\n`{account_details}`\n\n**အသုံးပြုနည်း:**\n{instructions}\n\nအဆင်မပြေတာရှိရင် ပြန်လည်မေးမြန်းနိုင်ပါတယ်ဗျ။"
                bot.send_message(customer_id, success_msg, parse_mode="Markdown")
                
                # Admin ထံသို့ စာရင်းရှင်းတမ်း ပြန်ပို့ခြင်း
                bot.edit_message_caption(f"✅ Customer ဆီသို့ အကောင့် ပို့ပေးပြီးပါပြီ။\nပစ္စည်း: {name}\nပေးလိုက်သော အရေအတွက်: {qty}\n\n📦 လက်ကျန်: **{avail - qty} ခု** ကျန်ပါမည်။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)
                del user_orders[customer_id]
            else:
                # Stock မလုံလောက်လျှင် Alert ပြမည်
                bot.edit_message_caption(f"⚠️ Stock မလုံလောက်တော့ပါ။ (လက်ကျန်: {avail} | Customer ဝယ်ယူမှု: {qty})\nCustomer ထံသို့ `/reply {customer_id} စာသား` ဖြင့် အကောင့်သစ် Manual သွားပို့ပေးပါ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)
                bot.send_message(customer_id, "✅ ငွေလွှဲမှု အောင်မြင်ပါတယ်။ သင့်အကောင့်ကို Admin မှ ခဏအတွင်း လာရောက်ပို့ပေးပါမည်။")
                
        except gspread.exceptions.CellNotFound:
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ Database ထဲတွင် Product ID '{product_key}' ကို ရှာမတွေ့ပါ။ Excel ဇယားကို ပြန်စစ်ပါ။")
        except Exception as e:
             bot.send_message(ADMIN_CHAT_ID, f"⚠️ Database ဖြတ်တောက်ရာတွင် Error တက်နေပါသည်။: {e}")

    elif action == "rej":
        bot.send_message(customer_id, "❌ ငွေလွှဲမှု မှားယွင်းနေပါသဖြင့် Admin မှ ပယ်ဖျက်လိုက်ပါတယ်။ ငွေလွှဲမှတ်တမ်းကို ပြန်စစ်ပေးပါဗျ။")
        bot.edit_message_caption("❌ ငြင်းပယ် (Reject) လုပ်ပြီးပါပြီ။", chat_id=ADMIN_CHAT_ID, message_id=call.message.message_id)

# --- ၂၄ နာရီ Web Server ---
app = Flask(__name__)
@app.route('/')
def home(): return "Google Sheets Bot is Running 24/7!"
def run_bot(): bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))