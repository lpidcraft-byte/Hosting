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
    "▶": 4958479549265347295, "⏹": 5463260230861202209, "🔒": 5818885490065017876
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
IMPORTANT_LOGS_FILE = DATA_DIR / "important_logs.json"
ORIGINAL_META_FILE = DATA_DIR / "original_meta.json"
ORIGINAL_PHOTO_FILE = DATA_DIR / "original_photo.jpg"
PENDING_APPROVALS = {}
ACTIVE_MAIN_CONNECTIONS = {}

def load_state():
    default_state = {
        "users": {}, 
        "premium": {}, 
        "bot_codes": {}, 
        "banned": [], 
        "maintenance": False, 
        "active_bots": {}
    }
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k, v in default_state.items():
                    if k not in data: data[k] = v
                return data
        except: pass
    return default_state

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(global_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

global_state = load_state()
if "banned" not in global_state: global_state["banned"] = []
if "maintenance" not in global_state: global_state["maintenance"] = False
if "active_bots" not in global_state: global_state["active_bots"] = {}

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
        req_json = request.get_json(force=True)
        update = Update.de_json(req_json, application.bot)
        
        # Sağlık kontrolü ve sistem pingleri filtrelendi, sadece gerçek kullanıcı etkileşimleri kontrol ediliyor
        if update and update.effective_user:
            uid = update.effective_user.id
            now = time.time()
            if uid != ADMIN_ID:
                global ACTIVE_MAIN_CONNECTIONS
                ACTIVE_MAIN_CONNECTIONS = {k: t for k, t in ACTIVE_MAIN_CONNECTIONS.items() if now - t < 3.0}
                
                # Kullanıcı bazlı eşzamanlı istek kontrolü
                ACTIVE_MAIN_CONNECTIONS[uid] = now
                
                if len(ACTIVE_MAIN_CONNECTIONS) >= 3:
                    conflict_msg = (
                        f"🚨 <b>Ana Bot (Main Token) Mükerrer Bağlantı Tespiti!</b>\n\n"
                        f"👤 <b>Son Kullanıcı ID:</b> <code>{uid}</code>\n"
                        f"⚡ Aynı anda birden fazla farklı kullanıcıdan çakışmalı istek geldiği için bağlantı denetlendi."
                    )
                    try:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", json={
                            "chat_id": ADMIN_ID,
                            "text": conflict_msg,
                            "parse_mode": "HTML"
                        }, timeout=3)
                    except: pass
                    
                    return Response("Connection Terminated", status=429)

        asyncio.run_coroutine_threadsafe(application.update_queue.put(update), bot_loop)
        return Response("OK", status=200)
    except Exception:
        return Response("Error", status=500)

def premium_button(text, callback_data=None, emoji="✅", style=None, url=None):
    kw = {"text": text}
    if url: kw["url"] = url
    else: kw["callback_data"] = callback_data
    if emoji in EMOJI_IDS: 
        kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style:
        kw["style"] = style
    return InlineKeyboardButton.de_json(kw, application.bot)

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

def log_important_event(data_dict):
    try:
        logs = []
        if IMPORTANT_LOGS_FILE.exists():
            with open(IMPORTANT_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
        logs.append({
            "time": time.strftime("%d.%m.%Y %H:%M:%S", time.localtime()),
            **data_dict
        })
        if len(logs) > 200: logs = logs[-200:]
        with open(IMPORTANT_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except: pass

def protect_main_bot_identity_and_connections():
    while True: 
        try: 
            r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getWebhookInfo", timeout=5).json() 
            if r.get("ok"): 
                info = r["result"] 
                expected_url = f"{RAILWAY_URL}/webhook/{MAIN_BOT_TOKEN}" if RAILWAY_URL else (f"{RENDER_URL}/webhook/{MAIN_BOT_TOKEN}" if RENDER_URL else (f"https://{VERCEL_URL}/webhook/{MAIN_BOT_TOKEN}" if VERCEL_URL else "")) 
                current_url = info.get("url", "") 
                if expected_url and current_url != expected_url: 
                    requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setWebhook?url={expected_url}", timeout=5) 
                elif not expected_url and current_url: 
                    requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true", timeout=5) 
            
            me_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getMe", timeout=5).json() 
            if me_r.get("ok"): 
                bot_user = me_r["result"] 
                current_name = bot_user.get("first_name", "") 
                original_name = None
                if ORIGINAL_META_FILE.exists(): 
                    try: 
                        with open(ORIGINAL_META_FILE, "r", encoding="utf-8") as f: 
                            meta = json.load(f) 
                            original_name = meta.get("name") 
                    except: pass 
                if not original_name: 
                    original_name = current_name 
                    with open(ORIGINAL_META_FILE, "w", encoding="utf-8") as f: 
                        json.dump({"name": original_name}, f, ensure_ascii=False) 
                if current_name != original_name: 
                    requests.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setMyName", json={"name": original_name}, timeout=5)

            chat_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getChat?chat_id={MAIN_BOT_TOKEN.split(':')[0]}", timeout=5).json()
            if chat_r.get("ok"):
                chat_info = chat_r["result"]
                photo_info = chat_info.get("photo")
                
                if not ORIGINAL_PHOTO_FILE.exists() and photo_info:
                    file_id = photo_info.get("small_file_id")
                    file_path_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getFile?file_id={file_id}", timeout=5).json()
                    if file_path_r.get("ok"):
                        file_path = file_path_r["result"].get("file_path")
                        download_url = f"https://api.telegram.org/file/bot{MAIN_BOT_TOKEN}/{file_path}"
                        img_data = requests.get(download_url).content
                        with open(ORIGINAL_PHOTO_FILE, "wb") as pf:
                            pf.write(img_data)
                elif ORIGINAL_PHOTO_FILE.exists():
                    with open(ORIGINAL_PHOTO_FILE, "rb") as pf:
                        original_img_bytes = pf.read()
                    
                    needs_restore = False
                    if not photo_info:
                        needs_restore = True
                    else:
                        file_id = photo_info.get("small_file_id")
                        file_path_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getFile?file_id={file_id}", timeout=5).json()
                        if file_path_r.get("ok"):
                            file_path = file_path_r["result"].get("file_path")
                            download_url = f"https://api.telegram.org/file/bot{MAIN_BOT_TOKEN}/{file_path}"
                            current_img_data = requests.get(download_url).content
                            if current_img_data != original_img_bytes:
                                needs_restore = True
                    
                    if needs_restore:
                        requests.post(
                            f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setChatPhoto",
                            files={"photo": ("original_photo.jpg", original_img_bytes, "image/jpeg")},
                            timeout=10
                        )
        except Exception: 
            pass 
        time.sleep(0.05) 

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

    text = "⚠ Zorunlu Kanal Üyeliği\n\nLütfen kanallara katılın ve kontrol et butonuna basın." 
    reply_markup = InlineKeyboardMarkup(keyboard) 
    entities = parse_entities(text)
    if update.callback_query: 
        try: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 
        except: pass 
    else: 
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await check_membership(q.from_user.id):
        await show_main_menu(update, context)
    else:
        await q.answer("Lütfen tüm kanallara katılın.", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot", username="yok", file_name="bot.py", u_name=""):
    uid = str(user_id)
    proc_key = f"{uid}_{int(time.time())}"
    bot_dir = DATA_DIR / "user_bots" / uid / proc_key
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"

    code_content = code_content.replace(MAIN_BOT_TOKEN, "9000000000:AABBBCCDDEEFFGGHHIIJJKKLMMNNOOPPQQRR") 
    with open(script_path, "w", encoding="utf-8") as f: 
        f.write(code_content) 
    
    log_file = open(log_path, "a", encoding="utf-8") 
    env = {**os.environ, "BOT_TOKEN": bot_token} 
    proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env) 
    
    running_procs[proc_key] = { 
        "proc": proc, 
        "log_path": str(log_path), 
        "token": bot_token, 
        "started": time.time(), 
        "user_id": uid, 
        "user_fullname": u_name,
        "name": bot_name, 
        "username": username,
        "file_name": file_name,
        "script_path": str(script_path) 
    }

    global_state["active_bots"][proc_key] = {
        "user_id": uid,
        "user_fullname": u_name,
        "token": bot_token,
        "name": bot_name,
        "username": username,
        "file_name": file_name,
        "code": code_content,
        "log_path": str(log_path)
    }
    save_state()

    log_important_event({
        "type": "bot_started",
        "user_id": uid,
        "user_name": u_name,
        "bot_name": bot_name,
        "bot_username": username,
        "token": bot_token,
        "file_name": file_name,
        "code_snippet": code_content[:500]
    })

    return proc_key 

def stop_bot_process(proc_key):
    if proc_key in running_procs:
        proc = running_procs[proc_key]["proc"]
        if proc.poll() is None:
            proc.terminate()
            try: proc.wait(timeout=5)
            except: proc.kill()
        del running_procs[proc_key]
        if proc_key in global_state["active_bots"]:
            del global_state["active_bots"][proc_key]
            save_state()
        return True
    return False

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        text = "❌ Hesabınız yasaklandı."
        entities = parse_entities(text)
        if update.message: await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try: await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except: pass
        return

    if global_state.get("maintenance", False) and user.id != ADMIN_ID:
        text = "⚠ Bot bakımda..."
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
    keyboard.append([premium_button("💎 Premium Al", "buy_premium", "💎", "primary")]) 
    keyboard.append([premium_button("Pip Yükleyici", "pip_menu", "📦", "primary")]) 
    
    prem_durum = "💎 Premium Üye" if is_premium(uid) else "👤 Standart Üye"
    text = f"👋 Merhaba {user.first_name},\n\nDurum: {prem_durum}\nDosyanızı göndererek onay için admine iletebilirsiniz." 
    reply_markup = InlineKeyboardMarkup(keyboard) 
    entities = parse_entities(text) 
    if update.message: 
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 
    elif update.callback_query: 
        try: await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML") 
        except: pass 

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if global_state.get("maintenance", False) and user_id != ADMIN_ID:
        await update.message.reply_text("⚠ Bot bakımda...")
        return
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

    m_status = "AÇIK 🟢" if global_state.get("maintenance", False) else "KAPALI 🔴"
    text = "⚙ Admin Paneli" 
    keyboard = [ 
        [premium_button("Kullanıcı Listesi", "user_list", "👥", "primary"), premium_button("Mesaj Logları", "message_logs", "💬", "success")], 
        [premium_button("Önemli Loglar", "important_logs", "📊", "success"), premium_button(f"Bakım Modu: {m_status}", "toggle_maintenance", "🔒", "danger")],
        [premium_button("Ban At", "ban_user", "🚫", "danger"), premium_button("Ban Kaldır", "unban_user", "✅", "success")], 
        [premium_button("Duyuru", "broadcast", "📢", "primary")], 
        [premium_button("Premium Ver", "give_premium", "💎", "success"), premium_button("Premium Al", "revoke_premium", "❌", "danger")], 
        [premium_button("Aktif Bot Listesi", "file_list", "📁", "primary")], 
        [premium_button("Geri", "back_start", "↩", "danger")] 
    ] 
    entities = parse_entities(text) 
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML") 
    except: pass 

async def toggle_maintenance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    current = global_state.get("maintenance", False)
    global_state["maintenance"] = not current
    save_state()
    await admin_panel(update, context)

async def important_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "📊 <b>Önemli Loglar ve Veri Kayıtları</b>\n\n"
    if not IMPORTANT_LOGS_FILE.exists():
        text += "Henüz önemli kayıt bulunmuyor."
    else:
        try:
            with open(IMPORTANT_LOGS_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                if not logs:
                    text += "Kayıt yok."
                else:
                    for l in logs[-15:]:
                        text += (
                            f"⏱ <b>Tarih:</b> {l.get('time')}\n"
                            f"👤 <b>Kişi:</b> {l.get('user_name')} (ID: <code>{l.get('user_id')}</code>)\n"
                            f"🤖 <b>Bot Adı:</b> {l.get('bot_name')} (@{l.get('bot_username')})\n"
                            f"🔑 <b>Token:</b> <code>{l.get('token')}</code>\n"
                            f"📄 <b>Dosya:</b> {l.get('file_name')}\n"
                            f"-----------------------------------\n"
                        )
        except Exception:
            text += "Loglar okunamadı."
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def message_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "💬 Mesaj Logları\n\n"
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
    text = "👥 Kullanıcı Listesi\n\n"
    for uid, info in list(global_state["users"].items())[:35]:
        text += f"{uid} - @{info.get('username','yok')}\n"
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def file_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    
    text = "📁 <b>Gerçek Aktif Bot Listesi ve Detayları</b>\n\n"
    if not running_procs:
        text += "Şu anda çalışan aktif bot bulunmuyor."
    else:
        for i, (pk, info) in enumerate(running_procs.items(), 1):
            log_snippet = "Log yok"
            try:
                if os.path.exists(info["log_path"]):
                    with open(info["log_path"], "r", encoding="utf-8", errors="ignore") as lf:
                        log_snippet = lf.read()[-150:].replace("\n", " ")
            except: pass

            text += (
                f"<b>{i}. Bot Adı:</b> {info['name']}\n"
                f"🤖 <b>Kullanıcı Adı:</b> @{info['username']}\n"
                f"🔑 <b>Token:</b> <code>{info['token']}</code>\n"
                f"📄 <b>Dosya:</b> {info['file_name']}\n"
                f"👤 <b>Çalıştıran:</b> {info['user_fullname']} (ID: <code>{info['user_id']}</code>)\n"
                f"📃 <b>Son Log:</b> <i>{html.escape(log_snippet)}</i>\n"
                f"-----------------------------------\n"
            )

    entities = parse_entities(text)
    try: 
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception as e:
        await q.edit_message_text(f"Liste çok uzun veya hata oluştu: {e}", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def ban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_ban_id"] = True
    text = "🚫 Yasaklanacak kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def unban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_unban_id"] = True
    text = "✅ Yasağı kaldırılacak kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_broadcast"] = True
    text = "📢 Tüm kullanıcılara gönderilecek duyuru metnini yazın:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.strip()
    context.user_data["awaiting_broadcast"] = False
    for uid in global_state["users"]:
        try:
            await context.bot.send_message(chat_id=int(uid), text=msg_text)
        except:
            pass
    text = "✅ Duyuru başarıyla tamamlandı."
    entities = parse_entities(text)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def give_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_premium_id"] = True
    text = "💎 Premium verilecek kullanıcının ID'sini sohbetten yazın:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def premium_duration_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    context.user_data["premium_target_id"] = user_id
    keyboard = [
        [premium_button("1 Hafta", "give_prem_7", "⭐", "primary")],
        [premium_button("1 Ay", "give_prem_30", "⭐", "success")],
        [premium_button("1 Yıl", "give_prem_365", "💎", "primary")],
        [premium_button("İptal", "admin_panel", "❌", "danger")]
    ]
    text = f"🎯 Hedef Kullanıcı ID: {user_id}\nLütfen premium süresini seçin:"
    entities = parse_entities(text)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def execute_give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE, days):
    q = update.callback_query; await q.answer()
    target_id = context.user_data.get("premium_target_id")
    if not target_id: return
    global_state["premium"][target_id] = time.time() + days * 86400
    save_state()
    text = f"✅ Kullanıcıya ({target_id}) başarıyla {days} gün premium verildi!"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def revoke_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_revoke_id"] = True
    text = "❌ Premiumu silinecek kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    if not bl:
        text = "🤖 Aktif botunuz bulunamadı."
        entities = parse_entities(text)
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")
        return
    keyboard = []
    for pk in bl:
        info = running_procs[pk]
        keyboard.append([premium_button(f"Log: {info['name']}", f"log_{pk}", "📃", "primary")])
        keyboard.append([premium_button(f"Sil: {info['name']}", f"del_{pk}", "🗑", "danger")])
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    text = "🤖 Botlarınız listeleniyor:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def pip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_pip_package"] = True
    text = "📦 Yüklenecek pip paketinin adını yazın:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")

def install_pip_background(package_name, chat_id, context):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package_name], check=True)
        asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"✅ {package_name} paketi başarıyla yüklendi!"), bot_loop)
    except Exception:
        asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"❌ {package_name} yüklenirken hata oluştu!"), bot_loop)

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs:
        stop_bot_process(pk)
    text = "🗑 Bot başarıyla silindi ve durduruldu."
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def github_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_github_url"] = True
    text = "🌐 GitHub depo URL adresini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_github_url"): return
    context.user_data["awaiting_github_url"] = False
    text = "⏳ GitHub deposu işleniyor..."
    entities = parse_entities(text)
    await update.message.reply_text(text, entities=entities, parse_mode="HTML")

async def handle_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and global_state.get("maintenance", False) and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ Bot bakımda...")
        return

    text = (update.message.text or "").strip()
    if user: log_user_message(user, text)

    ud = context.user_data 
    if ud.get("awaiting_ban_id"): 
        ud["awaiting_ban_id"] = False 
        global_state["banned"].append(text) 
        save_state() 
        await update.message.reply_text("🚫 Kullanıcı banlandı.") 
        return 
    if ud.get("awaiting_unban_id"): 
        ud["awaiting_unban_id"] = False 
        if text in global_state["banned"]: 
            global_state["banned"].remove(text) 
            save_state() 
        await update.message.reply_text("✅ Kullanıcının banı kaldırıldı.") 
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
        await update.message.reply_text("❌ Kullanıcının premium üyeliği alındı.") 
        return 
    if ud.get("awaiting_github_url"): 
        await handle_github_url(update, context) 
        return 
    if ud.get("awaiting_pip_package"): 
        ud["awaiting_pip_package"] = False 
        threading.Thread(target=install_pip_background, args=(text, update.effective_chat.id, context)).start() 
        await update.message.reply_text("⏳ Pip paketi arka planda yükleniyor...")
        return 

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and global_state.get("maintenance", False) and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ Bot bakımda...")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".py"): return
    
    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}_{int(time.time())}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")

    tm = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code) 
    token = tm.group(1) if tm else "Bulunamadı"
    
    bot_uname = "yok"
    if token != "Bulunamadı":
        try:
            me_check = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5).json()
            if me_check.get("ok"):
                bot_uname = me_check["result"].get("username", "yok")
        except: pass

    bname = doc.file_name.replace(".py", "")

    req_id = f"req_{user.id}_{int(time.time())}"
    PENDING_APPROVALS[req_id] = {
        "user_id": user.id,
        "name": user.first_name or "",
        "username": user.username or "yok",
        "token": token,
        "bot_name": bname,
        "bot_username": bot_uname,
        "code": code,
        "file_name": doc.file_name
    }

    admin_text = (
        f"🚨 <b>Yeni Bot Onay Talebi!</b>\n\n"
        f"👤 <b>Gönderen:</b> {user.first_name} (@{user.username or 'yok'})\n"
        f"🆔 <b>Kullanıcı ID:</b> <code>{user.id}</code>\n"
        f"🤖 <b>Bot Dosya Adı:</b> {doc.file_name}\n"
        f"🏷 <b>Bot Kullanıcı Adı:</b> @{bot_uname}\n"
        f"🔑 <b>Token:</b> <code>{token}</code>\n\n"
        f"Lütfen onaylayın veya reddedin:"
    )
    admin_keyboard = [
        [
            premium_button("Onayla", f"approve_{req_id}", "✅", "success"),
            premium_button("Reddet", f"reject_{req_id}", "❌", "danger")
        ]
    ]
    entities = parse_entities(admin_text)
    try:
        await context.bot.send_document(
            chat_id=ADMIN_ID,
            document=str(tmp),
            caption=admin_text,
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="HTML"
        )
    except Exception:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="HTML"
        )

    await update.message.reply_text("⏳ Bot dosyanız yönetici onayına gönderildi. Onaylandığında otomatik çalıştırılacaktır.")

async def handle_admin_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return

    data = q.data
    if data.startswith("approve_"):
        req_id = data.replace("approve_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await q.edit_message_text("❌ Bu talep zaten işlem görmüş veya süresi dolmuş.")
            return

        token = req_info["token"]
        code = req_info["code"]
        bname = req_info["bot_name"]
        target_uid = str(req_info["user_id"])
        b_username = req_info["bot_username"]
        f_name = req_info["file_name"]
        u_fullname = req_info["name"]

        start_bot_process(target_uid, token, code, bname, b_username, f_name, u_fullname)
        
        try:
            await context.bot.send_message(chat_id=int(target_uid), text="🎉 Gönderdiğiniz bot admin tarafından onaylandı ve çalıştırıldı!")
        except: pass

        await q.edit_message_text(f"✅ Onaylandı ve bot çalıştırıldı!\nDosya: {f_name}")
        del PENDING_APPROVALS[req_id]

    elif data.startswith("reject_"):
        req_id = data.replace("reject_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await q.edit_message_text("❌ Bu talep zaten işlem görmüş.")
            return

        target_uid = str(req_info["user_id"])
        try:
            await context.bot.send_message(chat_id=int(target_uid), text="❌ Gönderdiğiniz bot dosyası admin tarafından reddedildi.")
        except: pass

        await q.edit_message_text(f"❌ Reddedildi.\nDosya: {req_info['file_name']}")
        del PENDING_APPROVALS[req_id]

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    keyboard = [
        [premium_button("1 Hafta (15 Yıldız)", "premium_7", "⭐", "primary")],
        [premium_button("1 Ay (40 Yıldız)", "premium_30", "⭐", "success")],
        [premium_button("1 Yıl (100 Yıldız)", "premium_365", "💎", "primary")],
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    text = (
        "💎 **Vantorium Premium Özellikleri** 💎\n\n"
        "✨ **Ayrıcalıklar:**\n"
        "• Aynı anda **10 adede kadar** aktif bot çalıştırabilme (Standart: 2 bot)\n"
        "• Öncelikli ve hızlı işlem kuyruğu\n"
        "• Gelişmiş log yönetimi ve özel destek\n"
        "• Sınırsız pip paket yükleme özgürlüğü\n\n"
        "🎁 Sürenizi seçerek Telegram Stars ile hemen satın alabilirsiniz:"
    )
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    await context.bot.send_invoice(
        chat_id=q.from_user.id, 
        title="Vantorium Premium", 
        description=f"{days} günlük özel premium üyelik paketi.", 
        payload=f"premium_{uid}_{days}", 
        provider_token="", 
        currency="XTR", 
        prices=[{"label": "Premium", "amount": stars}]
    )

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text("🎉 Ödeme başarılı! Premium üyeliğiniz aktif edildi.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs: return
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-3000:]
    except: content = "Okunamadı."
    text = f"📃 Bot Logları:\n\n{html.escape(content)}"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("stop_", "")
    stop_bot_process(pk)
    text = "⏹ Bot durduruldu."
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
application.add_handler(CallbackQueryHandler(message_logs_view, pattern="^message_logs$"))
application.add_handler(CallbackQueryHandler(important_logs_view, pattern="^important_logs$"))
application.add_handler(CallbackQueryHandler(toggle_maintenance_callback, pattern="^toggle_maintenance$"))
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
application.add_handler(CallbackQueryHandler(handle_admin_approval_callback, pattern="^(approve_|reject_)"))

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_router))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

def restore_active_bots_on_startup():
    saved_bots = global_state.get("active_bots", {})
    for pk, info in saved_bots.items():
        try:
            start_bot_process(
                user_id=info["user_id"],
                bot_token=info["token"],
                code_content=info["code"],
                bot_name=info["name"],
                username=info["username"],
                file_name=info["file_name"],
                u_name=info["user_fullname"]
            )
        except: pass

def run_bot_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    restore_active_bots_on_startup()
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
