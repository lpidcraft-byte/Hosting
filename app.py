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
import base64
from pathlib import Path
from flask import Flask, request, Response

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

# --- Ayarlar ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9053394489:AAEMkxfOuDRVTcTY4mWluMgNdDbj-Y9ryMY")
ADMIN_ID = 8913966694
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

REQUIRED_CHANNELS = [
    {"id": -1003947388912, "link": "https://t.me/+3A7s7kVfaoMxYjM0", "name": "𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 𝗧𝗘𝗔𝗠 #𝐊𝐫𝐚𝐥𝐥𝐢𝐤"},
    {"id": -1004443368027, "link": "https://t.me/vantoriumchat", "name": "𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 TEAM sohbet"}
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
    "🌐": 5821388137443626414,
}

DATA_DIR = Path("/tmp/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"

def load_state():
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: pass
    return {"users": {}, "premium": {}, "bot_codes": {}}

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(global_state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Dosya kayıt hatası: {e}")

global_state = load_state()
running_procs = {}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

application = Application.builder().token(BOT_TOKEN).updater(None).build()
bot_loop = asyncio.new_event_loop()

flask_app = Flask(__name__)

@flask_app.route("/", methods=["GET"])
def health():
    return "Bot is running", 200

@flask_app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run_coroutine_threadsafe(application.update_queue.put(update), bot_loop)
        return Response("OK", status=200)
    except Exception as e:
        logger.error(f"Webhook hatası: {e}")
        return Response("Error", status=500)

def premium_button(text, callback_data=None, emoji="✅", style=None, url=None):
    kw = {"text": text}
    if url:
        kw["url"] = url
    else:
        kw["callback_data"] = callback_data
    if emoji in EMOJI_IDS:
        kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style:
        kw["style"] = style
    return InlineKeyboardButton(**kw)

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

def is_premium(user_id):
    return global_state["premium"].get(str(user_id), 0) > time.time()

def check_bot_limit(user_id):
    uid = str(user_id)
    count = sum(1 for k in running_procs if k.startswith(uid + "_"))
    return count < (5 if is_premium(uid) else 1)

async def check_membership(user_id: int) -> bool:
    for ch in REQUIRED_CHANNELS:
        try:
            member = await application.bot.get_chat_member(chat_id=ch["id"], user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except Exception as e:
            logger.error(f"Kanal kontrol hatası ({ch['name']}): {e}")
            return False
    return True

async def send_join_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for ch in REQUIRED_CHANNELS:
        keyboard.append([premium_button(f"Katıl: {ch['name']}", emoji="📢", style="primary", url=ch["link"])])
    keyboard.append([premium_button("✅ Kontrol Et", "check_join", "✅", "success")])
    
    text = (
        "⚠️ **Zorunlu Kanal Üyeliği**\n\n"
        "Botu kullanabilmek için aşağıdaki kanallara katılman gerekiyor:\n\n"
        "1️⃣ **𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 𝗧𝗘𝗔𝗠 #𝐊𝐫𝐚𝐥𝐥𝐢𝐤** (Kanal)\n"
        "2️⃣ **𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 TEAM sohbet** (Grup)\n\n"
        "Katıldıktan sonra **Kontrol Et** butonuna bas."
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
        except: pass
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if await check_membership(q.from_user.id):
        await show_main_menu(update, context)
    else:
        await q.answer("❌ Henüz tüm kanallara katılmadın!", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot"):
    uid = str(user_id)
    proc_key = f"{uid}_{int(time.time())}"
    bot_dir = DATA_DIR / "user_bots" / uid
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot_{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"
    
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code_content)
        
    log_file = open(log_path, "w", encoding="utf-8")
    env = {**os.environ, "BOT_TOKEN": bot_token}
    proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
    running_procs[proc_key] = {
        "proc": proc, 
        "log_path": str(log_path), 
        "token": bot_token, 
        "started": time.time(), 
        "user_id": uid,
        "name": bot_name
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
    if update.message:
        uid = str(user.id)
        global_state["users"][uid] = {"username": user.username or "", "first_name": user.first_name or ""}
        save_state()
    
    keyboard = []
    if user.id == ADMIN_ID:
        keyboard.append([premium_button("Admin Paneli", "admin_panel", "👮‍♀", "primary")])
    keyboard.append([premium_button("GitHub'dan Bot Aktif Et", "github_start", "🌐", "success")])
    keyboard.append([premium_button("Botlarım", "my_bots", "🤖", "success")])
    keyboard.append([premium_button("Premium Al", "buy_premium", "💎", "primary")])
    keyboard.append([premium_button("Pip İndir", "pip_menu", "📦", "primary")])
    keyboard.append([premium_button("Kanalı Ziyaret Et", emoji="🚀", style="success", url="https://t.me/+3A7s7kVfaoMxYjM0")])
    
    text = (
        f"👋 **Merhaba {user.first_name}!**\n\n"
        "🤖 **VDS Bot Hosting Hizmeti**\n"
        "Kendi botlarını 7/24 çalıştır, loglarını anlık görüntüle.\n\n"
        "🌐 **GitHub Desteği**\n"
        "GitHub repo URL'ni gönder, içindeki botu otomatik bulup çalıştıralım.\n\n"
        "📦 **Pip Desteği**\n"
        "Eksik modülleri tek tıkla yükle, hata almadan botunu çalıştır.\n\n"
        "💎 **Premium Avantajları**\n"
        "Sıra beklemeden anında onay, 5 bota kadar çalıştırma izni.\n\n"
        "👇 **Hemen başla**\n"
        "Botunu çalıştırmak için `.py` uzantılı dosyanı buraya gönder."
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    entities = parse_entities(text)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities)
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities)
        except Exception as e:
            logger.error(f"Menü hatası: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id):
        await send_join_message(update, context)
        return
    await show_main_menu(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return await q.edit_message_text("⛔ Yetkisiz.")
    text = "👮‍♀ **Admin Paneli**\n\nAşağıdaki işlemlerden birini seçebilirsin:"
    keyboard = [[premium_button("Kullanıcı Listesi", "user_list", "👥", "primary")], [premium_button("Geri", "back_start", "↩", "danger")]]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities)
    except: pass

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "👥 **Kullanıcı Listesi**\n\n"
    for uid, info in list(global_state["users"].items())[:50]:
        ps = "💎" if is_premium(uid) else ""
        text += f"🆔 `{uid}` | @{info.get('username','yok')} | {info.get('first_name','')} {ps}\n"
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities)
    except: pass

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    
    if not bl:
        text = "🤖 **Bot Bulunamadı**\n\nHenüz bir bot yüklemedin. Çalıştırmak için `.py` dosyanı gönder veya GitHub URL'si ile aktif et."
        entities = parse_entities(text)
        try:
            return await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities)
        except: return
    
    keyboard = []
    text = "🤖 **Aktif Botlarınız**\n\n"
    for i, pk in enumerate(bl):
        st = "🟢 Çalışıyor" if running_procs[pk]["proc"].poll() is None else "🔴 Durdu"
        text += f"📦 **{running_procs[pk]['name']}** - {st}\n"
        if running_procs[pk]["proc"].poll() is None:
            keyboard.append([premium_button(f"Log Al: {running_procs[pk]['name']}", f"log_{pk}", "📃", "primary")])
            keyboard.append([premium_button(f"Durdur: {running_procs[pk]['name']}", f"stop_{pk}", "⏹", "danger")])
        else:
            keyboard.append([premium_button(f"Log Al: {running_procs[pk]['name']}", f"log_{pk}", "📃", "primary")])
            keyboard.append([premium_button(f"Başlat: {running_procs[pk]['name']}", f"start_{pk}", "▶", "success")])
            keyboard.append([premium_button(f"Sil: {running_procs[pk]['name']}", f"del_{pk}", "🗑", "danger")])
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities)
    except Exception as e:
        logger.error(f"Bot listesi hatası: {e}")

async def pip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (
        "📦 **Pip Paket İndirici**\n\n"
        "Alt botlarında eksik modül hatası mı alıyorsun?\n\n"
        "🔍 **Nasıl Kullanılır?**\n"
        "Aşağıya indirmek istediğin paketin adını yaz. Örnek: `aiohttp`, `beautifulsoup4`\n\n"
        "⚡ **Hız**\n"
        "Paketler arka planda indirilir, botun donmaz.\n\n"
        "👇 **Hemen başla**\n"
        "Paket adını mesaj olarak yaz."
    )
    keyboard = [[premium_button("Geri", "back_start", "↩", "danger")]]
    context.user_data["awaiting_pip_package"] = True
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities)
    except: pass

def install_pip_background(package_name, chat_id, context):
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package_name], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"✅ `{package_name}` başarıyla yüklendi!"), bot_loop)
        else:
            asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"❌ Hata:\n\n```\n{result.stderr[-1000:]}\n```", parse_mode="Markdown"), bot_loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"❌ İşlem hatası: {e}"), bot_loop)

async def handle_pip_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_pip_package"): return
    package_name = update.message.text.strip()
    if not re.match(r"^[a-zA-Z0-9_\-]+$", package_name):
        return await update.message.reply_text("❌ Geçersiz paket adı!")
    context.user_data["awaiting_pip_package"] = False
    await update.message.reply_text(f"⏳ `{package_name}` arka planda yükleniyor...", parse_mode="Markdown")
    threading.Thread(target=install_pip_background, args=(package_name, update.effective_chat.id, context)).start()

async def start_stopped_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("start_", "")
    if pk in running_procs:
        info = running_procs[pk]
        bot_dir = DATA_DIR / "user_bots" / info["user_id"]
        script_path = bot_dir / f"bot_{pk}.py"
        if script_path.exists():
            log_file = open(info["log_path"], "a", encoding="utf-8")
            proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env={**os.environ, "BOT_TOKEN": info["token"]})
            running_procs[pk]["proc"] = proc
            try:
                await q.edit_message_text(f"▶ Bot yeniden başlatıldı: `{info['name']}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
            except: pass
        else: 
            try: await q.edit_message_text("❌ Bot dosyası bulunamadı.")
            except: pass
    else: 
        try: await q.edit_message_text("❌ Bot bulunamadı.")
        except: pass

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs:
        info = running_procs[pk]
        if info["proc"].poll() is None: info["proc"].terminate()
        del running_procs[pk]
        try:
            await q.edit_message_text(f"🗑 Bot silindi: `{info['name']}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
        except: pass
    else: 
        try: await q.edit_message_text("❌ Bot zaten yok.")
        except: pass

# --- GITHUB URL İLE BOT AKTİF ETME ---
async def github_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_github_url"] = True
    text = (
        "🌐 **GitHub'dan Bot Aktif Etme**\n\n"
        "GitHub repo URL'sini gönder. Örnek:\n"
        "`https://github.com/kullanici/repo`\n\n"
        "🔍 Repo içindeki `.py` dosyaları taranır, içinde geçerli Telegram token olan dosya bulunur ve bot doğrulanarak çalıştırılır.\n\n"
        "⚠️ Token'ın şu formatta olmalı: `123456789:AA...`\n\n"
        "👇 URL'yi mesaj olarak yaz."
    )
    keyboard = [[premium_button("Geri", "back_start", "↩", "danger")]]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities)
    except: pass

def github_repo_api(url):
    """GitHub URL'sinden API endpoint üret"""
    url = url.strip().rstrip("/")
    # https://github.com/user/repo veya https://github.com/user/repo/tree/branch
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)(?:/tree/([^/]+))?", url)
    if not m:
        return None, None, None
    user, repo, branch = m.group(1), m.group(2), m.group(3)
    return user, repo, branch

def fetch_github_files(user, repo, branch=None):
    """Repo içeriğini GitHub API ile getir"""
    headers = {"Accept": "application/vnd.github+json"}
    if branch is None:
        # varsayılan branch'i öğren
        r = requests.get(f"https://api.github.com/repos/{user}/{repo}", headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"Repo bulunamadı veya erişilemedi (HTTP {r.status_code})"
        branch = r.json().get("default_branch", "main")
    r = requests.get(f"https://api.github.com/repos/{user}/{repo}/git/trees/{branch}?recursive=1", headers=headers, timeout=20)
    if r.status_code != 200:
        return None, f"Dosya listesi alınamadı (HTTP {r.status_code})"
    return r.json().get("tree", []), None

def download_github_file(user, repo, branch, path):
    """Tek dosyayı raw olarak indir"""
    url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    r = requests.get(url, timeout=20)
    if r.status_code == 200:
        return r.text
    return None

def extract_and_validate_token(code):
    """Kod içinden geçerli Telegram token bul ve doğrula"""
    # Rakamla başlayıp harf/rakam/altçizgi/tire ile devam eden token formatı
    matches = re.findall(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    for token in matches:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            data = r.json()
            if data.get("ok"):
                bot_info = data["result"]
                return token, bot_info.get("first_name", "Bot"), bot_info.get("username", "")
        except:
            continue
    return None, None, None

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_github_url"):
        return
    context.user_data["awaiting_github_url"] = False
    url = update.message.text.strip()
    user_id = update.effective_user.id
    uid = str(user_id)
    
    if not check_bot_limit(uid):
        return await update.message.reply_text("⚠️ Bot limitin doldu! Premium alman lazım.")
    
    user, repo, branch = github_repo_api(url)
    if not user:
        return await update.message.reply_text("❌ Geçersiz GitHub URL. Örnek: `https://github.com/kullanici/repo`", parse_mode="Markdown")
    
    msg = await update.message.reply_text("🔍 Repo taranıyor, lütfen bekle...")
    
    # Arka planda işle
    def process():
        try:
            files, err = fetch_github_files(user, repo, branch)
            if err:
                asyncio.run_coroutine_threadsafe(msg.edit_text(f"❌ {err}"), bot_loop)
                return
            
            py_files = [f for f in files if f["type"] == "blob" and f["path"].endswith(".py")]
            if not py_files:
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ Repo içinde `.py` dosyası bulunamadı."), bot_loop)
                return
            
            asyncio.run_coroutine_threadsafe(msg.edit_text(f"📂 {len(py_files)} Python dosyası bulundu, token aranıyor..."), bot_loop)
            
            found = None
            for f in py_files[:30]:  # max 30 dosya tara
                content = download_github_file(user, repo, branch or "main", f["path"])
                if not content:
                    continue
                token, bot_name, bot_username = extract_and_validate_token(content)
                if token:
                    found = (f["path"], content, token, bot_name, bot_username)
                    break
            
            if not found:
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ Repo içinde geçerli Telegram token içeren `.py` dosyası bulunamadı.\n\nToken formatı: `123456789:AA...`"), bot_loop)
                return
            
            path, code, token, bot_name, bot_username = found
            
            # Bot doğrulandı, çalıştır
            name = f"{bot_name} (@{bot_username})"
            pk = start_bot_process(uid, token, code, name)
            
            premium_msg = "✅ **Premium Üye:** Bot anında başlatıldı!" if is_premium(uid) else "📥 **Admin onayına gönderildi.**"
            
            if not is_premium(uid):
                # Admin'e onay için gönder
                global_state["bot_codes"][uid] = code; save_state()
                context.bot_data[f"code_{uid}"] = code
                context.bot_data[f"token_{uid}"] = token
                context.bot_data[f"name_{uid}"] = name
                asyncio.run_coroutine_threadsafe(
                    context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=f"📥 **GitHub Bot Onayı**\n\n👤 {update.effective_user.first_name}\n🆔 `{uid}`\n🤖 Bot: {name}\n🔗 Repo: {url}\n📄 Dosya: `{path}`\n🔑 Token: `{token}`",
                        reply_markup=InlineKeyboardMarkup([[premium_button("Onayla", f"approve_{uid}", "✅", "success"), premium_button("Reddet", f"reject_{uid}", "❌", "danger")]]),
                        parse_mode="Markdown"
                    ), bot_loop
                )
            
            result_text = (
                f"✅ **Bot Başarıyla Aktif Edildi!**\n\n"
                f"🤖 **Bot Adı:** {bot_name}\n"
                f"👤 **Kullanıcı Adı:** @{bot_username}\n"
                f"📄 **Dosya:** `{path}`\n"
                f"🔑 **Token:** `{token[:15]}...`\n\n"
                f"{premium_msg}"
            )
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(result_text, reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Git", "my_bots", "🤖", "primary")]]), parse_mode="Markdown"),
                bot_loop
            )
        except Exception as e:
            logger.error(f"GitHub işlem hatası: {e}")
            asyncio.run_coroutine_threadsafe(msg.edit_text(f"❌ Hata: {e}"), bot_loop)
    
    threading.Thread(target=process, daemon=True).start()

# --- DOSYA İLE BOT AKTİF ETME ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; doc = update.message.document
    if not doc.file_name.endswith(".py"): return await update.message.reply_text("❌ Sadece `.py` dosyaları kabul edilir.")
    if not check_bot_limit(str(user.id)): return await update.message.reply_text("⚠️ Limit doldu! Premium alman lazım.")
    
    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")
    token_match = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    
    if not token_match: return await update.message.reply_text("❌ Dosyada geçerli bir token bulunamadı!")
    extracted_token = token_match.group(1).strip().strip("'\"")
    
    try:
        check = requests.get(f"https://api.telegram.org/bot{extracted_token}/getMe", timeout=10)
        if not check.json().get("ok"): return await update.message.reply_text("❌ Dosyadaki token Telegram tarafından reddedildi!")
    except: return await update.message.reply_text("❌ Token doğrulanamadı.")
    
    bot_name = doc.file_name.replace(".py", "")
    context.bot_data[f"code_{user.id}"] = code; context.bot_data[f"token_{user.id}"] = extracted_token; context.bot_data[f"name_{user.id}"] = bot_name
    
    if is_premium(user.id):
        global_state["bot_codes"][str(user.id)] = code; save_state()
        pk = start_bot_process(str(user.id), extracted_token, code, bot_name)
        await update.message.reply_text(f"✅ **Premium Üye:** Dosyanız anında başlatıldı!\nBot Adı: `{bot_name}`", parse_mode="Markdown")
    else:
        await context.bot.send_document(
            chat_id=ADMIN_ID, document=doc.file_id,
            caption=f"📥 **Dosya Onayı**\n\n👤 {user.first_name} (@{user.username})\n🆔 `{user.id}`\n🤖 Token: `{extracted_token}`\n📄 `{doc.file_name}`",
            reply_markup=InlineKeyboardMarkup([[premium_button("Onayla", f"approve_{user.id}", "✅", "success"), premium_button("Reddet", f"reject_{user.id}", "❌", "danger")]]),
            parse_mode="Markdown"
        )
        await update.message.reply_text("⏳ Admin onayına gönderildi.")

async def approve_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("approve_", "")
    code = context.bot_data.get(f"code_{user_id}"); token = context.bot_data.get(f"token_{user_id}"); name = context.bot_data.get(f"name_{user_id}", "Bot")
    if code and token:
        global_state["bot_codes"][user_id] = code; save_state()
        pk = start_bot_process(user_id, token, code, name)
        try:
            await q.edit_message_caption(f"✅ Onaylandı.\nBot Adı: `{name}`", parse_mode="Markdown")
        except: pass
        try:
            await context.bot.send_message(chat_id=int(user_id), text="✅ **Sevgili kullanıcı,**\n\nDosyanız moderatörler tarafından incelendi ve aksilik tespit edilmedi, dosyanız çalışır halde, iyi kullanımlar!")
        except: pass
    else: 
        try: await q.edit_message_caption("❌ Hata.")
        except: pass

async def reject_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("reject_", "")
    try:
        await q.edit_message_caption("❌ Reddedildi.")
    except: pass
    try:
        await context.bot.send_message(chat_id=int(user_id), text="❌ **Sevgili kullanıcı,**\n\nMaalesef dosyanız moderatörler tarafından incelendi ve bir aksilik çıkarak reddedildi.")
    except: pass

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (
        "💎 **Premium Üyelik Avantajları**\n\n"
        "👑 **Normal Üyelik**\n"
        "Sadece 1 bot çalıştırabilirsin. Dosyalar admin onayı bekler.\n\n"
        "⚡ **Premium Üyelik**\n"
        "5 bota kadar çalıştırabilirsin. Dosyalar anında çalışır!\n\n"
        "🚀 **Sunucu Önceliği**\n"
        "Premium üyelerin botları daha hızlı yanıt verir.\n\n"
        "👇 **Paket Seç**"
    )
    keyboard = [
        [premium_button("1 Haftalık - 15 ⭐", "premium_7", "⭐", "primary")], 
        [premium_button("1 Aylık - 40 ⭐", "premium_30", "⭐", "success")], 
        [premium_button("1 Yıllık - 100 ⭐", "premium_365", "💎", "primary")], 
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities)
    except: pass

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    try:
        await context.bot.send_invoice(chat_id=q.from_user.id, title=f"Premium - {days} Gün", description=f"{days} gün premium.", payload=f"premium_{uid}_{days}", provider_token="", currency="XTR", prices=[{"label": "Premium", "amount": stars}])
    except Exception as e:
        try: await q.edit_message_text(f"❌ Hata: {e}")
        except: pass

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text(f"✅ Premium aktif! {parts[2]} gün.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    pk = q.data.replace("log_", "")
    if pk not in running_procs:
        try: await q.edit_message_text("❌ Bot bulunamadı.")
        except: pass
        return
    
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-3000:]
        if not content.strip():
            content = "Henüz log kaydı yok."
    except:
        content = "Log okunamadı."
    
    safe_content = html.escape(content)
    text = f"📃 <b>Log: {running_procs[pk]['name']}</b>\n\n<pre>{safe_content}</pre>"
    
    try:
        await q.edit_message_text(
            text, 
            reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), 
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Log edit hatası: {e}")
        try:
            await context.bot.send_message(
                chat_id=q.from_user.id, 
                text=text, 
                reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]),
                parse_mode="HTML"
            )
        except: pass

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("stop_", "")
    if stop_bot_process(pk): 
        try:
            await q.edit_message_text(f"🔴 Bot durduruldu.", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
        except: pass
    else: 
        try: await q.edit_message_text("❌ Bot yok.")
        except: pass

application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
application.add_handler(CallbackQueryHandler(my_bots, pattern="^my_bots$"))
application.add_handler(CallbackQueryHandler(pip_menu, pattern="^pip_menu$"))
application.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_premium$"))
application.add_handler(CallbackQueryHandler(handle_premium_purchase, pattern="^premium_"))
application.add_handler(CallbackQueryHandler(github_start, pattern="^github_start$"))
application.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
application.add_handler(CallbackQueryHandler(stop_bot, pattern="^stop_"))
application.add_handler(CallbackQueryHandler(start_stopped_bot, pattern="^start_"))
application.add_handler(CallbackQueryHandler(delete_bot, pattern="^del_"))
application.add_handler(CallbackQueryHandler(approve_file, pattern="^approve_"))
application.add_handler(CallbackQueryHandler(reject_file, pattern="^reject_"))
application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_start$"))

# ÖNEMLİ: GitHub URL handler pip'ten ÖNCE olmalı
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Regex(r"^https?://github\.com/"), handle_github_url))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_pip_input))
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
    
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
            logger.info(f"Webhook ayarlandı: {r.json()}")
        except Exception as e:
            logger.error(f"Webhook ayarlanamadı: {e}")
    
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
