import os
import sys
import json
import subprocess
import time
import re
import logging
import asyncio
import threading
import requests
import html
from pathlib import Path
from flask import Flask, request, Response

def ensure_dependencies():
    required_pkgs = {
        "pip": "pip",
        "socks": "PySocks",
        "telegram": "python-telegram-bot",
        "flask": "flask",
        "requests": "requests"
    }
    for module_name, pkg_name in required_pkgs.items():
        try:
            __import__(module_name)
        except ImportError:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", pkg_name], check=True)
            except Exception:
                pass

ensure_dependencies()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

MAIN_BOT_TOKEN = "9083299742:AAGFQ3OAzLSe9LF3cZb3tyoptTfQt0MtgQU"
BOT_TOKEN = os.environ.get("BOT_TOKEN", MAIN_BOT_TOKEN)
ADMIN_ID = 8913966694

RAILWAY_URL = os.environ.get("RAILWAY_STATIC_URL", os.environ.get("RAILWAY_PUBLIC_DOMAIN", ""))
if RAILWAY_URL and not RAILWAY_URL.startswith("http"):
    RAILWAY_URL = f"https://{RAILWAY_URL}"

RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
VERCEL_URL = os.environ.get("VERCEL_URL", "")
GITHUB_API_TOKEN = os.environ.get("GITHUB_TOKEN", "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")

REQUIRED_CHANNELS = [
    {"id": -1003947388912, "link": "https://t.me/+3A7s7kVfaoMxYjM0", "name": "VANTOKRIUM TEAM KRALLIK"},
    {"id": -1004443368027, "link": "https://t.me/vantoriumchat", "name": "VANTORIUM TEAM SOHBET"}
]

EMOJI_IDS = {
    "👋": 5454390891466726015, "👍": 5456267427102858366, "⚠": 5879449820338330922,
    "👮‍♀": 5818678700274617758, "👮": 5818678700274617758,
    "✅": 5927037044365725425, "🛠": 5818705028424141605, "💬": 5819022220348886685,
    "⚙": 5929098607192969118, "🔘": 5960842268096073715, "👆": 5960842268096073715,
    "👇": 5960842268096073715, "👉": 5960842268096073715,
    "👤": 5352861489541714456, "⏳": 5337172996211648018, "⌛": 5337172996211648018,
    "📊": 5352877703043258544, "📈": 5352877703043258544, "🎁": 5879631269821685769,
    "🟢": 5879696093763084445, "🔴": 5463260230861202209, "💎": 5352838545826420397,
    "🗑": 5231339530249845638, "📥": 5386570059328010279, "🚫": 5796574861539155606,
    "↩": 5255799059762941032, "❌": 5420130255174145507, "😴": 5350513671439133456,
    "🧹": 4956591954088428445, "⚡": 4958479549265347295, "🛒": 5265132878395621818,
    "💰": 4958926882994127612, "➕": 4956507094124594921, "👑": 5217822164362739968,
    "⭐": 5438496463044752972, "📦": 5884479287171485878, "🎟": 6070989023684333046,
    "🎫": 5803295587709230597, "🏠": 4981247505908893312, "🏆": 5897617042374138003,
    "📃": 5257965810634202885, "📄": 5257965810634202885, "🎉": 6287474217424263219,
    "🔧": 5348239232852836489, "🆔": 5818885490065017876,
    "⏱": 6037268453759389862, "🕓": 6037268453759389862, "⏰": 6037268453759389862,
    "🥇": 5805346022276208487, "🥈": 6073465089510351822, "🥉": 5780636873558858577,
    "🔍": 5258274739041883702, "👥": 4909043075529048789, "👁": 5424892643760937442,
    "🌐": 5821388137443626414, "🤖": 5352861489541714456, "📁": 5257965810634202885,
    "▶": 4958479549265347295, "⏹": 5463260230861202209
}

class SensitiveFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        msg = msg.replace(MAIN_BOT_TOKEN, "GIZLENDI")
        msg = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:GIZLENDI', msg)
        msg = re.sub(r'github_pat_[A-Za-z0-9_]{50,}', 'GIZLENDI', msg)
        record.msg = msg
        record.args = ()
        return True

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addFilter(SensitiveFilter())

if os.path.exists("/data") and os.access("/data", os.W_OK):
    DATA_DIR = Path("/data")
else:
    DATA_DIR = Path("/tmp/data")

DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
MESSAGE_LOGS_FILE = DATA_DIR / "message_logs.json"
ORIGINAL_META_FILE = DATA_DIR / "original_meta.json"

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"users": {}, "premium": {}, "bot_codes": {}, "banned": []}

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(global_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

global_state = load_state()
if "banned" not in global_state: global_state["banned"] = []
running_procs = {}

application = Application.builder().token(BOT_TOKEN).updater(None).build()
bot_loop = asyncio.new_event_loop()

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run_coroutine_threadsafe(application.update_queue.put(update), bot_loop)
        return Response("OK", status=200)
    except Exception:
        return Response("Error", status=500)

def premium_button(text, callback_data=None, emoji="✅", style=None, url=None):
    kw = {"text": text}
    if url: kw["url"] = url
    else: kw["callback_data"] = callback_data
    if emoji in EMOJI_IDS: kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    # style parametresi telegram-bot kütüphanesinde hata yaptığından güvenle hariç tutuluyor
    return InlineKeyboardButton(**kw)

def parse_entities(text: str):
    entities = []
    for emoji_char, emoji_id in EMOJI_IDS.items():
        start = 0
        while True:
            idx = text.find(emoji_char, start)
            if idx == -1: break
            offset = len(text[:idx].encode('utf-16-le')) // 2
            length = len(emoji_char.encode('utf-16-le')) // 2
            entities.append(MessageEntity(type="custom_emoji", offset=offset, length=length, custom_emoji_id=str(emoji_id)))
            start = idx + len(emoji_char)
    return entities

def mask_token_in_text(text):
    if not text: return ""
    text = text.replace(MAIN_BOT_TOKEN, "GIZLENDI")
    text = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:GIZLENDI', text)
    text = re.sub(r'github_pat_[A-Za-z0-9_]{50,}', 'GIZLENDI', text)
    return text

def is_premium(user_id):
    return global_state["premium"].get(str(user_id), 0) > time.time()

def is_banned(user_id):
    return str(user_id) in global_state.get("banned", [])

def check_bot_limit(user_id):
    uid = str(user_id)
    count = sum(1 for k in running_procs if k.startswith(uid + "_"))
    return count < (10 if is_premium(uid) else 2)

def log_user_message(user, text):
    if not user or not text: return
    try:
        logs = []
        if MESSAGE_LOGS_FILE.exists():
            with open(MESSAGE_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        safe_text = mask_token_in_text(text) 
        log_entry = { 
            "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime()), 
            "id": user.id, 
            "name": user.first_name or "", 
            "username": user.username or "yok", 
            "text": safe_text 
        } 
        logs.append(log_entry) 
        if len(logs) > 500: logs = logs[-500:] 
        with open(MESSAGE_LOGS_FILE, "w", encoding="utf-8") as f: 
            json.dump(logs, f, ensure_ascii=False, indent=2) 
    except Exception: 
        pass 

def protect_main_bot_identity_and_connections():
    original_name = None
    while True: 
        try: 
            r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getWebhookInfo", timeout=10).json() 
            if r.get("ok"): 
                info = r["result"] 
                expected_url = f"{RAILWAY_URL}/webhook/{MAIN_BOT_TOKEN}" if RAILWAY_URL else (f"{RENDER_URL}/webhook/{MAIN_BOT_TOKEN}" if RENDER_URL else (f"https://{VERCEL_URL}/webhook/{MAIN_BOT_TOKEN}" if VERCEL_URL else "")) 
                current_url = info.get("url", "") 
                if expected_url and current_url != expected_url: 
                    requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setWebhook?url={expected_url}", timeout=10) 
                elif not expected_url and current_url: 
                    requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=10) 
            
            me_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getMe", timeout=10).json() 
            if me_r.get("ok"): 
                bot_user = me_r["result"] 
                current_name = bot_user.get("first_name", "") 
                if ORIGINAL_META_FILE.exists(): 
                    try: 
                        with open(ORIGINAL_META_FILE, "r", encoding="utf-8") as f: 
                            meta = json.load(f) 
                            original_name = meta.get("name", original_name) 
                    except: pass 
                if not original_name: 
                    original_name = current_name 
                    with open(ORIGINAL_META_FILE, "w", encoding="utf-8") as f: 
                        json.dump({"name": original_name}, f, ensure_ascii=False) 
                if current_name != original_name: 
                    requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setMyName", json={"name": original_name}, timeout=10) 
        except Exception: 
            pass 
        time.sleep(2) 

threading.Thread(target=protect_main_bot_identity_and_connections, daemon=True).start()

async def check_membership(user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True

async def send_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for ch in REQUIRED_CHANNELS:
        keyboard.append([premium_button(f"Katıl: {ch['name']}", emoji="📢", style="primary", url=ch["link"])])
    keyboard.append([premium_button("Kontrol Et", "check_join", "✅", "success")])

    text = "Zorunlu Kanal Üyeliği\n\nLütfen kanallara katılın ve kontrol et butonuna basın." 
    reply_markup = InlineKeyboardMarkup(keyboard) 
    if update.callback_query: 
        try: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML") 
        except: pass 
    else: 
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML") 

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await check_membership(q.from_user.id):
        await show_main_menu(update, context)
    else:
        await q.answer("Lütfen tüm kanallara katılın.", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot", build_cmd="", start_cmd=""):
    uid = str(user_id)
    proc_key = f"{uid}_{int(time.time())}"
    bot_dir = DATA_DIR / "user_bots" / uid / proc_key
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"

    code_content = code_content.replace(MAIN_BOT_TOKEN, "9000000000:AABBBCCDDEEFFGGHHIIJJKKLMMNNOOPPQQRR") 
    with open(script_path, "w", encoding="utf-8") as f: 
        f.write(code_content) 
    with open(log_path, "w", encoding="utf-8") as lf: 
        if build_cmd.strip(): 
            try: subprocess.run(build_cmd, shell=True, cwd=str(bot_dir), capture_output=True, text=True, timeout=300) 
            except Exception: pass 
    log_file = open(log_path, "a", encoding="utf-8") 
    env = {**os.environ, "BOT_TOKEN": bot_token} 
    if start_cmd.strip(): 
        proc = subprocess.Popen(start_cmd, shell=True, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env) 
    else: 
        proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env) 
    running_procs[proc_key] = { 
        "proc": proc, 
        "log_path": str(log_path), 
        "token": "GİZLİ", 
        "started": time.time(), 
        "user_id": uid, 
        "name": bot_name, 
        "build_cmd": build_cmd, 
        "start_cmd": start_cmd, 
        "script_path": str(script_path) 
    } 
    return proc_key 

def stop_bot_process(proc_key):
    if proc_key in running_procs:
        proc = running_procs[proc_key]["proc"]
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except: proc.kill()
        del running_procs[proc_key]
        return True
    return False

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        text = "Hesabınız yasaklandı."
        entities = parse_entities(text)
        if update.message: await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try: await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except: pass
        return

    uid = str(user.id) 
    global_state["users"][uid] = {"username": user.username or "", "first_name": user.first_name or ""} 
    save_state() 
    keyboard = [] 
    if user.id == ADMIN_ID: 
        keyboard.append([premium_button("Admin Paneli", "admin_panel", "👮‍♀", "primary")]) 
    keyboard.append([premium_button("GitHub ile Başlat", "github_start", "🌐", "success")]) 
    keyboard.append([premium_button("Botlarım", "my_bots", "🤖", "success")]) 
    keyboard.append([premium_button("Premium Al", "buy_premium", "💎", "primary")]) 
    keyboard.append([premium_button("Pip Yükleyici", "pip_menu", "📦", "primary")]) 
    
    text = f"Merhaba {user.first_name}, dosyanızı göndererek botunuzu çalıştırabilirsiniz." 
    reply_markup = InlineKeyboardMarkup(keyboard) 
    entities = parse_entities(text) 
    if update.message: 
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 
    elif update.callback_query: 
        try: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 
        except: pass 

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await show_main_menu(update, context)
        return
    if not await check_membership(user_id):
        await send_join_message(update, context)
        return
    await show_main_menu(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return

    text = "Admin Paneli" 
    keyboard = [ 
        [premium_button("Kullanıcı Listesi", "user_list", "👥", "primary"), premium_button("Mesaj Logları", "message_logs", "💬", "success")], 
        [premium_button("Ban At", "ban_user", "🚫", "danger"), premium_button("Ban Kaldır", "unban_user", "✅", "success")], 
        [premium_button("Duyuru", "broadcast", "📢", "primary")], 
        [premium_button("Premium Ver", "give_premium", "💎", "success"), premium_button("Premium Al", "revoke_premium", "❌", "danger")], 
        [premium_button("Çalışan Botlar", "file_list", "📁", "primary")], 
        [premium_button("Geri", "back_start", "↩", "danger")] 
    ] 
    entities = parse_entities(text) 
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML") 
    except: pass 

async def message_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "Mesaj Logları\n\n"
    if not MESSAGE_LOGS_FILE.exists():
        text += "Kayıt yok."
    else:
        try:
            with open(MESSAGE_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not logs:
                    text += "Kayıt bulunamadı."
                else:
                    for l in logs[-25:]:
                        text += f"{l['time']} - {l['name']} (@{l['username']}) [{l['id']}]: {html.escape(l['text'])}\n"
        except Exception:
            text += "Okunamadı."
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "Kullanıcı Listesi\n\n"
    for uid, info in list(global_state["users"].items())[:35]:
        text += f"{uid} - @{info.get('username','yok')}\n"
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def file_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "Aktif Botlar\n\n"
    for i, (pk, info) in enumerate(running_procs.items(), 1):
        text += f"{i}. {info['name']} - Token: GİZLİ\n"
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def ban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_ban_id"] = True
    await q.edit_message_text("Yasaklanacak ID girin:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def unban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_unban_id"] = True
    await q.edit_message_text("Yasağı kaldırılacak ID girin:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_broadcast"] = True
    await q.edit_message_text("Duyuru mesajını yazın:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.strip()
    context.user_data["awaiting_broadcast"] = False
    for uid in global_state["users"]:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg_text)
        except:
            pass
    await update.message.reply_text("Duyuru tamamlandı.", reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]))

async def give_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_premium_id"] = True
    await q.edit_message_text("Premium verilecek ID girin:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def premium_duration_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    context.user_data["premium_target_id"] = user_id
    keyboard = [
        [premium_button("1 Hafta", "give_prem_7", "⭐", "primary")],
        [premium_button("1 Ay", "give_prem_30", "⭐", "success")],
        [premium_button("1 Yıl", "give_prem_365", "💎", "primary")],
        [premium_button("İptal", "admin_panel", "❌", "danger")]
    ]
    await update.callback_query.edit_message_text("Süre seçin:", reply_markup=InlineKeyboardMarkup(keyboard))

async def execute_give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE, days):
    q = update.callback_query; await q.answer()
    target_id = context.user_data.get("premium_target_id")
    if not target_id: return
    global_state["premium"][target_id] = time.time() + days * 86400
    save_state()
    await q.edit_message_text("Premium verildi.", reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]))

async def revoke_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_revoke_id"] = True
    await q.edit_message_text("Premiumu silinecek ID girin:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    if not bl:
        await q.edit_message_text("Bot bulunamadı.", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]))
        return
    keyboard = []
    for pk in bl:
        info = running_procs[pk]
        keyboard.append([premium_button(f"Log: {info['name']}", f"log_{pk}", "📃", "primary")])
        keyboard.append([premium_button(f"Sil: {info['name']}", f"del_{pk}", "🗑", "danger")])
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    await q.edit_message_text("Botlarınız:", reply_markup=InlineKeyboardMarkup(keyboard))

async def pip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_pip_package"] = True
    await q.edit_message_text("Yüklenecek paket adını yazın:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]))

def install_pip_background(package_name, chat_id, context):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package_name], check=True)
        asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"{package_name} yüklendi."), bot_loop)
    except Exception:
        pass

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs:
        stop_bot_process(pk)
    await q.edit_message_text("Bot silindi.", reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]))

async def github_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_github_url"] = True
    await q.edit_message_text("GitHub depo URL adresini gönderin:", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]))

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_github_url"): return
    context.user_data["awaiting_github_url"] = False
    await update.message.reply_text("İşleniyor...")

async def handle_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (update.message.text or "").strip()
    if user: log_user_message(user, text)

    ud = context.user_data 
    if ud.get("awaiting_ban_id"): 
        ud["awaiting_ban_id"] = False 
        global_state["banned"].append(text) 
        save_state() 
        await update.message.reply_text("Banlandı.") 
        return 
    if ud.get("awaiting_unban_id"): 
        ud["awaiting_unban_id"] = False 
        if text in global_state["banned"]: 
            global_state["banned"].remove(text) 
            save_state() 
        await update.message.reply_text("Ban kaldırıldı.") 
        return 
    if ud.get("awaiting_broadcast"): 
        await do_broadcast(update, context) 
        return 
    if ud.get("awaiting_premium_id"): 
        ud["awaiting_premium_id"] = False 
        await premium_duration_menu(update, context, text) 
        return 
    if ud.get("awaiting_revoke_id"): 
        ud["awaiting_revoke_id"] = False 
        global_state["premium"].pop(text, None) 
        save_state() 
        await update.message.reply_text("Premium alındı.") 
        return 
    if ud.get("awaiting_github_url"): 
        await handle_github_url(update, context) 
        return 
    if ud.get("awaiting_pip_package"): 
        ud["awaiting_pip_package"] = False 
        threading.Thread(target=install_pip_background, args=(text, update.effective_chat.id, context)).start() 
        return 

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; doc = update.message.document
    if not doc.file_name.endswith(".py"): return
    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")

    code = code.replace(MAIN_BOT_TOKEN, "GIZLENDI") 
    tm = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code) 
    if not tm: return 
    token = tm.group(1) 
    bname = doc.file_name.replace(".py", "") 
    start_bot_process(str(user.id), token, code, bname) 
    await update.message.reply_text("Bot başlatıldı.") 

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    keyboard = [
        [premium_button("1 Hafta", "premium_7", "⭐", "primary")],
        [premium_button("1 Ay", "premium_30", "⭐", "success")],
        [premium_button("1 Yıl", "premium_365", "💎", "primary")],
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    await q.edit_message_text("Paket seçin:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    await context.bot.send_invoice(chat_id=q.from_user.id, title="Premium", description="Premium üyelik", payload=f"premium_{uid}_{days}", provider_token="", currency="XTR", prices=[{"label": "Premium", "amount": stars}])

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text("Ödeme başarılı.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs: return
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-3000:]
    except: content = "Okunamadı."
    await q.edit_message_text(f"Log:\n\n{html.escape(content)}", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]))

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("stop_", "")
    stop_bot_process(pk)
    await q.edit_message_text("Durduruldu.", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "primary")]]))

application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
application.add_handler(CallbackQueryHandler(message_logs_view, pattern="^message_logs$"))
application.add_handler(CallbackQueryHandler(ban_user_menu, pattern="^ban_user$"))
application.add_handler(CallbackQueryHandler(unban_user_menu, pattern="^unban_user$"))
application.add_handler(CallbackQueryHandler(broadcast_menu, pattern="^broadcast$"))
application.add_handler(CallbackQueryHandler(give_premium_menu, pattern="^give_premium$"))
application.add_handler(CallbackQueryHandler(revoke_premium_menu, pattern="^revoke_premium$"))
application.add_handler(CallbackQueryHandler(file_list, pattern="^file_list$"))
application.add_handler(CallbackQueryHandler(my_bots, pattern="^my_bots$"))
application.add_handler(CallbackQueryHandler(pip_menu, pattern="^pip_menu$"))
application.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_premium$"))
application.add_handler(CallbackQueryHandler(handle_premium_purchase, pattern="^premium_"))

async def give_prem_7(u, c): await execute_give_premium(u, c, 7)
async def give_prem_30(u, c): await execute_give_premium(u, c, 30)
async def give_prem_365(u, c): await execute_give_premium(u, c, 365)

application.add_handler(CallbackQueryHandler(give_prem_7, pattern="^give_prem_7$"))
application.add_handler(CallbackQueryHandler(give_prem_30, pattern="^give_prem_30$"))
application.add_handler(CallbackQueryHandler(give_prem_365, pattern="^give_prem_365$"))

application.add_handler(CallbackQueryHandler(github_start, pattern="^github_start$"))
application.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
application.add_handler(CallbackQueryHandler(stop_bot, pattern="^stop_"))
application.add_handler(CallbackQueryHandler(delete_bot, pattern="^del_"))
application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_start$"))

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_router))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

def run_bot_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    loop.run_forever()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot_async_loop, args=(bot_loop,), daemon=True)
    bot_thread.start()

    active_url = RAILWAY_URL or RENDER_URL or (f"https://{VERCEL_URL}" if VERCEL_URL else "")
    if active_url: 
        try: 
            requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={active_url}/webhook/{BOT_TOKEN}") 
        except: 
            pass

    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
