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
ADMIN_USERNAME = "@NyeinChanKoKo24" # သင့် Username ပြင်ထည့်ပါ

# --- Google Sheets ချိတ်ဆက်ခြင်း ---
SHEET_ID = '1kw8MLCSk9d_38Vmxet3BM4cwAqUL4Qy50diFNWeFw7o'
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Render က Secret File ကနေ credentials.json ကို လှမ်းဖတ်မည်
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

user_orders = {}

# Google Sheet မှ Data များကို ဆွဲယူခြင်း
def get_inventory_from_sheet():
    records = sheet.get_all_records()
    context = "လက်ရှိ ဆိုင်တွင်ရနိုင်သော ပစ္စည်းစာရင်းများ:\n"
    has_items = False
    
    for row in records:
        try:
            pid = row['ProductID']
            if not pid: continue
            name = row['Name']
            price = row['Price']
            type_val = str(row['Type']).lower()
            total_slots = int(row['Total_Slots']) if row['Total_Slots'] else 0
            used_slots = int(row['Used_Slots']) if row['Used_Slots'] else 0
            
            stock_count = total_slots - used_slots if type_val == 'shared' else total_slots
            stock_status = f"ရနိုင်သည် (လက်ကျန် {stock_count} ခု)" if stock_count > 0 else "ကုန်နေသည် (Out of stock)"
            
            context += f"- Product ID: [{pid}] | နာမည်: {name} | ဈေးနှုန်း: {price} ကျပ် | အခြေအနေ: {stock_status}\n"
            has_items = True
        except Exception as e:
            continue
            
    if not has_items:
        context += "လက်ရှိတွင် ပစ္စည်းများ မရှိသေးပါ။"
    return context, records

# --- Telegram Admin Commands ---
@bot.message_handler(commands=['stock'])
def admin_check_stock(message):
    if str(message.chat.id) != ADMIN_CHAT_ID: return
    context, _ = get_inventory_from_sheet()
    bot.reply_to(message, f"📊 **လက်ရှိ Database မှ စာရင်း:**\n\n{context}", parse_mode="Markdown")

@bot.message_handler(commands=['editprice'])
def admin_edit_price(message):
    if str(message.chat.id) != ADMIN_CHAT_ID: return
    try:
        parts = message.text.split(' ')
        pid = parts[1]
        new_price = parts[2]
        
        cell = sheet.find(pid)
        sheet.update_cell(cell.row, 4, new_price) # 4 is Price column (D)
        bot.reply_to(message, f"✅ `{pid}` ရဲ့ ဈေးနှုန်းကို {new_price} သို့ ပြောင်းလဲပြီးပါပြီ။", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, "❌ Command မှားနေပါတယ်။ Format: `/editprice ProductID ဈေးနှုန်းသစ်` (ဥပမာ - /editprice Capcut_01 12000)")

# --- AI Customer Service ---
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
        ၂။ Error ရှိပါက အဆုံးတွင် `[SUPPORT]` ဟု လျှို့ဝှက်ထည့်ပါ။
        ၃။ ဝယ်ယူရန်သေချာပါက KPay (09123456789 - U Ba) သို့ ငွေလွှဲပြေစာ တောင်းပါ။
        ၄။ (အရေးကြီး) ဝယ်ရန်သေချာပါက စာ၏အဆုံးတွင် `[ORDER: Product ID | အရေအတွက်]` ဟု အင်္ဂလိပ်ဂဏန်းသက်သက်ဖြင့်သာ မဖြစ်မနေ ထည့်ရေးပေးပါ။ 
        (ဥပမာ - [ORDER: Capcut_01 | 2])
        """
        
        prompt = system_prompt + "\nCustomer စာ: " + message.text
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Order Extract လုပ်ခြင်း (Regex Error ကင်းအောင် ပြင်ထားသည်)
        match_order = re.search(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', response_text)
        if match_order:
            product_key = match_order.group(1).strip()
            qty = int(match_order.group(2).strip())
            user_orders[message.chat.id] = {"product": product_key, "qty": qty}
            response_text = re.sub(r'\[ORDER:\s*(.*?)\s*\|\s*(\d+)\]', '', response_text).strip()
            
        if "[SUPPORT]" in response_text:
            response_text = response_text.replace("[SUPPORT]", "").strip()
            bot.send_message(ADMIN_CHAT_ID, f"⚠️ **Support လိုအပ်နေပါသည်:**\nCustomer ID: `{message.chat.id}`\nစာ: {message.text}")
            
        bot.reply_to(message, response_text)
    except Exception as e:
        bot.send_message(ADMIN_CHAT_ID, f"⚠️ **Bot Error တက်နေပါသည်:**\nCustomer နှင့် စကားပြောနေစဉ် Error တက်သွားပါသည်။\nError: {str(e)}")
        bot.reply_to(message, f"🙏 ဆာဗာ အနည်းငယ် ချို့ယွင်းနေပါတယ်။ Admin ({ADMIN_USERNAME}) ကို တိုက်ရိုက် ဆက်သွယ်ပေးပါခင်ဗျာ။")

# --- ၂၄ နာရီ Web Server ---
app = Flask(__name__)
@app.route('/')
def home(): return "Google Sheets Bot is Running!"
def run_bot(): bot.infinity_polling()

if __name__ == "__main__":
    t = threading.Thread(target=run_bot)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))