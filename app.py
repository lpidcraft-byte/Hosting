import os
import sys
import json
import base64
import shutil
import subprocess
import time
import re
import logging
import asyncio
import threading
import requests
import html
import platform
from pathlib import Path
from collections import defaultdict
from flask import Flask, request, Response

def ensure_dependencies():
    # waitress eklendi (Flask'ı production modunda çalıştırmak için)
    required = {"pip": "pip", "socks": "PySocks", "telegram": "python-telegram-bot",
                "flask": "flask", "requests": "requests", "waitress": "waitress"}
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except ImportError:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", pkg], check=True)
            except Exception:
                pass

ensure_dependencies()

from waitress import serve
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

FALLBACK_URL = "https://hosting-production-a01232b6.up.railway.app"

REQUIRED_CHANNELS = [
    {"id": -1003947388912, "link": "https://t.me/+3A7s7kVfaoMxYjM0", "name": "VANTOKRIUM TEAM KRALLIK"},
    {"id": -1004443368027, "link": "https://t.me/vantoriumchat", "name": "VANTORIUM TEAM SOHBET"}
]

EMOJI_IDS = {
    "👋": 5454390891466726015, "👍": 5456267427102858366, "⚠": 5879449820338330922,
    "👮‍♀": 5818678700274617758, "👮": 5818678700274617758,
    "✅": 5927037044365725425, "🛠": 5818705028424141605, "💬": 5819022220348886685,
    "⚙": 5929098607192969118, "👤": 5352861489541714456, "⏳": 5337172996211648018,
    "📊": 5352877703043258544, "🎁": 5879631269821685769, "🟢": 5879696093763084445,
    "🔴": 5463260230861202209, "💎": 5352838545826420397, "🗑": 5231339530249845638,
    "📥": 5386570059328010279, "🚫": 5796574861539155606, "↩": 5255799059762941032,
    "❌": 5420130255174145507, "🧹": 4956591954088428445, "⚡": 4958479549265347295,
    "🛒": 5265132878395621818, "💰": 4958926882994127612, "➕": 4956507094124594921,
    "👑": 5217822164362739968, "⭐": 5438496463044752972, "📦": 5884479287171485878,
    "🎟": 6070989023684333046, "🏠": 4981247505908893312, "📃": 5257965810634202885,
    "📄": 5257965810634202885, "🎉": 6287474217424263219, "🔧": 5348239232852836489,
    "🆔": 5818885490065017876, "⏱": 6037268453759389862, "🔍": 5258274739041883702,
    "👥": 4909043075529048789, "🌐": 5821388137443626414, "🤖": 5352861489541714456,
    "📁": 5257965810634202885, "🔒": 5818885490065017876, "📋": 5229064374403997682,
    "❓": 5379748062124056162, "💡": 5424892643760937442, "🎯": 5438496463044752972,
    "🚀": 4958479549265347295, "🛡": 5818885490065017876, "💌": 5879631269821685769
}

class SensitiveFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
            msg = msg.replace(MAIN_BOT_TOKEN, "GIZLENDI")
            msg = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:GIZLENDI', msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
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
SECURITY_LOG_FILE = DATA_DIR / "security_logs.json"
ORIGINAL_META_FILE = DATA_DIR / "original_meta.json"
ORIGINAL_PHOTO_FILE = DATA_DIR / "original_photo.jpg"
PREMIUM_HISTORY_FILE = DATA_DIR / "premium_history.json"
PROMO_FILE = DATA_DIR / "promo_codes.json"

PENDING_APPROVALS = {}
ACTIVE_MAIN_CONNECTIONS = {}
RATE_LIMIT = defaultdict(list)
BOT_START_TIME = time.time()

MAX_FILE_SIZE = 10 * 1024 * 1024
STANDARD_FILE_LIMIT = 2 * 1024 * 1024
PREMIUM_FILE_LIMIT = 10 * 1024 * 1024

STANDARD_BOT_LIMIT = 2
PREMIUM_BOT_LIMIT = 10
MAX_VIOLATIONS_BEFORE_BAN = 3

AUTO_PIP_MODULES = {
    "requests": "requests", "numpy": "numpy", "pandas": "pandas",
    "telegram": "python-telegram-bot", "flask": "flask", "aiohttp": "aiohttp",
    "bs4": "beautifulsoup4", "lxml": "lxml", "PIL": "pillow",
    "psutil": "psutil", "sqlalchemy": "sqlalchemy", "redis": "redis",
    "pymongo": "pymongo", "openpyxl": "openpyxl", "matplotlib": "matplotlib",
    "scipy": "scipy", "yfinance": "yfinance", "ccxt": "ccxt",
    "cryptography": "cryptography", "Crypto": "pycryptodome",
    "instagrapi": "instagrapi", "tweepy": "tweepy", "discord": "discord.py",
    "yt_dlp": "yt-dlp", "cv2": "opencv-python", "pyrogram": "pyrogram",
    "telethon": "telethon", "aiogram": "aiogram", "fastapi": "fastapi",
    "uvicorn": "uvicorn", "pydantic": "pydantic", "httpx": "httpx",
    "aiofiles": "aiofiles", "yaml": "pyyaml", "dotenv": "python-dotenv",
    "qrcode": "qrcode", "pytz": "pytz", "dateutil": "python-dateutil",
    "colorama": "colorama", "tqdm": "tqdm", "rich": "rich", "loguru": "loguru",
    "schedule": "schedule", "apscheduler": "apscheduler", "websockets": "websockets",
    "cloudscraper": "cloudscraper", "fake_useragent": "fake-useragent",
    "pytube": "pytube", "instaloader": "instaloader", "praw": "praw",
    "wikipedia": "wikipedia", "validators": "validators",
    "phonenumbers": "phonenumbers", "PyPDF2": "PyPDF2", "docx": "python-docx",
    "pptx": "python-pptx", "pydub": "pydub", "pygame": "pygame",
    "pyautogui": "pyautogui", "jinja2": "jinja2", "bcrypt": "bcrypt",
    "jwt": "pyjwt", "gunicorn": "gunicorn", "openai": "openai",
    "transformers": "transformers", "datasets": "datasets",
    "sklearn": "scikit-learn", "xgboost": "xgboost", "seaborn": "seaborn",
    "plotly": "plotly", "streamlit": "streamlit", "gradio": "gradio",
}

MALICIOUS_PATTERNS = [
    (r"\bos\.environ\b", "Ortam değişkenlerine erişim"),
    (r"\bMAIN_BOT_TOKEN\b", "Ana bot token erişimi"),
    (r"\bBOT_TOKEN\b", "Sistem token erişimi"),
    (r"/proc/(?:self|\d+)/environ", "Sunucu ortam dosyası"),
    (r"/proc/(?:self|\d+)/cmdline", "Sunucu komut satırı"),
    (r"/etc/(?:passwd|shadow|hosts)", "Sistem kritik dosyaları"),
    (r"state\.json|message_logs\.json|important_logs\.json", "Bot veri/log dosyaları"),
    (r"\bos\.(?:system|popen|execv|execl|spawn)\b", "Sistem komutu"),
    (r"\bpty\.spawn\b", "Etkileşimli kabuk"),
    (r"\bsocket\.socket\b", "Ham ağ soketi"),
    (r"(?:requests\.post|httpx\.post|urlopen)\s*\(.*(?:environ|token|secret|password)", "Veri sızdırma"),
    (r"\b(?:eval|exec)\s*\(.*(?:environ|socket|open|base64)", "Dinamik tehlikeli kod"),
]

PREMIUM_FORBIDDEN_MODULES = [
    (r"\bimport\s+ctypes\b", "ctypes"),
    (r"\bfrom\s+ctypes\b", "ctypes"),
    (r"\bimport\s+multiprocessing\b", "multiprocessing"),
    (r"\bimport\s+paramiko\b", "paramiko"),
    (r"\bimport\s+scapy\b", "scapy"),
    (r"\bimport\s+impacket\b", "impacket"),
    (r"\bimport\s+pty\b", "pty"),
    (r"\bimport\s+fcntl\b", "fcntl"),
    (r"\bimport\s+winreg\b", "winreg"),
    (r"\bimport\s+_winreg\b", "_winreg"),
    (r"\bimport\s+msvcrt\b", "msvcrt"),
    (r"\bimport\s+pickle\b", "pickle"),
    (r"\bimport\s+marshal\b", "marshal"),
    (r"\bimport\s+dill\b", "dill"),
    (r"\b__import__\s*\(", "dinamik import"),
]

def decode_base64_layers(content, max_depth=3):
    decoded_texts = []
    seen = set()
    queue = [(content, 0)]
    while queue:
        current_text, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        candidates = re.findall(r"[A-Za-z0-9+/=]{16,}", current_text)
        stripped = re.sub(r"\s+", "", current_text)
        if len(stripped) >= 16 and re.fullmatch(r"[A-Za-z0-9+/=]+", stripped):
            candidates.append(stripped)
        for cand in candidates:
            clean = re.sub(r"\s+", "", cand)
            if len(clean) < 16 or clean in seen:
                continue
            seen.add(clean)
            pad_len = (-len(clean)) % 4
            padded = clean + ("=" * pad_len)
            try:
                raw = base64.b64decode(padded, validate=False)
                if not raw:
                    continue
                decoded_str = raw.decode("utf-8", errors="ignore")
                printable = sum(1 for ch in decoded_str if ch.isprintable() or ch in "\r\n\t") / max(len(decoded_str), 1)
                if printable > 0.75 and len(decoded_str.strip()) >= 6:
                    decoded_texts.append(decoded_str)
                    queue.append((decoded_str, depth + 1))
            except Exception:
                continue
    return decoded_texts

def scan_code(code):
    decoded = decode_base64_layers(code, max_depth=3)
    targets = [("Orijinal", code)] + [(f"Base64 #{i}", d) for i, d in enumerate(decoded, 1)]
    findings = []
    for label, target in targets:
        for pattern, reason in MALICIOUS_PATTERNS:
            try:
                if re.search(pattern, target, flags=re.IGNORECASE | re.MULTILINE):
                    entry = f"{reason} [{label}]"
                    if entry not in findings:
                        findings.append(entry)
            except re.error:
                continue
    return findings, len(decoded) > 0

def scan_forbidden_modules(code):
    warnings = []
    for pattern, reason in PREMIUM_FORBIDDEN_MODULES:
        try:
            if re.search(pattern, code, flags=re.IGNORECASE):
                if reason not in warnings:
                    warnings.append(reason)
        except re.error:
            continue
    return warnings

def extract_imports(code):
    imports = set()
    for m in re.finditer(r"^\s*import\s+([A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*)", code, re.MULTILINE):
        for part in m.group(1).split(","):
            mod = part.strip().split(".")[0]
            if mod:
                imports.add(mod)
    for m in re.finditer(r"^\s*from\s+([A-Za-z_][\w.]*)\s+import", code, re.MULTILINE):
        mod = m.group(1).strip().split(".")[0]
        if mod:
            imports.add(mod)
    return imports

def auto_install_for_premium(code, user_id, chat_id, context):
    imports = extract_imports(code)
    to_install = []
    for mod in imports:
        if mod in AUTO_PIP_MODULES:
            pkg = AUTO_PIP_MODULES[mod]
            try:
                __import__(mod)
            except ImportError:
                to_install.append(pkg)
        elif mod not in ("os", "sys", "json", "re", "time", "datetime",
                         "base64", "html", "random", "string", "threading",
                         "asyncio", "logging", "subprocess", "shutil",
                         "pathlib", "collections", "typing", "functools",
                         "itertools", "math", "hashlib", "uuid", "copy",
                         "tempfile", "traceback", "urllib", "http", "email",
                         "smtplib", "io", "csv", "sqlite3", "unicodedata"):
            to_install.append(mod)

    installed_ok = []
    installed_fail = []
    for pkg in set(to_install):
        try:
            res = subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", pkg],
                                 capture_output=True, timeout=120)
            if res.returncode == 0:
                installed_ok.append(pkg)
            else:
                installed_fail.append(pkg)
        except Exception:
            installed_fail.append(pkg)

    try:
        if installed_ok:
            asyncio.run_coroutine_threadsafe(
                context.bot.send_message(chat_id,
                    f"📦 <b>Otomatik Pip Yükleme</b>\n\n✅ Yüklenen: <code>{', '.join(installed_ok)}</code>",
                    parse_mode="HTML"), bot_loop)
        if installed_fail:
            asyncio.run_coroutine_threadsafe(
                context.bot.send_message(chat_id,
                    f"⚠️ <b>Yüklenemeyen paketler:</b> <code>{', '.join(installed_fail)}</code>",
                    parse_mode="HTML"), bot_loop)
        if installed_ok or installed_fail:
            asyncio.run_coroutine_threadsafe(
                context.bot.send_message(ADMIN_ID,
                    f"📦 <b>Premium Otomatik Pip</b>\n"
                    f"👤 <code>{user_id}</code>\n"
                    f"✅ {', '.join(installed_ok) or '-'}\n"
                    f"❌ {', '.join(installed_fail) or '-'}",
                    parse_mode="HTML"), bot_loop)
    except Exception:
        pass

def load_state():
    default = {
        "users": {}, "premium": {}, "banned": [], "maintenance": False,
        "active_bots": {}, "violations": {}
    }
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in default.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return default

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(global_state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

global_state = load_state()
running_procs = {}
application = Application.builder().token(BOT_TOKEN).updater(None).build()
bot_loop = asyncio.new_event_loop()
flask_app = Flask(__name__)

def get_webhook_url():
    if RAILWAY_URL:
        return f"{RAILWAY_URL}/webhook/{MAIN_BOT_TOKEN}"
    if RENDER_URL:
        return f"{RENDER_URL}/webhook/{MAIN_BOT_TOKEN}"
    if VERCEL_URL:
        return f"https://{VERCEL_URL}/webhook/{MAIN_BOT_TOKEN}"
    return f"{FALLBACK_URL}/webhook/{MAIN_BOT_TOKEN}"

def force_delete_webhook():
    try:
        url = f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/deleteWebhook"
        requests.post(url, json={"drop_pending_updates": False}, timeout=10)
    except Exception:
        pass

def setup_webhook():
    target = get_webhook_url()
    if not target:
        return False
    try:
        info = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getWebhookInfo", timeout=10).json()
        current_url = info.get("result", {}).get("url", "")
        if current_url == target:
            return True
        if current_url:
            force_delete_webhook()
            time.sleep(1)
    except Exception:
        pass

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setWebhook",
            json={
                "url": target,
                "drop_pending_updates": False,
                "max_connections": 1, # TEK SEFERDE 1 BAĞLANTI (429 HATASINI ÇÖZER)
                "allowed_updates": ["message", "callback_query", "pre_checkout_query"]
            },
            timeout=15
        ).json()
        if res.get("ok"):
            logger.info(f"✅ Webhook başarıyla kuruldu: {target}")
            return True
    except Exception as e:
        logger.error(f"Webhook kurulum hatası: {e}")
    return False

def webhook_watchdog():
    while True:
        try:
            target = get_webhook_url()
            info = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getWebhookInfo", timeout=10).json()
            if info.get("ok"):
                result = info.get("result", {})
                current_url = result.get("url", "")
                last_error = result.get("last_error_message", "")

                if current_url != target:
                    setup_webhook()
                # Broken pipe veya 429 hatası olsa bile watchdog sadece bekler, Telegram'ı boğmaz.
        except Exception:
            pass
        time.sleep(300) # 5 dakikaya çıkardık (Telegram ban yemesin diye)

threading.Thread(target=webhook_watchdog, daemon=True).start()

@flask_app.route("/", methods=["GET"])
def health():
    return "OK", 200

@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        req_json = request.get_json(force=True)
        update = Update.de_json(req_json, application.bot)
        
        # İstekleri engellemiyoruz, direkt kuyruğa atıyoruz
        if update:
            asyncio.run_coroutine_threadsafe(application.update_queue.put(update), bot_loop)
            
        return Response("OK", status=200)
    except Exception:
        return Response("OK", status=200)

def premium_button(text, callback_data=None, emoji="✅", style=None, url=None):
    kw = {"text": text}
    if url: kw["url"] = url
    else: kw["callback_data"] = callback_data
    if emoji and emoji in EMOJI_IDS:
        kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style: kw["style"] = style
    try:
        return InlineKeyboardButton(**kw)
    except Exception:
        return InlineKeyboardButton(text=text, callback_data=callback_data or "noop", url=url)

def parse_entities(text):
    entities = []
    if not text: return entities
    used = set()
    for emoji_char, emoji_id in EMOJI_IDS.items():
        start = 0
        while True:
            idx = text.find(emoji_char, start)
            if idx == -1: break
            offset = len(text[:idx].encode('utf-16-le')) // 2
            length = len(emoji_char.encode('utf-16-le')) // 2
            if (offset, length) not in used:
                used.add((offset, length))
                entities.append(MessageEntity(type="custom_emoji", offset=offset, length=length, custom_emoji_id=str(emoji_id)))
            start = idx + len(emoji_char)
    return entities

def mask_token(text):
    if not text: return ""
    text = text.replace(MAIN_BOT_TOKEN, "GIZLENDI")
    text = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:GIZLENDI', text)
    return text

def is_premium(uid): return global_state["premium"].get(str(uid), 0) > time.time()
def is_banned(uid): return str(uid) in global_state.get("banned", [])

def format_uptime(started_ts):
    sec = max(0, int(time.time() - started_ts))
    dak, sn = divmod(sec, 60)
    saat, dak = divmod(dak, 60)
    gun, saat = divmod(saat, 24)
    if gun > 0: return f"{gun}g {saat}s"
    if saat > 0: return f"{saat}s {dak}d"
    return f"{dak}d {sn}sn"

def log_user_message(user, text):
    if not user or not text: return
    try:
        logs = []
        if MESSAGE_LOGS_FILE.exists():
            logs = json.loads(MESSAGE_LOGS_FILE.read_text(encoding="utf-8"))
        logs.append({"time": time.strftime("%d.%m.%Y %H:%M:%S"), "id": user.id,
                     "name": user.first_name or "", "username": user.username or "yok",
                     "text": mask_token(text)})
        MESSAGE_LOGS_FILE.write_text(json.dumps(logs[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def log_important(data):
    try:
        logs = []
        if IMPORTANT_LOGS_FILE.exists():
            logs = json.loads(IMPORTANT_LOGS_FILE.read_text(encoding="utf-8"))
        logs.append({"time": time.strftime("%d.%m.%Y %H:%M:%S"), **data})
        IMPORTANT_LOGS_FILE.write_text(json.dumps(logs[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def log_security(data):
    try:
        logs = []
        if SECURITY_LOG_FILE.exists():
            logs = json.loads(SECURITY_LOG_FILE.read_text(encoding="utf-8"))
        logs.append({"time": time.strftime("%d.%m.%Y %H:%M:%S"), **data})
        SECURITY_LOG_FILE.write_text(json.dumps(logs[-300:], ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass

def health_check():
    while True:
        try:
            for pk, info in list(running_procs.items()):
                if info["proc"].poll() is not None:
                    restart_bot_process(pk)
        except Exception:
            pass
        time.sleep(60)

threading.Thread(target=health_check, daemon=True).start()

async def check_membership(user_id):
    for ch in REQUIRED_CHANNELS:
        try:
            m = await application.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if m.status not in ["member", "administrator", "creator"]:
                return False
        except Exception:
            return False
    return True

async def send_join_message(update, context):
    kb = [[premium_button(f"📢 {ch['name']}", emoji="📢", style="primary", url=ch["link"])] for ch in REQUIRED_CHANNELS]
    kb.append([premium_button("Kontrol Et", "check_join", "✅", "success")])
    text = "⚠ <b>Zorunlu Kanal Üyeliği</b>\n\nKanallara katılın ve Kontrol Et'e basın."
    entities = parse_entities(text)
    if update.callback_query:
        try: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
        except Exception: pass
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")

async def check_join_callback(update, context):
    q = update.callback_query
    await q.answer()
    if await check_membership(q.from_user.id):
        await show_main_menu(update, context)
    else:
        await q.answer("⚠ Lütfen tüm kanallara katılın.", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot", username="yok",
                       file_name="bot.py", u_name="", proc_key=None):
    uid = str(user_id)
    if not proc_key:
        proc_key = f"{uid}_{int(time.time() * 1000)}"
    bot_dir = DATA_DIR / "user_bots" / uid / proc_key
    bot_dir.mkdir(parents=True, exist_ok=True)
    script = bot_dir / f"bot_{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"
    safe = code_content.replace(MAIN_BOT_TOKEN, "9000000000:AABBBCCDDEEFFGGHHIIJJKKLMMNNOOPPQQRR")
    script.write_text(safe, encoding="utf-8")
    if bot_token and bot_token != "Bulunamadı":
        try: requests.post(f"https://api.telegram.org/bot{bot_token}/deleteWebhook",
                           json={"drop_pending_updates": False}, timeout=6)
        except Exception: pass
    log_file = open(log_path, "a", encoding="utf-8")
    env = {**os.environ, "BOT_TOKEN": bot_token}
    proc = subprocess.Popen([sys.executable, str(script)], stdout=log_file,
                             stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
    running_procs[proc_key] = {"proc": proc, "log_path": str(log_path), "token": bot_token,
                                "started": time.time(), "user_id": uid, "user_fullname": u_name,
                                "name": bot_name, "username": username, "file_name": file_name,
                                "script_path": str(script), "code": code_content}
    global_state["active_bots"][proc_key] = {"user_id": uid, "user_fullname": u_name,
                                               "token": bot_token, "name": bot_name,
                                               "username": username, "file_name": file_name,
                                               "code": code_content, "log_path": str(log_path)}
    save_state()
    log_important({"type": "bot_started", "user_id": uid, "user_name": u_name,
                   "bot_name": bot_name, "bot_username": username, "token": bot_token,
                   "file_name": file_name})
    return proc_key

def stop_bot_process(proc_key, remove_state=True):
    if proc_key in running_procs:
        p = running_procs[proc_key]["proc"]
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=5)
            except Exception: p.kill()
        del running_procs[proc_key]
        if remove_state and proc_key in global_state["active_bots"]:
            del global_state["active_bots"][proc_key]
            save_state()
        return True
    return False

def restart_bot_process(proc_key):
    info = running_procs.get(proc_key) or global_state.get("active_bots", {}).get(proc_key)
    if not info: return None
    code = info.get("code")
    if not code and info.get("script_path") and os.path.exists(info["script_path"]):
        code = Path(info["script_path"]).read_text(encoding="utf-8", errors="ignore")
    if not code: return None
    stop_bot_process(proc_key, remove_state=False)
    return start_bot_process(info["user_id"], info["token"], code,
                              info.get("name", "Bot"), info.get("username", "yok"),
                              info.get("file_name", "bot.py"), info.get("user_fullname", ""),
                              proc_key=proc_key)

def get_user_bot_count(uid):
    return len([k for k in running_procs if k.startswith(str(uid) + "_")])

def get_user_bot_limit(uid):
    return PREMIUM_BOT_LIMIT if is_premium(uid) else STANDARD_BOT_LIMIT

async def show_main_menu(update, context):
    user = update.effective_user
    if is_banned(user.id):
        text = "❌ <b>Hesabınız yasaklandı.</b>"
        entities = parse_entities(text)
        if update.message: await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try: await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except Exception: pass
        return
    if global_state.get("maintenance") and user.id != ADMIN_ID:
        text = "⚠ <b>Bot bakım modunda.</b>"
        entities = parse_entities(text)
        if update.message: await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try: await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except Exception: pass
        return
    uid = str(user.id)
    global_state["users"][uid] = {"username": user.username or "", "first_name": user.first_name or ""}
    save_state()
    kb = []
    if user.id == ADMIN_ID:
        kb.append([premium_button("Admin Paneli", "admin_panel", "👮‍♀", "primary")])
    kb.append([premium_button("Botlarım", "my_bots", "🤖", "success")])
    kb.append([premium_button("Premium Özellikleri", "premium_features", "💎", "primary")])
    kb.append([premium_button("Premium Al", "buy_premium", "🛒", "success")])
    kb.append([premium_button("Pip Yükleyici", "pip_menu", "📦", "primary")])
    kb.append([premium_button("Yardım", "help_menu", "❓", "primary")])
    prem = "💎 Premium" if is_premium(uid) else "👤 Standart"
    bot_count = get_user_bot_count(user.id)
    bot_limit = get_user_bot_limit(user.id)
    text = (
        f"👋 Merhaba <b>{html.escape(user.first_name or 'Kullanıcı')}</b>,\n\n"
        f"📊 Durum: {prem}\n"
        f"🤖 Bot: {bot_count}/{bot_limit}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        f"📄 Bot dosyanızı göndererek onay için admine iletebilirsiniz."
    )
    entities = parse_entities(text)
    if update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
    elif update.callback_query:
        try: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
        except Exception: pass

async def start_command(update, context):
    if global_state.get("maintenance") and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠ <b>Bot bakım modunda.</b>", parse_mode="HTML")
        return
    if is_banned(update.effective_user.id):
        await show_main_menu(update, context)
        return
    if not await check_membership(update.effective_user.id):
        await send_join_message(update, context)
        return
    await show_main_menu(update, context)

async def help_menu(update, context):
    q = update.callback_query
    if q: await q.answer()
    text = (
        "❓ <b>Yardım</b>\n\n"
        "🤖 <b>Komutlar:</b>\n"
        "• /start — Ana menü\n"
        "• /yardim — Bu menü\n"
        "• /premium — Premium durumunuz\n"
        "• /myid — ID'nizi öğrenin\n\n"
        "📄 <b>Bot Yönetimi:</b>\n"
        "• Ana menüden .py dosyası gönderin\n"
        "• Onay sonrası otomatik çalışır\n\n"
        "💎 <b>Premium:</b>\n"
        "• 10 aktif bot (Standart: 2)\n"
        "• 10 MB dosya limiti (Standart: 2 MB)\n"
        "• Otomatik pip yükleme\n"
        "• Öncelikli destek"
    )
    entities = parse_entities(text)
    kb = [[premium_button("Geri", "back_start", "↩", "danger")]]
    if q:
        try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
        except Exception: pass
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")

async def premium_features_view(update, context):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    is_prem = is_premium(uid)
    durum = "💎 <b>Premium Üyesiniz!</b>" if is_prem else "👤 <b>Standart Üyesiniz</b>"
    text = (
        f"💎 <b>Vantorium Premium Özellikleri</b>\n\n"
        f"📊 Durumunuz: {durum}\n\n"
        f"✨ <b>Premium Ayrıcalıkları:</b>\n"
        f"• 🤖 <b>10 aktif bot</b> (Standart: 2)\n"
        f"• 📦 <b>10 MB dosya limiti</b> (Standart: 2 MB)\n"
        f"• ⚡ <b>Öncelikli işlem kuyruğu</b>\n"
        f"• 📥 <b>Sınırsız pip paket</b> yükleme\n"
        f"• 📦 <b>Otomatik pip yükleme</b> (dosyadaki tüm import'lar)\n"
        f"• 📊 <b>Gelişmiş log yönetimi</b>\n"
        f"• 👑 <b>Premium rozet</b>\n"
        f"• 🆘 <b>Öncelikli destek</b>\n"
        f"• 🎟 <b>Promosyon kodlarına erken erişim</b>\n"
        f"• 🛡 <b>Yasaklı modül koruması</b> aktif\n\n"
        f"💰 <b>Fiyatlar:</b>\n"
        f"• 1 Hafta — 15 ⭐\n"
        f"• 1 Ay — 40 ⭐\n"
        f"• 1 Yıl — 100 ⭐\n\n"
        f"👇 Satın almak için bir süre seçin:"
    )
    kb = []
    if not is_prem:
        kb.append([premium_button("1 Hafta (15 ⭐)", "premium_7", "⭐", "primary")])
        kb.append([premium_button("1 Ay (40 ⭐)", "premium_30", "⭐", "success")])
        kb.append([premium_button("1 Yıl (100 ⭐)", "premium_365", "💎", "primary")])
    else:
        kb.append([premium_button("Premium'u Uzat", "buy_premium", "🔄", "success")])
    kb.append([premium_button("Geri", "back_start", "↩", "danger")])
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def myid_command(update, context):
    await update.message.reply_text(f"🆔 <b>ID'niz:</b> <code>{update.effective_user.id}</code>", parse_mode="HTML")

async def premium_status_command(update, context):
    uid = str(update.effective_user.id)
    if is_premium(uid):
        exp = global_state["premium"].get(uid, 0)
        exp_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(exp))
        rem = max(0, int(exp - time.time()))
        gun, kalan = divmod(rem, 86400)
        text = f"💎 <b>Premium Aktif</b>\n\n📅 Bitiş: <code>{exp_str}</code>\n⏱ Kalan: <b>{gun} gün {kalan // 3600} saat</b>"
    else:
        text = "👤 <b>Premium yok.</b>"
    entities = parse_entities(text)
    await update.message.reply_text(text, entities=entities, parse_mode="HTML")

async def admin_panel(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    m = "AÇIK 🟢" if global_state.get("maintenance") else "KAPALI 🔴"
    text = "⚙ <b>Admin Paneli</b>"
    kb = [
        [premium_button("İstatistikler", "stats_view", "📊", "success")],
        [premium_button(f"Bakım: {m}", "toggle_maintenance", "🔒", "danger")],
        [premium_button("Ban At", "ban_user", "🚫", "danger"),
         premium_button("Ban Kaldır", "unban_user", "✅", "success")],
        [premium_button("Premium Ver", "give_premium", "💎", "success")],
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def stats_view(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = len(global_state.get("users", {}))
    prem = sum(1 for v in global_state["premium"].values() if v > time.time())
    banned = len(global_state.get("banned", []))
    active = len(running_procs)
    alive = sum(1 for i in running_procs.values() if i["proc"].poll() is None)
    text = (
        f"📊 <b>İstatistikler</b>\n\n"
        f"👥 Kullanıcı: <b>{total}</b>\n"
        f"💎 Premium: <b>{prem}</b>\n"
        f"🚫 Banlı: <b>{banned}</b>\n"
        f"🤖 Bot: <b>{active}</b>\n"
        f"🟢 Çalışan: <b>{alive}</b>\n"
        f"⏱ Uptime: <b>{format_uptime(BOT_START_TIME)}</b>"
    )
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def toggle_maintenance_callback(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    global_state["maintenance"] = not global_state.get("maintenance", False)
    save_state()
    await admin_panel(update, context)

async def ban_user_menu(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_ban_id"] = True
    text = "🚫 <b>Ban</b>\n\nYasaklanacak ID:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def unban_user_menu(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_unban_id"] = True
    text = "✅ <b>Ban Kaldır</b>\n\nID:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def give_premium_menu(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_premium_id"] = True
    text = "💎 <b>Premium Ver</b>\n\nKullanıcı ID:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardUp([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def premium_duration_menu(update, context, user_id):
    context.user_data["premium_target_id"] = user_id
    kb = [[premium_button("1 Hafta", "give_prem_7", "⭐", "primary")],
          [premium_button("1 Ay", "give_prem_30", "⭐", "success")],
          [premium_button("1 Yıl", "give_prem_365", "💎", "primary")],
          [premium_button("İptal", "admin_panel", "❌", "danger")]]
    text = f"🎯 ID: <code>{html.escape(str(user_id))}</code>\n\nSüre:"
    entities = parse_entities(text)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")

async def execute_give_premium(update, context, days):
    q = update.callback_query
    await q.answer()
    target = context.user_data.get("premium_target_id")
    if not target: return
    current = global_state["premium"].get(str(target), 0)
    base = max(current, time.time())
    global_state["premium"][str(target)] = base + days * 86400
    save_state()
    text = f"✅ <code>{html.escape(str(target))}</code> <b>{days} gün</b> premium verildi."
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Admin", "admin_panel", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def my_bots(update, context):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    if not bl:
        text = "🤖 <b>Bot yok.</b>\n\nAna menüden .py dosyası gönderin."
        entities = parse_entities(text)
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")
        return
    kb = []
    lines = ["🤖 <b>Botlarınız</b>\n"]
    for idx, pk in enumerate(bl, 1):
        info = running_procs[pk]
        alive = info["proc"].poll() is None
        icon = "🟢" if alive else "🔴"
        up = format_uptime(info.get("started", time.time()))
        lines.append(f"{idx}. {icon} <b>{html.escape(str(info['name']))}</b> — ⏱ {up}")
        kb.append([premium_button(f"Log: {info['name']}", f"log_{pk}", "📃", "primary"),
                   premium_button("Yeniden Başlat", f"restart_{pk}", "⚡", "success")])
        kb.append([premium_button(f"Sil: {info['name']}", f"del_{pk}", "🗑", "danger")])
    kb.append([premium_button("Geri", "back_start", "↩", "danger")])
    entities = parse_entities("\n".join(lines))
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")

async def restart_bot_callback(update, context):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("restart_", "")
    new_pk = restart_bot_process(pk)
    text = "⚡ <b>Bot yeniden başlatıldı!</b>" if new_pk else "❌ <b>Başarısız.</b>"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def delete_bot(update, context):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs: stop_bot_process(pk)
    text = "🗑 <b>Bot silindi.</b>"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def pip_menu(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_pip_package"] = True
    text = "📦 <b>Pip Yükleyici</b>\n\nPaket adı:\n\nÖrnek: <code>requests</code>"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")

def install_pip_bg(package, chat_id, context):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package], check=True)
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id, f"✅ <b>{package}</b> yüklendi!", parse_mode="HTML"), bot_loop)
    except Exception:
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id, f"❌ <b>{package}</b> yüklenemedi!", parse_mode="HTML"), bot_loop)

async def buy_premium(update, context):
    q = update.callback_query
    await q.answer()
    kb = [[premium_button("1 Hafta (15 ⭐)", "premium_7", "⭐", "primary")],
          [premium_button("1 Ay (40 ⭐)", "premium_30", "⭐", "success")],
          [premium_button("1 Yıl (100 ⭐)", "premium_365", "💎", "primary")],
          [premium_button("Geri", "back_start", "↩", "danger")]]
    text = "💎 <b>Premium</b>\n\nSüre seçin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")

async def handle_premium_purchase(update, context):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    await context.bot.send_invoice(q.from_user.id, "Vantorium Premium",
                                    f"{days} günlük premium.",
                                    f"premium_{uid}_{days}", "", "XTR",
                                    [{"label": "Premium", "amount": stars}])

async def pre_checkout(update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update, context):
    msg = update.message
    parts = msg.successful_payment.invoice_payload.split("_")
    if len(parts) >= 3:
        target = parts[1]
        days = int(parts[2])
        current = global_state["premium"].get(target, 0)
        base = max(current, time.time())
        global_state["premium"][target] = base + days * 86400
        save_state()
    await msg.reply_text("🎉 <b>Ödeme başarılı!</b>", parse_mode="HTML")

async def log_view(update, context):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs:
        await q.answer("Bot yok.", show_alert=True)
        return
    try:
        content = Path(running_procs[pk]["log_path"]).read_text(encoding="utf-8", errors="ignore")[-2600:].strip()
    except Exception:
        content = "Log yok."
    safe = html.escape(content or "Henüz log yok.")
    text = f"📃 <b>Log</b>\n\n<code>{safe}</code>"
    kb = [[premium_button("Kopyala", f"copylog_{pk}", "📋", "primary")],
          [premium_button("Log Al", f"downloadlog_{pk}", "📥", "success")],
          [premium_button("Temizle", f"clearlog_{pk}", "🧹", "danger")],
          [premium_button("Geri", "my_bots", "↩", "primary")]]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def copylog_callback(update, context):
    q = update.callback_query
    await q.answer("📋")
    pk = q.data.replace("copylog_", "")
    if pk not in running_procs: return
    try:
        content = Path(running_procs[pk]["log_path"]).read_text(encoding="utf-8", errors="ignore")[-3500:]
    except Exception:
        content = ""
    await context.bot.send_message(q.from_user.id, f"📋 <b>Log</b>\n\n<code>{html.escape(content)}</code>", parse_mode="HTML")

async def downloadlog_callback(update, context):
    q = update.callback_query
    await q.answer("📥")
    pk = q.data.replace("downloadlog_", "")
    if pk not in running_procs: return
    try:
        content = Path(running_procs[pk]["log_path"]).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        content = ""
    tmp = DATA_DIR / f"log_{pk}_{int(time.time())}.txt"
    tmp.write_text(content or "Log yok", encoding="utf-8")
    try:
        await context.bot.send_document(q.from_user.id, str(tmp), filename=f"log_{pk}.txt", caption="📥 Log")
    except Exception:
        pass
    finally:
        try: tmp.unlink(missing_ok=True)
        except Exception: pass

async def clear_log_callback(update, context):
    q = update.callback_query
    await q.answer("🧹")
    pk = q.data.replace("clearlog_", "")
    info = running_procs.get(pk)
    if info:
        try: Path(info["log_path"]).write_text("", encoding="utf-8")
        except Exception: pass
    text = "🧹 <b>Temizlendi.</b>"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def handle_text_router(update, context):
    user = update.effective_user
    if not user: return
    if is_banned(user.id):
        await update.message.reply_text("❌ <b>Yasaklısınız.</b>", parse_mode="HTML"); return
    if global_state.get("maintenance") and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ <b>Bakım modu.</b>", parse_mode="HTML"); return
    text = (update.message.text or "").strip()
    log_user_message(user, text)
    ud = context.user_data
    if ud.get("awaiting_ban_id"):
        ud["awaiting_ban_id"] = False
        if text not in global_state["banned"]:
            global_state["banned"].append(text); save_state()
        await update.message.reply_text(f"🚫 Banlandı: <code>{html.escape(text)}</code>", parse_mode="HTML"); return
    if ud.get("awaiting_unban_id"):
        ud["awaiting_unban_id"] = False
        if text in global_state["banned"]:
            global_state["banned"].remove(text); save_state()
            await update.message.reply_text(f"✅ Kaldırıldı: <code>{html.escape(text)}</code>", parse_mode="HTML")
        return
    if ud.get("awaiting_premium_id"):
        ud["awaiting_premium_id"] = False
        await premium_duration_menu(update, context, text)
        return
    if ud.get("awaiting_pip_package"):
        ud["awaiting_pip_package"] = False
        threading.Thread(target=install_pip_bg, args=(text, update.effective_chat.id, context)).start()
        await update.message.reply_text("⏳ Yükleniyor...", parse_mode="HTML")
        return
    await update.message.reply_text("ℹ️ /start yazın.", parse_mode="HTML")

async def handle_document(update, context):
    user = update.effective_user
    if not user: return
    if is_banned(user.id):
        await update.message.reply_text("❌ <b>Yasaklısınız.</b>", parse_mode="HTML"); return
    if global_state.get("maintenance") and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ <b>Bakım.</b>", parse_mode="HTML"); return
    doc = update.message.document
    if not doc.file_name.endswith(".py"):
        await update.message.reply_text("⚠ Sadece <b>.py</b>.", parse_mode="HTML"); return

    file_size = doc.file_size or 0
    file_size_mb = file_size / (1024 * 1024)
    user_prem = is_premium(user.id)
    limit = PREMIUM_FILE_LIMIT if user_prem else STANDARD_FILE_LIMIT
    limit_mb = limit // (1024 * 1024)

    if not user_prem and file_size > STANDARD_FILE_LIMIT:
        text = (
            f"⚠ <b>Dosya Boyutu Limiti</b>\n\n"
            f"📦 Boyut: <b>{file_size_mb:.2f} MB</b>\n"
            f"📉 Limit: <b>{limit_mb} MB</b>\n\n"
            f"💎 <b>Premium aboneliğiniz olmadığı için maalesef sadece "
            f"{limit_mb} MB dosyaları yükleyebilirsiniz.</b>\n\n"
            f"🚀 Premium ile <b>10 MB</b>'a kadar!"
        )
        kb = [[premium_button("Premium Al", "premium_features", "💎", "primary")],
              [premium_button("Geri", "back_start", "↩", "danger")]]
        entities = parse_entities(text)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), entities=entities, parse_mode="HTML")
        return

    if user_prem and file_size > PREMIUM_FILE_LIMIT:
        text = f"⚠ <b>Limit</b>\n\n📦 {file_size_mb:.2f} MB / {limit_mb} MB\n\nPremium maksimum 10 MB."
        entities = parse_entities(text)
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")
        return

    if user.id != ADMIN_ID:
        cur = get_user_bot_count(user.id)
        lim = get_user_bot_limit(user.id)
        if cur >= lim and not context.user_data.get("pending_update_target_pk"):
            await update.message.reply_text(f"⚠ <b>Bot limitiniz dolu!</b>\n\n📊 {cur}/{lim}", parse_mode="HTML"); return

    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}_{int(time.time())}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")

    findings, _ = scan_code(code)
    if findings and user.id != ADMIN_ID:
        context.user_data.pop("pending_update_target_pk", None)
        try: tmp.unlink(missing_ok=True)
        except Exception: pass
        ban_user_immediately(user.id)
        log_security({"user_id": str(user.id), "user_name": user.first_name or "",
                      "file_name": doc.file_name, "reason": ", ".join(findings[:3])})
        try:
            await context.bot.send_message(ADMIN_ID,
                f"🚨 <b>Zararlı Dosya!</b>\n👤 <code>{user.id}</code>\n📄 {html.escape(doc.file_name)}\n⚠ {', '.join(findings[:3])}",
                parse_mode="HTML")
        except Exception: pass
        await update.message.reply_text("🚫 <b>Güvenlik ihlali! Banlandınız.</b>", parse_mode="HTML")
        return

    if user_prem and user.id != ADMIN_ID:
        forbidden = scan_forbidden_modules(code)
        if forbidden:
            context.user_data.pop("pending_update_target_pk", None)
            try: tmp.unlink(missing_ok=True)
            except Exception: pass
            v = global_state["violations"].get(str(user.id), 0) + 1
            global_state["violations"][str(user.id)] = v
            save_state()
            if v >= MAX_VIOLATIONS_BEFORE_BAN:
                ban_user_immediately(user.id)
                await update.message.reply_text(
                    f"🚫 <b>Çok fazla ihlal ({v})!</b>\n\nHesabınız yasaklandı.",
                    parse_mode="HTML")
            else:
                await update.message.reply_text(
                    f"🚫 <b>Yasaklı Modül Tespit Edildi!</b>\n\n"
                    f"⚠ Tespit: <code>{', '.join(forbidden)}</code>\n\n"
                    f"Bu modüller güvenlik nedeniyle yasaktır.\n"
                    f"⚠ İhlal: {v}/{MAX_VIOLATIONS_BEFORE_BAN}",
                    parse_mode="HTML")
            log_security({"user_id": str(user.id), "user_name": user.first_name or "",
                          "file_name": doc.file_name, "reason": f"forbidden_modules: {forbidden}"})
            try:
                await context.bot.send_message(ADMIN_ID,
                    f"🚫 <b>Yasaklı Modül (Premium)</b>\n👤 <code>{user.id}</code>\n⚠ {', '.join(forbidden)}\n🔢 İhlal: {v}",
                    parse_mode="HTML")
            except Exception: pass
            return

    if user_prem and user.id != ADMIN_ID:
        threading.Thread(target=auto_install_for_premium,
                         args=(code, user.id, update.effective_chat.id, context)).start()

    tm = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    token = tm.group(1) if tm else "Bulunamadı"
    bot_uname = "yok"
    if token != "Bulunamadı":
        try:
            me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5).json()
            if me.get("ok"): bot_uname = me["result"].get("username", "yok")
        except Exception: pass
    bname = doc.file_name.replace(".py", "")
    target_pk = context.user_data.pop("pending_update_target_pk", None)
    is_update = bool(target_pk)
    req_id = f"req_{user.id}_{int(time.time() * 1000)}"
    PENDING_APPROVALS[req_id] = {"mode": "update" if is_update else "create",
                                   "target_pk": target_pk, "user_id": user.id,
                                   "name": user.first_name or "", "username": user.username or "yok",
                                   "token": token, "bot_name": bname, "bot_username": bot_uname,
                                   "code": code, "file_name": doc.file_name}
    if is_update:
        admin_text = (f"🔄 <b>Güncelleme</b>\n👤 {html.escape(user.first_name or '')}\n"
                      f"🆔 <code>{user.id}</code>\n📄 {html.escape(doc.file_name)}\n"
                      f"🏷 @{html.escape(bot_uname)}\n🔑 <code>{mask_token(token)}</code>")
        approve, reject = f"approveupd_{req_id}", f"rejectupd_{req_id}"
    else:
        admin_text = (f"🚨 <b>Yeni Bot</b>\n👤 {html.escape(user.first_name or '')}\n"
                      f"🆔 <code>{user.id}</code>\n📄 {html.escape(doc.file_name)}\n"
                      f"🏷 @{html.escape(bot_uname)}\n🔑 <code>{mask_token(token)}</code>")
        approve, reject = f"approve_{req_id}", f"reject_{req_id}"
    kb = [[premium_button("Onayla", approve, "✅", "success"),
           premium_button("Reddet", reject, "❌", "danger")]]
    try:
        await context.bot.send_document(ADMIN_ID, str(tmp), caption=admin_text,
                                         reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    except Exception:
        await context.bot.send_message(ADMIN_ID, admin_text,
                                        reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    await update.message.reply_text("⏳ Onaya gönderildi.", parse_mode="HTML")

async def _replace_msg(q, text):
    entities = parse_entities(text)
    if q.message and q.message.caption is not None:
        try:
            await q.edit_message_caption(caption=text, reply_markup=None, entities=entities, parse_mode="HTML")
            return
        except Exception: pass
    try:
        await q.edit_message_text(text, reply_markup=None, entities=entities, parse_mode="HTML")
    except Exception: pass

async def handle_admin_approval(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    data = q.data
    if data.startswith("approveupd_"):
        req_id = data.replace("approveupd_", "")
        req = PENDING_APPROVALS.get(req_id)
        if not req:
            await _replace_msg(q, "✅ Zaten işlendi."); return
        apply_approved_bot_update(req["target_pk"], req["token"], req["code"],
                                   req["bot_name"], req["bot_username"], req["file_name"],
                                   req["name"], str(req["user_id"]))
        try:
            await context.bot.send_message(int(req["user_id"]),
                f"🔄 <b>Bot güncellendi!</b>", parse_mode="HTML")
        except Exception: pass
        await _replace_msg(q, f"✅ Onaylandı: {html.escape(req['file_name'])}")
        del PENDING_APPROVALS[req_id]
    elif data.startswith("rejectupd_"):
        req_id = data.replace("rejectupd_", "")
        req = PENDING_APPROVALS.get(req_id)
        if not req:
            await _replace_msg(q, "❌ Zaten kapalı."); return
        try:
            await context.bot.send_message(int(req["user_id"]),
                f"❌ Reddedildi: {html.escape(req['file_name'])}", parse_mode="HTML")
        except Exception: pass
        await _replace_msg(q, f"❌ {html.escape(req['file_name'])}")
        del PENDING_APPROVALS[req_id]
    elif data.startswith("approve_"):
        req_id = data.replace("approve_", "")
        req = PENDING_APPROVALS.get(req_id)
        if not req:
            await _replace_msg(q, "✅ Zaten."); return
        start_bot_process(str(req["user_id"]), req["token"], req["code"],
                           req["bot_name"], req["bot_username"],
                           req["file_name"], req["name"])
        try:
            await context.bot.send_message(int(req["user_id"]),
                f"🎉 <b>Bot onaylandı!</b>", parse_mode="HTML")
        except Exception: pass
        await _replace_msg(q, f"✅ {html.escape(req['file_name'])}")
        del PENDING_APPROVALS[req_id]
    elif data.startswith("reject_"):
        req_id = data.replace("reject_", "")
        req = PENDING_APPROVALS.get(req_id)
        if not req:
            await _replace_msg(q, "❌ Zaten."); return
        try:
            await context.bot.send_message(int(req["user_id"]),
                f"❌ Reddedildi: {html.escape(req['file_name'])}", parse_mode="HTML")
        except Exception: pass
        await _replace_msg(q, f"❌ {html.escape(req['file_name'])}")
        del PENDING_APPROVALS[req_id]

def apply_approved_bot_update(target_pk, new_token, new_code, new_bname, new_b_username, new_f_name, u_fullname, uid):
    existing = running_procs.get(target_pk) or global_state.get("active_bots", {}).get(target_pk) or {}
    final_token = new_token if new_token != "Bulunamadı" else existing.get("token", "")
    if target_pk in running_procs:
        stop_bot_process(target_pk, remove_state=False)
    return start_bot_process(uid, final_token, new_code,
                              new_bname or existing.get("name", "Bot"),
                              new_b_username if new_b_username != "yok" else existing.get("username", "yok"),
                              new_f_name or existing.get("file_name", "bot.py"),
                              u_fullname or existing.get("user_fullname", ""), proc_key=target_pk)

def ban_user_immediately(user_id):
    uid = str(user_id)
    if uid not in global_state["banned"]:
        global_state["banned"].append(uid)
        save_state()

def restore_bots():
    for pk, info in global_state.get("active_bots", {}).items():
        try:
            start_bot_process(info["user_id"], info["token"], info["code"],
                                info["name"], info["username"], info["file_name"],
                                info.get("user_fullname", ""), proc_key=pk)
        except Exception: pass

def run_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    restore_bots()
    loop.run_forever()

# Handler kayıtları
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CommandHandler("yardim", help_menu))
application.add_handler(CommandHandler("help", help_menu))
application.add_handler(CommandHandler("myid", myid_command))
application.add_handler(CommandHandler("premium", premium_status_command))

application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(stats_view, pattern="^stats_view$"))
application.add_handler(CallbackQueryHandler(toggle_maintenance_callback, pattern="^toggle_maintenance$"))
application.add_handler(CallbackQueryHandler(ban_user_menu, pattern="^ban_user$"))
application.add_handler(CallbackQueryHandler(unban_user_menu, pattern="^unban_user$"))
application.add_handler(CallbackQueryHandler(give_premium_menu, pattern="^give_premium$"))
application.add_handler(CallbackQueryHandler(my_bots, pattern="^my_bots$"))
application.add_handler(CallbackQueryHandler(restart_bot_callback, pattern="^restart_"))
application.add_handler(CallbackQueryHandler(delete_bot, pattern="^del_"))
application.add_handler(CallbackQueryHandler(pip_menu, pattern="^pip_menu$"))
application.add_handler(CallbackQueryHandler(help_menu, pattern="^help_menu$"))
application.add_handler(CallbackQueryHandler(premium_features_view, pattern="^premium_features$"))
application.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_premium$"))
application.add_handler(CallbackQueryHandler(handle_premium_purchase, pattern="^premium_"))

async def gp7(u, c): await execute_give_premium(u, c, 7)
async def gp30(u, c): await execute_give_premium(u, c, 30)
async def gp365(u, c): await execute_give_premium(u, c, 365)
application.add_handler(CallbackQueryHandler(gp7, pattern="^give_prem_7$"))
application.add_handler(CallbackQueryHandler(gp30, pattern="^give_prem_30$"))
application.add_handler(CallbackQueryHandler(gp365, pattern="^give_prem_365$"))

application.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
application.add_handler(CallbackQueryHandler(copylog_callback, pattern="^copylog_"))
application.add_handler(CallbackQueryHandler(downloadlog_callback, pattern="^downloadlog_"))
application.add_handler(CallbackQueryHandler(clear_log_callback, pattern="^clearlog_"))
application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_start$"))
application.add_handler(CallbackQueryHandler(handle_admin_approval, pattern="^(approveupd_|rejectupd_|approve_|reject_)"))

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_router))
application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
application.add_handler(PreCheckoutQueryHandler(pre_checkout))
application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_async_loop, args=(bot_loop,), daemon=True)
    bot_thread.start()
    
    time.sleep(2)
    logger.info("Başlangıç webhook kurulumu başlıyor...")
    force_delete_webhook()
    time.sleep(1)
    setup_webhook()
    
    port = int(os.environ.get("PORT", 10000))
    # Flask yerine Waitress kullanıyoruz (Broken Pipe hatasını çözer)
    logger.info(f"Sunucu {port} portunda başlatılıyor...")
    serve(flask_app, host="0.0.0.0", port=port, threads=4)
