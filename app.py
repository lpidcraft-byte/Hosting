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

MALICIOUS_PATTERNS = [
    (r"\bos\.environ\b", "Ortam değişkenlerine erişim (os.environ)"),
    (r"\bgetenv\s*\(", "Ortam değişkeni okuma (getenv)"),
    (r"\bMAIN_BOT_TOKEN\b", "Ana bot tokenine erişim denemesi"),
    (r"\bBOT_TOKEN\b", "Sistem tokenine erişim denemesi"),
    (r"/proc/(?:self|\d+)/environ", "Sunucu bellek/ortam dosyasına erişim (/proc/.../environ)"),
    (r"/proc/(?:self|\d+)/cmdline", "Sunucu süreç komut satırına erişim (/proc/.../cmdline)"),
    (r"/etc/(?:passwd|shadow|hosts)", "Sistem kritik dosyalarına erişim (/etc/...)"),
    (r"\.env\b", ".env gizli yapılandırma dosyasına erişim"),
    (r"state\.json|message_logs\.json|important_logs\.json", "Bot veri ve log dosyalarına erişim"),
    (r"\bsubprocess\.(?:Popen|run|call|check_output|getoutput)\b", "Sunucu kabuk komutu çalıştırma (subprocess)"),
    (r"\bos\.(?:system|popen|execv|execl|spawn)\b", "Sistem komutu yürütme (os.*)"),
    (r"\bpty\.spawn\b", "Etkileşimli kabuk açma (pty.spawn)"),
    (r"\bsocket\.socket\b", "Ham ağ soketi açma (socket.socket)"),
    (r"(?:requests\.post|httpx\.post|urlopen)\s*\(.*(?:environ|token|secret|password|passwd|data|state|log)", "Dış sunucuya hassas veri/dosya sızdırma"),
    (r"\b(?:__import__|eval|exec)\s*\(.*(?:environ|subprocess|socket|open|base64)", "Dinamik tehlikeli kod yürütme")
]

def decode_base64_layers(content: str, max_depth: int = 3):
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
                printable_ratio = sum(1 for ch in decoded_str if ch.isprintable() or ch in "\r\n\t") / max(len(decoded_str), 1)
                if printable_ratio > 0.75 and len(decoded_str.strip()) >= 6:
                    decoded_texts.append(decoded_str)
                    queue.append((decoded_str, depth + 1))
            except Exception:
                continue

    return decoded_texts

def scan_code_for_vds_exfiltration(code: str):
    decoded_parts = decode_base64_layers(code, max_depth=3)
    scan_targets = [("Orijinal Dosya", code)]
    for idx, dec in enumerate(decoded_parts, 1):
        scan_targets.append((f"Base64 Çözülmüş #{idx}", dec))

    findings = []
    for source_label, target_text in scan_targets:
        for pattern, reason in MALICIOUS_PATTERNS:
            if re.search(pattern, target_text, flags=re.IGNORECASE | re.MULTILINE):
                entry = f"{reason} [{source_label}]"
                if entry not in findings:
                    findings.append(entry)

    return findings, len(decoded_parts) > 0

def ban_user_immediately(user_id: int):
    uid_str = str(user_id)
    if "banned" not in global_state:
        global_state["banned"] = []
    if uid_str not in global_state["banned"]:
        global_state["banned"].append(uid_str)
    save_state()

def purge_user_files(user_id: int, tmp_file: Path = None):
    if tmp_file and tmp_file.exists():
        try:
            tmp_file.unlink()
        except Exception:
            pass
    user_bot_dir = DATA_DIR / "user_bots" / str(user_id)
    if user_bot_dir.exists():
        try:
            shutil.rmtree(user_bot_dir, ignore_errors=True)
        except Exception:
            pass
    for req_id in list(PENDING_APPROVALS.keys()):
        if str(PENDING_APPROVALS[req_id].get("user_id")) == str(user_id):
            del PENDING_APPROVALS[req_id]

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
                    if k not in data:
                        data[k] = v
                return data
        except Exception:
            pass
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

        if update and update.effective_user:
            uid = update.effective_user.id
            now = time.time()
            if uid != ADMIN_ID:
                global ACTIVE_MAIN_CONNECTIONS
                ACTIVE_MAIN_CONNECTIONS = {k: t for k, t in ACTIVE_MAIN_CONNECTIONS.items() if now - t < 3.0}
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
                    except Exception:
                        pass
                    return Response("Connection Terminated", status=429)

        asyncio.run_coroutine_threadsafe(application.update_queue.put(update), bot_loop)
        return Response("OK", status=200)
    except Exception:
        return Response("Error", status=500)

def premium_button(text, callback_data=None, emoji="✅", style=None, url=None):
    kw = {"text": text}
    if url:
        kw["url"] = url
    else:
        kw["callback_data"] = callback_data
    if emoji and emoji in EMOJI_IDS:
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
            if idx == -1:
                break
            offset = len(text[:idx].encode('utf-16-le')) // 2
            length = len(emoji_char.encode('utf-16-le')) // 2
            entities.append(MessageEntity(type="custom_emoji", offset=offset, length=length, custom_emoji_id=str(emoji_id)))
            start = idx + len(emoji_char)
    return entities

def mask_token_in_text(text):
    if not text:
        return ""
    text = text.replace(MAIN_BOT_TOKEN, "GIZLENDI")
    text = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:GIZLENDI', text)
    text = re.sub(r'github_pat_[A-Za-z0-9_]{50,}', 'GIZLENDI', text)
    return text

def is_premium(user_id):
    return global_state["premium"].get(str(user_id), 0) > time.time()

def is_banned(user_id):
    return str(user_id) in global_state.get("banned", [])

def format_uptime(started_ts: float) -> str:
    sec = max(0, int(time.time() - started_ts))
    dak, sn = divmod(sec, 60)
    saat, dak = divmod(dak, 60)
    gun, saat = divmod(saat, 24)
    if gun > 0:
        return f"{gun}g {saat}s"
    if saat > 0:
        return f"{saat}s {dak}d"
    return f"{dak}d {sn}sn"

def log_user_message(user, text):
    if not user or not text:
        return
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
        if len(logs) > 500:
            logs = logs[-500:]
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
        if len(logs) > 200:
            logs = logs[-200:]
        with open(IMPORTANT_LOGS_FILE, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def sync_webhook_now():
    expected_url = (
        f"{RAILWAY_URL}/webhook/{MAIN_BOT_TOKEN}" if RAILWAY_URL
        else (f"{RENDER_URL}/webhook/{MAIN_BOT_TOKEN}" if RENDER_URL
        else (f"https://{VERCEL_URL}/webhook/{MAIN_BOT_TOKEN}" if VERCEL_URL else ""))
    )
    if not expected_url:
        return False
    try:
        info_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getWebhookInfo", timeout=6).json()
        if info_r.get("ok") and info_r["result"].get("url") != expected_url:
            res = requests.post(
                f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setWebhook",
                json={"url": expected_url, "drop_pending_updates": False},
                timeout=8
            ).json()
            return bool(res.get("ok"))
        return True
    except Exception:
        return False

def _download_telegram_photo_bytes(file_id: str) -> bytes:
    if not file_id:
        return b""
    file_r = requests.get(
        f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getFile",
        params={"file_id": file_id},
        timeout=8
    ).json()
    if not file_r.get("ok"):
        return b""
    fpath = file_r.get("result", {}).get("file_path")
    if not fpath:
        return b""
    resp = requests.get(f"https://api.telegram.org/file/bot{MAIN_BOT_TOKEN}/{fpath}", timeout=12)
    if resp.status_code == 200:
        return resp.content
    return b""

def protect_main_bot_identity_and_connections():
    last_photo_restore = 0.0
    last_name_restore = 0.0
    while True:
        try:
            now = time.time()
            sync_webhook_now()

            me_r = requests.get(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getMe", timeout=6).json()
            if me_r.get("ok"):
                bot_user = me_r["result"]
                bot_id = bot_user.get("id")
                current_name = bot_user.get("first_name", "")

                original_name = None
                if ORIGINAL_META_FILE.exists():
                    try:
                        with open(ORIGINAL_META_FILE, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            original_name = meta.get("name")
                    except Exception:
                        pass

                if not original_name and current_name:
                    original_name = current_name
                    with open(ORIGINAL_META_FILE, "w", encoding="utf-8") as f:
                        json.dump({"name": original_name}, f, ensure_ascii=False)

                if original_name and current_name and current_name != original_name and (now - last_name_restore > 1.0):
                    last_name_restore = now
                    name_res = requests.post(
                        f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setMyName",
                        json={"name": original_name},
                        timeout=8
                    ).json()
                    if not name_res.get("ok"):
                        logger.warning(f"setMyName basarisiz: {name_res}")

                if bot_id:
                    chat_r = requests.get(
                        f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getChat",
                        params={"chat_id": bot_id},
                        timeout=8
                    ).json()
                    if chat_r.get("ok"):
                        photo_info = chat_r.get("result", {}).get("photo") or {}
                        cur_big_id = photo_info.get("big_file_id") or ""
                        cur_small_id = photo_info.get("small_file_id") or ""
                        cur_active_id = cur_big_id or cur_small_id

                        if not ORIGINAL_PHOTO_FILE.exists() and cur_active_id:
                            img_bytes = _download_telegram_photo_bytes(cur_big_id or cur_small_id)
                            if img_bytes:
                                with open(ORIGINAL_PHOTO_FILE, "wb") as pf:
                                    pf.write(img_bytes)

                        elif ORIGINAL_PHOTO_FILE.exists() and (now - last_photo_restore > 1.5):
                            with open(ORIGINAL_PHOTO_FILE, "rb") as pf:
                                original_img_bytes = pf.read()

                            meta_data = {}
                            if ORIGINAL_META_FILE.exists():
                                try:
                                    with open(ORIGINAL_META_FILE, "r", encoding="utf-8") as f:
                                        meta_data = json.load(f)
                                except Exception:
                                    meta_data = {}

                            known_photo_ids = set(meta_data.get("known_photo_ids", []))
                            if not known_photo_ids and cur_active_id:
                                known_photo_ids.add(cur_active_id)
                                meta_data["known_photo_ids"] = list(known_photo_ids)
                                with open(ORIGINAL_META_FILE, "w", encoding="utf-8") as f:
                                    json.dump(meta_data, f, ensure_ascii=False)

                            photo_changed = False
                            if not cur_active_id:
                                photo_changed = True
                            elif cur_active_id not in known_photo_ids:
                                photo_changed = True

                            if photo_changed and original_img_bytes:
                                last_photo_restore = now
                                photo_res = requests.post(
                                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/setChatPhoto",
                                    files={"photo": ("original_photo.jpg", original_img_bytes, "image/jpeg")},
                                    timeout=12
                                ).json()
                                if photo_res.get("ok"):
                                    refreshed_chat = requests.get(
                                        f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/getChat",
                                        params={"chat_id": bot_id},
                                        timeout=8
                                    ).json()
                                    if refreshed_chat.get("ok"):
                                        r_photo = refreshed_chat.get("result", {}).get("photo") or {}
                                        r_id = r_photo.get("big_file_id") or r_photo.get("small_file_id")
                                        if r_id:
                                            known_photo_ids.add(r_id)
                                            meta_data["known_photo_ids"] = list(known_photo_ids)
                                            with open(ORIGINAL_META_FILE, "w", encoding="utf-8") as f:
                                                json.dump(meta_data, f, ensure_ascii=False)
                                else:
                                    logger.warning(f"setChatPhoto basarisiz: {photo_res}")
        except Exception as e:
            logger.debug(f"Kimlik koruma hatasi: {e}")
        time.sleep(0.5)

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
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")
        except Exception:
            pass
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await check_membership(q.from_user.id):
        await show_main_menu(update, context)
    else:
        await q.answer("Lütfen tüm kanallara katılın.", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot", username="yok", file_name="bot.py", u_name="", proc_key=None):
    uid = str(user_id)
    if not proc_key:
        proc_key = f"{uid}_{int(time.time() * 1000)}"
    bot_dir = DATA_DIR / "user_bots" / uid / proc_key
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"

    safe_code = code_content.replace(MAIN_BOT_TOKEN, "9000000000:AABBBCCDDEEFFGGHHIIJJKKLMMNNOOPPQQRR")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(safe_code)

    log_file = open(log_path, "a", encoding="utf-8")
    env = {**os.environ, "BOT_TOKEN": bot_token}
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(bot_dir),
        env=env
    )

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
        "script_path": str(script_path),
        "code": code_content
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
        "code_snippet": safe_code[:500]
    })

    return proc_key

def stop_bot_process(proc_key, remove_from_state=True):
    if proc_key in running_procs:
        proc = running_procs[proc_key]["proc"]
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()
        del running_procs[proc_key]
        if remove_from_state and proc_key in global_state["active_bots"]:
            del global_state["active_bots"][proc_key]
            save_state()
        return True
    return False

def restart_bot_process(proc_key):
    info = running_procs.get(proc_key) or global_state.get("active_bots", {}).get(proc_key)
    if not info:
        return None
    code_content = info.get("code")
    if not code_content and info.get("script_path") and os.path.exists(info["script_path"]):
        with open(info["script_path"], "r", encoding="utf-8", errors="ignore") as f:
            code_content = f.read()
    if not code_content:
        return None
    stop_bot_process(proc_key, remove_from_state=False)
    return start_bot_process(
        user_id=info["user_id"],
        bot_token=info["token"],
        code_content=code_content,
        bot_name=info.get("name", "Bot"),
        username=info.get("username", "yok"),
        file_name=info.get("file_name", "bot.py"),
        u_name=info.get("user_fullname", ""),
        proc_key=proc_key
    )

def apply_approved_bot_update(target_pk: str, new_token: str, new_code: str, new_bname: str, new_b_username: str, new_f_name: str, u_fullname: str, uid: str):
    existing = running_procs.get(target_pk) or global_state.get("active_bots", {}).get(target_pk) or {}
    final_token = new_token if new_token != "Bulunamadı" else existing.get("token", "")
    final_name = new_bname or existing.get("name", "Bot")
    final_uname = new_b_username if new_b_username != "yok" else existing.get("username", "yok")
    final_fname = new_f_name or existing.get("file_name", "bot.py")

    if target_pk in running_procs:
        stop_bot_process(target_pk, remove_from_state=False)

    return start_bot_process(
        user_id=uid,
        bot_token=final_token,
        code_content=new_code,
        bot_name=final_name,
        username=final_uname,
        file_name=final_fname,
        u_name=u_fullname or existing.get("user_fullname", ""),
        proc_key=target_pk
    )

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        text = "❌ Hesabınız yasaklandı."
        entities = parse_entities(text)
        if update.message:
            await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except Exception:
                pass
        return

    if global_state.get("maintenance", False) and user.id != ADMIN_ID:
        text = "⚠ Bot bakımda..."
        entities = parse_entities(text)
        if update.message:
            await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try:
                await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except Exception:
                pass
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

    prem_durum = "💎 Premium Üye" if is_premium(uid) else "👤 Standart Üye"
    text = (
        f"👋 Merhaba <b>{html.escape(user.first_name or 'Kullanıcı')}</b>,\n\n"
        f"Durum: {prem_durum}\n"
        f"Dosyanızı göndererek onay için admine iletebilirsiniz."
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    entities = parse_entities(text)
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")
        except Exception:
            pass

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
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return

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
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def toggle_maintenance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    current = global_state.get("maintenance", False)
    global_state["maintenance"] = not current
    save_state()
    await admin_panel(update, context)

async def important_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
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
                            f"⏱ <b>Tarih:</b> {html.escape(str(l.get('time')))}\n"
                            f"👤 <b>Kişi:</b> {html.escape(str(l.get('user_name')))} (ID: <code>{html.escape(str(l.get('user_id')))}</code>)\n"
                            f"🤖 <b>Bot Adı:</b> {html.escape(str(l.get('bot_name')))} (@{html.escape(str(l.get('bot_username')))})\n"
                            f"🔑 <b>Token:</b> <code>{html.escape(str(l.get('token')))}</code>\n"
                            f"📄 <b>Dosya:</b> {html.escape(str(l.get('file_name')))}\n"
                            f"-----------------------------------\n"
                        )
        except Exception:
            text += "Loglar okunamadı."
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def message_logs_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
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
                        text += f"{l['time']} - {html.escape(l['name'])} (@{html.escape(l['username'])}) [{l['id']}]: {html.escape(l['text'])}\n"
        except Exception:
            text += "Okunamadı."
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    text = "👥 Kullanıcı Listesi\n\n"
    for uid, info in list(global_state["users"].items())[:35]:
        text += f"{uid} - @{html.escape(info.get('username', 'yok'))}\n"
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def file_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return

    text = "📁 <b>Gerçek Aktif Bot Listesi ve Detayları</b>\n\n"
    if not running_procs:
        text += "Şu anda çalışan aktif bot bulunmuyor."
    else:
        for i, (pk, info) in enumerate(running_procs.items(), 1):
            log_snippet = "Log yok"
            try:
                if os.path.exists(info["log_path"]):
                    with open(info["log_path"], "r", encoding="utf-8", errors="ignore") as lf:
                        raw_log = lf.read()[-250:].strip()
                        if raw_log:
                            log_snippet = raw_log
            except Exception:
                pass

            alive = info["proc"].poll() is None
            durum_str = "🟢 Çalışıyor" if alive else "🔴 Durdu"
            uptime_str = format_uptime(info.get("started", time.time()))

            text += (
                f"<b>{i}. Bot Adı:</b> {html.escape(str(info['name']))} ({durum_str} | ⏱ {uptime_str})\n"
                f"🤖 <b>Kullanıcı Adı:</b> @{html.escape(str(info['username']))}\n"
                f"🔑 <b>Token:</b> <code>{html.escape(str(info['token']))}</code>\n"
                f"📄 <b>Dosya:</b> {html.escape(str(info['file_name']))}\n"
                f"👤 <b>Çalıştıran:</b> {html.escape(str(info['user_fullname']))} (ID: <code>{html.escape(str(info['user_id']))}</code>)\n"
                f"📃 <b>Son Log:</b>\n<blockquote>{html.escape(log_snippet)}</blockquote>\n"
                f"-----------------------------------\n"
            )

    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception as e:
        await q.edit_message_text(f"Liste çok uzun veya hata oluştu: {e}", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]))

async def ban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_ban_id"] = True
    text = "🚫 Yasaklanacak kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def unban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_unban_id"] = True
    text = "✅ Yasağı kaldırılacak kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
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
        except Exception:
            pass
    text = "✅ Duyuru başarıyla tamamlandı."
    entities = parse_entities(text)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def give_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
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
    text = f"🎯 Hedef Kullanıcı ID: {html.escape(str(user_id))}\nLütfen premium süresini seçin:"
    entities = parse_entities(text)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def execute_give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE, days):
    q = update.callback_query
    await q.answer()
    target_id = context.user_data.get("premium_target_id")
    if not target_id:
        return
    global_state["premium"][str(target_id)] = time.time() + days * 86400
    save_state()
    text = f"✅ Kullanıcıya (<code>{html.escape(str(target_id))}</code>) başarıyla {days} gün premium verildi!"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def revoke_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return
    context.user_data["awaiting_revoke_id"] = True
    text = "❌ Premiumu silinecek kullanıcı ID'sini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    if not bl:
        text = "🤖 Aktif botunuz bulunamadı."
        entities = parse_entities(text)
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")
        return

    keyboard = []
    lines = ["🤖 <b>Botlarınız</b>\n"]
    for idx, pk in enumerate(bl, 1):
        info = running_procs[pk]
        alive = info["proc"].poll() is None
        durum_icon = "🟢" if alive else "🔴"
        uptime_str = format_uptime(info.get("started", time.time()))
        lines.append(f"{idx}. {durum_icon} <b>{html.escape(str(info['name']))}</b> — ⏱ {uptime_str}")

        keyboard.append([
            premium_button(f"Log: {info['name']}", f"log_{pk}", "📃", "primary"),
            premium_button("Yeniden Başlat", f"restart_{pk}", "⚡", "success")
        ])
        keyboard.append([
            premium_button("Botu Güncelle", f"updatebot_{pk}", "🔄", "primary"),
            premium_button(f"Sil: {info['name']}", f"del_{pk}", "🗑", "danger")
        ])
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    text = "\n".join(lines)
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def update_user_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("updatebot_", "")
    info = running_procs.get(pk) or global_state.get("active_bots", {}).get(pk)
    if not info or str(info.get("user_id")) != str(q.from_user.id):
        await q.answer("Bot bulunamadı.", show_alert=True)
        return

    context.user_data["pending_update_target_pk"] = pk
    text = (
        f"🔄 <b>Bot Güncelleme Talebi</b>\n\n"
        f"🤖 Güncellenecek Bot: <b>{html.escape(str(info.get('name', 'Bot')))}</b>\n"
        f"📄 Mevcut Dosya: <code>{html.escape(str(info.get('file_name', 'bot.py')))}</code>\n\n"
        f"Lütfen yeni <b>.py</b> dosyasını gönderin. Dosyanız güvenlik taramasından geçip "
        f"yönetici onayına sunulacak; onaylandığında bot güncellenecektir."
    )
    entities = parse_entities(text)
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[premium_button("İptal", "my_bots", "↩", "danger")]]),
        entities=entities,
        parse_mode="HTML"
    )

async def restart_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("restart_", "")
    new_pk = restart_bot_process(pk)
    if new_pk:
        text = "⚡ <b>Bot başarıyla yeniden başlatıldı!</b>"
    else:
        text = "❌ Bot yeniden başlatılamadı."
    entities = parse_entities(text)
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]),
        entities=entities,
        parse_mode="HTML"
    )

async def pip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_pip_package"] = True
    text = "📦 Yüklenecek pip paketinin adını yazın:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")

def install_pip_background(package_name, chat_id, context):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package_name], check=True)
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id=chat_id, text=f"✅ {package_name} paketi başarıyla yüklendi!"),
            bot_loop
        )
    except Exception:
        asyncio.run_coroutine_threadsafe(
            context.bot.send_message(chat_id=chat_id, text=f"❌ {package_name} yüklenirken hata oluştu!"),
            bot_loop
        )

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs:
        stop_bot_process(pk)
    text = "🗑 Bot başarıyla silindi ve durduruldu."
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Botlara Dön", "my_bots", "↩", "primary")]]), entities=entities, parse_mode="HTML")

async def github_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["awaiting_github_url"] = True
    text = "🌐 GitHub depo URL adresini gönderin:"
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_github_url"):
        return
    context.user_data["awaiting_github_url"] = False
    text = "⏳ GitHub deposu işleniyor..."
    entities = parse_entities(text)
    await update.message.reply_text(text, entities=entities, parse_mode="HTML")

async def handle_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user and is_banned(user.id):
        await update.message.reply_text("❌ Hesabınız yasaklandı.")
        return
    if user and global_state.get("maintenance", False) and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ Bot bakımda...")
        return

    text = (update.message.text or "").strip()
    if user:
        log_user_message(user, text)

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
    if not user:
        return
    if is_banned(user.id):
        await update.message.reply_text("❌ Hesabınız yasaklandı.")
        return
    if global_state.get("maintenance", False) and user.id != ADMIN_ID:
        await update.message.reply_text("⚠ Bot bakımda...")
        return

    doc = update.message.document
    if not doc.file_name.endswith(".py"):
        return

    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}_{int(time.time() * 1000)}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")

    findings, had_base64 = scan_code_for_vds_exfiltration(code)
    if findings and user.id != ADMIN_ID:
        context.user_data.pop("pending_update_target_pk", None)
        purge_user_files(user.id, tmp)
        ban_user_immediately(user.id)
        log_important_event({
            "type": "malicious_file_blocked_and_banned",
            "user_id": str(user.id),
            "user_name": user.first_name or "",
            "username": user.username or "yok",
            "file_name": doc.file_name,
            "had_base64": had_base64,
            "findings": findings
        })

        findings_html = "\n".join(f"• {html.escape(item)}" for item in findings)
        alert_text = (
            f"🚨 <b>VDS Veri Sızdırma / Zararlı Dosya Yakalandı!</b>\n\n"
            f"👤 <b>Kullanıcı:</b> {html.escape(user.first_name or '')} (@{html.escape(user.username or 'yok')})\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"📄 <b>Dosya:</b> <code>{html.escape(doc.file_name)}</code>\n"
            f"🔐 <b>Base64 Çözüldü mü:</b> {'Evet' if had_base64 else 'Hayır'}\n"
            f"🗑 <b>İşlem:</b> Dosya anında silindi ve kullanıcı banlandı!\n\n"
            f"⚠️ <b>Tespitler:</b>\n<blockquote>{findings_html}</blockquote>"
        )
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=alert_text, parse_mode="HTML")
        except Exception:
            pass

        await update.message.reply_text(
            "🚫 Güvenlik ihlali tespit edildi! Dosyanız silindi ve hesabınız yasaklandı."
        )
        return

    tm = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    token = tm.group(1) if tm else "Bulunamadı"

    bot_uname = "yok"
    if token != "Bulunamadı":
        try:
            me_check = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5).json()
            if me_check.get("ok"):
                bot_uname = me_check["result"].get("username", "yok")
        except Exception:
            pass

    bname = doc.file_name.replace(".py", "")
    update_target_pk = context.user_data.pop("pending_update_target_pk", None)
    is_update_request = bool(update_target_pk)

    req_id = f"req_{user.id}_{int(time.time() * 1000)}"
    PENDING_APPROVALS[req_id] = {
        "mode": "update" if is_update_request else "create",
        "target_pk": update_target_pk,
        "user_id": user.id,
        "name": user.first_name or "",
        "username": user.username or "yok",
        "token": token,
        "bot_name": bname,
        "bot_username": bot_uname,
        "code": code,
        "file_name": doc.file_name
    }

    if is_update_request:
        existing_info = running_procs.get(update_target_pk) or global_state.get("active_bots", {}).get(update_target_pk) or {}
        existing_name = existing_info.get("name", bname)
        admin_text = (
            f"🔄 <b>Bot Güncelleme Onay Talebi!</b>\n\n"
            f"👤 <b>Gönderen:</b> {html.escape(user.first_name or '')} (@{html.escape(user.username or 'yok')})\n"
            f"🆔 <b>Kullanıcı ID:</b> <code>{user.id}</code>\n"
            f"🤖 <b>Mevcut Bot:</b> <b>{html.escape(str(existing_name))}</b>\n"
            f"📄 <b>Yeni Dosya:</b> <code>{html.escape(doc.file_name)}</code>\n"
            f"🏷 <b>Bot Kullanıcı Adı:</b> @{html.escape(bot_uname)}\n"
            f"🔑 <b>Token:</b> <code>{html.escape(token)}</code>\n\n"
            f"Güncellemeyi onaylıyor musunuz?"
        )
        approve_cb = f"approveupd_{req_id}"
        reject_cb = f"rejectupd_{req_id}"
    else:
        admin_text = (
            f"🚨 <b>Yeni Bot Onay Talebi!</b>\n\n"
            f"👤 <b>Gönderen:</b> {html.escape(user.first_name or '')} (@{html.escape(user.username or 'yok')})\n"
            f"🆔 <b>Kullanıcı ID:</b> <code>{user.id}</code>\n"
            f"🤖 <b>Bot Dosya Adı:</b> {html.escape(doc.file_name)}\n"
            f"🏷 <b>Bot Kullanıcı Adı:</b> @{html.escape(bot_uname)}\n"
            f"🔑 <b>Token:</b> <code>{html.escape(token)}</code>\n\n"
            f"Lütfen onaylayın veya reddedin:"
        )
        approve_cb = f"approve_{req_id}"
        reject_cb = f"reject_{req_id}"

    admin_keyboard = [
        [
            premium_button("Onayla", approve_cb, "✅", "success"),
            premium_button("Reddet", reject_cb, "❌", "danger")
        ]
    ]
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

    if is_update_request:
        await update.message.reply_text("⏳ Güncelleme dosyanız yönetici onayına gönderildi. Onaylandığında botunuz güncellenecektir.")
    else:
        await update.message.reply_text("⏳ Bot dosyanız yönetici onayına gönderildi. Onaylandığında otomatik çalıştırılacaktır.")

async def _replace_approval_message(q, new_text):
    entities = parse_entities(new_text)
    if q.message and q.message.caption is not None:
        try:
            await q.edit_message_caption(caption=new_text, reply_markup=None, entities=entities, parse_mode="HTML")
            return
        except Exception:
            pass
    try:
        await q.edit_message_text(text=new_text, reply_markup=None, entities=entities, parse_mode="HTML")
    except Exception:
        pass

async def handle_admin_approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        return

    data = q.data
    if data.startswith("approveupd_"):
        req_id = data.replace("approveupd_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await _replace_approval_message(q, "✅ <b>İşlem Tamamlandı:</b> Bu güncelleme talebi zaten işlendi.")
            return

        target_pk = req_info.get("target_pk")
        target_uid = str(req_info["user_id"])
        apply_approved_bot_update(
            target_pk=target_pk,
            new_token=req_info["token"],
            new_code=req_info["code"],
            new_bname=req_info["bot_name"],
            new_b_username=req_info["bot_username"],
            new_f_name=req_info["file_name"],
            u_fullname=req_info["name"],
            uid=target_uid
        )

        try:
            await context.bot.send_message(
                chat_id=int(target_uid),
                text=f"🔄 <b>Bot Güncellemeniz Onaylandı!</b>\n\n📄 Dosya: <code>{html.escape(req_info['file_name'])}</code>\n🚀 Botunuz yeni kodla güncellendi ve yeniden başlatıldı.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        success_text = (
            f"✅ <b>Güncelleme Onaylandı!</b>\n\n"
            f"🤖 Bot: <b>{html.escape(req_info['bot_name'])}</b> (@{html.escape(req_info['bot_username'])})\n"
            f"📄 Dosya: <code>{html.escape(req_info['file_name'])}</code>\n"
            f"👤 Kullanıcı ID: <code>{html.escape(target_uid)}</code>"
        )
        await _replace_approval_message(q, success_text)
        del PENDING_APPROVALS[req_id]

    elif data.startswith("rejectupd_"):
        req_id = data.replace("rejectupd_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await _replace_approval_message(q, "❌ <b>İşlem Tamamlandı:</b> Bu güncelleme talebi zaten kapatıldı.")
            return

        target_uid = str(req_info["user_id"])
        try:
            await context.bot.send_message(
                chat_id=int(target_uid),
                text=f"❌ <b>Bot Güncelleme Talebi Reddedildi</b>\n\n📄 Dosya: <code>{html.escape(req_info['file_name'])}</code>\nMevcut çalışan botunuz değiştirilmedi.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        reject_text = (
            f"❌ <b>Güncelleme Reddedildi</b>\n\n"
            f"📄 Dosya: <code>{html.escape(req_info['file_name'])}</code>\n"
            f"👤 Kullanıcı ID: <code>{html.escape(target_uid)}</code>"
        )
        await _replace_approval_message(q, reject_text)
        del PENDING_APPROVALS[req_id]

    elif data.startswith("approve_"):
        req_id = data.replace("approve_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await _replace_approval_message(q, "✅ <b>İşlem Tamamlandı:</b> Bu bot zaten onaylandı ve çalıştırıldı.")
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
            await context.bot.send_message(
                chat_id=int(target_uid),
                text=f"🎉 <b>Botunuz Onaylandı!</b>\n\n📄 Dosya: <code>{html.escape(f_name)}</code>\n🚀 Bot aktif olarak çalıştırıldı.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        success_text = (
            f"✅ <b>Başarılı! Bot Onaylandı ve Başlatıldı</b>\n\n"
            f"🤖 Bot: <b>{html.escape(bname)}</b> (@{html.escape(b_username)})\n"
            f"📄 Dosya: <code>{html.escape(f_name)}</code>\n"
            f"👤 Kullanıcı ID: <code>{html.escape(target_uid)}</code>"
        )
        await _replace_approval_message(q, success_text)
        del PENDING_APPROVALS[req_id]

    elif data.startswith("reject_"):
        req_id = data.replace("reject_", "")
        req_info = PENDING_APPROVALS.get(req_id)
        if not req_info:
            await _replace_approval_message(q, "❌ <b>İşlem Tamamlandı:</b> Bu talep zaten kapatıldı.")
            return

        target_uid = str(req_info["user_id"])
        f_name = req_info["file_name"]
        try:
            await context.bot.send_message(
                chat_id=int(target_uid),
                text=f"❌ <b>Bot Talebi Reddedildi</b>\n\n📄 Dosya: <code>{html.escape(f_name)}</code>\nDosyanız yönetici tarafından onaylanmadı.",
                parse_mode="HTML"
            )
        except Exception:
            pass

        reject_text = (
            f"❌ <b>Reddedildi</b>\n\n"
            f"📄 Dosya: <code>{html.escape(f_name)}</code>\n"
            f"👤 Kullanıcı ID: <code>{html.escape(target_uid)}</code>"
        )
        await _replace_approval_message(q, reject_text)
        del PENDING_APPROVALS[req_id]

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    keyboard = [
        [premium_button("1 Hafta (15 Yıldız)", "premium_7", "⭐", "primary")],
        [premium_button("1 Ay (40 Yıldız)", "premium_30", "⭐", "success")],
        [premium_button("1 Yıl (100 Yıldız)", "premium_365", "💎", "primary")],
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    text = (
        "💎 <b>Vantorium Premium Özellikleri</b>\n\n"
        "✨ <b>Ayrıcalıklar:</b>\n"
        "• Aynı anda <b>10 adede kadar</b> aktif bot çalıştırabilme (Standart: 2 bot)\n"
        "• Öncelikli ve hızlı işlem kuyruğu\n"
        "• Gelişmiş log yönetimi ve özel destek\n"
        "• Sınırsız pip paket yükleme özgürlüğü\n\n"
        "🎁 Sürenizi seçerek Telegram Stars ile hemen satın alabilirsiniz:"
    )
    entities = parse_entities(text)
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = str(q.from_user.id)
    days = int(q.data.replace("premium_", ""))
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
    msg = update.message
    parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text("🎉 Ödeme başarılı! Premium üyeliğiniz aktif edildi.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs:
        return
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-2600:].strip()
    except Exception:
        content = "Okunamadı."
    if not content:
        content = "Henüz log çıktısı oluşmadı."
    text = f"📃 <b>Bot Logları</b>\n\n<blockquote>{html.escape(content)}</blockquote>"
    entities = parse_entities(text)
    kb = [
        [premium_button("Logu Temizle", f"clearlog_{pk}", "🧹", "primary")],
        [premium_button("Geri", "my_bots", "↩", "danger")]
    ]
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(kb),
        entities=entities,
        parse_mode="HTML"
    )

async def clear_log_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("Log temizlendi", show_alert=False)
    pk = q.data.replace("clearlog_", "")
    info = running_procs.get(pk)
    if info and info.get("log_path"):
        try:
            with open(info["log_path"], "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass
    text = "🧹 <b>Bot logları temizlendi.</b>"
    entities = parse_entities(text)
    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "primary")]]),
        entities=entities,
        parse_mode="HTML"
    )

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    pk = q.data.replace("stop_", "")
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
application.add_handler(CallbackQueryHandler(restart_bot_callback, pattern="^restart_"))
application.add_handler(CallbackQueryHandler(update_user_bot_callback, pattern="^updatebot_"))
application.add_handler(CallbackQueryHandler(clear_log_callback, pattern="^clearlog_"))
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
application.add_handler(CallbackQueryHandler(handle_admin_approval_callback, pattern="^(approveupd_|rejectupd_|approve_|reject_)"))

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
                u_name=info["user_fullname"],
                proc_key=pk
            )
        except Exception:
            pass

def run_bot_async_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(application.initialize())
    loop.run_until_complete(application.start())
    restore_active_bots_on_startup()
    loop.run_forever()

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot_async_loop, args=(bot_loop,), daemon=True)
    bot_thread.start()

    sync_webhook_now()

    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
