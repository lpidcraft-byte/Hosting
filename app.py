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

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, MessageEntity
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

# --- Ayarlar ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9053394489:AAEMkxfOuDRVTcTY4mWluMgNdDbj-Y9ryMY")
ADMIN_ID = 8913966694
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
GITHUB_API_TOKEN = os.environ.get("GITHUB_TOKEN", "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")

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

# --- LOG MASKELEME (GÜVENLİK) ---
class SensitiveFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # Telegram Token maskeleme (örn: 123456:ABC...)
        msg = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:***MASKELENDİ***', msg)
        # GitHub Token maskeleme
        msg = re.sub(r'github_pat_[A-Za-z0-9_]{50,}', '***GITHUB_TOKEN_GİZLİ***', msg)
        # Şifre vb.
        msg = re.sub(r'(?i)(password|passwd|secret|token)\s*[:=]\s*["\']?([^\s"\']+)', r'\1=***GİZLİ***', msg)
        record.msg = msg
        record.args = () 
        return True

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addFilter(SensitiveFilter()) # Ana loglara filtreyi ekle

# --- KALICI DEPOLAMA AYARI ---
if os.path.exists("/data") and os.access("/data", os.W_OK):
    DATA_DIR = Path("/data")
else:
    DATA_DIR = Path("/tmp/data")
    
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"

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
    except Exception as e:
        logger.error(f"Dosya kayıt hatası: {e}")

global_state = load_state()
if "banned" not in global_state: global_state["banned"] = []
running_procs = {}

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
    if url: kw["url"] = url
    else: kw["callback_data"] = callback_data
    if emoji in EMOJI_IDS: kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style: kw["style"] = style
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

def mask_token_in_log(text):
    """Kullanıcılara log gösterirken token vb. maskeler."""
    text = re.sub(r'\b(\d{6,12}):[A-Za-z0-9_-]{30,50}\b', r'\1:***TOKEN_GİZLENDİ***', text)
    text = re.sub(r'github_pat_[A-Za-z0-9_]{50,}', '***GITHUB_TOKEN_GİZLENDİ***', text)
    return text

def is_premium(user_id):
    return global_state["premium"].get(str(user_id), 0) > time.time()

def is_banned(user_id):
    return str(user_id) in global_state.get("banned", [])

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
        "⚠️ <b>Zorunlu Kanal Üyeliği</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Botu kullanabilmek için aşağıdaki kanallara katılman gerekiyor:</blockquote>\n\n"
        "1️⃣ <b>𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 𝗧𝗘𝗔𝗠 #𝐊𝐫𝐚𝐥𝐥𝐢𝐤</b> <i>(Kanal)</i>\n"
        "2️⃣ <b>𝙑𝘼𝙉𝙏𝙊𝙍𝙄𝙐𝙈 TEAM sohbet</b> <i>(Grup)</i>\n\n"
        "<i>Katıldıktan sonra</i> <b>Kontrol Et</b> <i>butonuna bas.</i>"
    )
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
        await q.answer("❌ Henüz tüm kanallara katılmadın!", show_alert=True)

def start_bot_process(user_id, bot_token, code_content, bot_name="Bot", build_cmd="", start_cmd=""):
    uid = str(user_id)
    proc_key = f"{uid}_{int(time.time())}"
    bot_dir = DATA_DIR / "user_bots" / uid / proc_key
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot_{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"
    
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code_content)

    with open(log_path, "w", encoding="utf-8") as lf:
        if build_cmd.strip():
            try:
                br = subprocess.run(build_cmd, shell=True, cwd=str(bot_dir), capture_output=True, text=True, timeout=300)
                lf.write(f"[BUILD] {build_cmd}\n[OUT]\n{br.stdout}\n[ERR]\n{br.stderr}\n[RC] {br.returncode}\n\n")
            except Exception as e:
                lf.write(f"[BUILD HATA] {e}\n")
    
    log_file = open(log_path, "a", encoding="utf-8")
    env = {**os.environ, "BOT_TOKEN": bot_token}
    
    if start_cmd.strip():
        proc = subprocess.Popen(start_cmd, shell=True, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
    else:
        proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
    
    running_procs[proc_key] = {
        "proc": proc, "log_path": str(log_path), "token": bot_token,
        "started": time.time(), "user_id": uid, "name": bot_name,
        "build_cmd": build_cmd, "start_cmd": start_cmd
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
        text = (
            "🚫 <b>Hesabınız Yasaklandı</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "<blockquote>Bu botu kullanma yetkiniz kaldırılmıştır. Detaylı bilgi için <i>admin</i> ile iletişime geçin.</blockquote>"
        )
        entities = parse_entities(text)
        if update.message:
            await update.message.reply_text(text, entities=entities, parse_mode="HTML")
        elif update.callback_query:
            try: await update.callback_query.edit_message_text(text, entities=entities, parse_mode="HTML")
            except: pass
        return
    
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
        f"👋 <b>Merhaba, <i>{user.first_name}</i>! 🎉</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "🤖 <b>VDS Bot Hosting Hizmeti</b>\n"
        "<i>Kendi botlarını 7/24 çalıştır, loglarını anlık görüntüle.</i>\n\n"
        "🌐 <b>GitHub Desteği</b>\n"
        "<i>GitHub repo URL'ni gönder, içindeki botu otomatik bulup çalıştıralım.</i>\n\n"
        "📦 <b>Pip Desteği</b>\n"
        "<i>Eksik modülleri tek tıkla yükle, hata almadan botunu çalıştır.</i>\n\n"
        "💎 <b>Premium Avantajları</b>\n"
        "<i>Sıra beklemeden anında onay, 5 bota kadar çalıştırma izni.</i>\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "👇 <b>Hemen Başla</b>\n"
        "<blockquote>Botunu çalıştırmak için <code>.py</code> uzantılı dosyanı buraya gönder.</blockquote>"
    )
    reply_markup = InlineKeyboardMarkup(keyboard)
    entities = parse_entities(text)
    
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")
    elif update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=reply_markup, entities=entities, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Menü hatası: {e}")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        await show_main_menu(update, context)
        return
    if not await check_membership(user_id):
        await send_join_message(update, context)
        return
    await show_main_menu(update, context)

# --- ADMIN PANELİ ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: 
        return await q.edit_message_text("⛔ <b>Yetkisiz!</b>\n\n<i>Bu alan sadece admin içindir.</i>", parse_mode="HTML")
    
    text = (
        "👮‍♀ <b>Admin Kontrol Paneli</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Aşağıdaki işlemlerden birini seçebilirsin:</blockquote>\n\n"
        "• 👥 <b>Kullanıcı Listesi</b> — <i>Tüm kullanıcıları görüntüle</i>\n"
        "• 🚫 <b>Ban At</b> — <i>Kullanıcıyı yasakla</i>\n"
        "• ✅ <b>Ban Kaldır</b> — <i>Yasağı geri al</i>\n"
        "• 📢 <b>Duyuru Yap</b> — <i>Tüm kullanıcılara mesaj gönder</i>\n"
        "• 💎 <b>Premium Ver</b> — <i>Kullanıcıya premium tanımla</i>\n"
        "• ❌ <b>Premium Geri Al</b> — <i>Premium'u iptal et</i>\n"
        "• 📁 <b>Dosya Listesi</b> — <i>Çalışan tüm botları görüntüle</i>"
    )
    keyboard = [
        [premium_button("Kullanıcı Listesi", "user_list", "👥", "primary")],
        [premium_button("Ban At", "ban_user", "🚫", "danger"), premium_button("Ban Kaldır", "unban_user", "✅", "success")],
        [premium_button("Duyuru Yap", "broadcast", "📢", "primary")],
        [premium_button("Premium Ver", "give_premium", "💎", "success")],
        [premium_button("Premium Geri Al", "revoke_premium", "❌", "danger")],
        [premium_button("Dosya Listesi", "file_list", "📁", "primary")],
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except: pass

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = (
        "👥 <b>Kullanıcı Listesi</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    if not global_state["users"]:
        text += "<i>Henüz kayıtlı kullanıcı yok.</i>"
    for uid, info in list(global_state["users"].items())[:50]:
        ps = "💎 " if is_premium(uid) else ""
        ban = "🚫 " if is_banned(uid) else ""
        text += f"🆔 <code>{uid}</code>\n👤 @{info.get('username','yok')} | <i>{info.get('first_name','')}</i> {ps}{ban}\n\n"
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

# --- BAN / UNBAN ---
async def ban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_ban_id"] = True
    text = (
        "🚫 <b>Ban Atma</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Banlamak istediğin kullanıcının <b>ID'sini</b> gönder.</blockquote>\n\n"
        "📌 <i>Örnek:</i> <code>123456789</code>\n\n"
        "<i>İptal için</i> <b>Geri</b> <i>butonuna bas.</i>"
    )
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def unban_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    banned_list = global_state.get("banned", [])
    text = (
        "✅ <b>Ban Kaldırma</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    if not banned_list:
        text += "<i>Şu an banlı kullanıcı yok.</i>"
        try:
            return await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), parse_mode="HTML")
        except: return
    text += f"Toplam <b>{len(banned_list)}</b> banlı kullanıcı:\n\n"
    for bid in banned_list[:30]:
        info = global_state["users"].get(bid, {})
        text += f"🆔 <code>{bid}</code> | @{info.get('username','yok')}\n"
    text += "\n👇 <b>Kaldırmak için ID yaz.</b>"
    context.user_data["awaiting_unban_id"] = True
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

# --- DUYURU ---
async def broadcast_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_broadcast"] = True
    total = len(global_state["users"])
    text = (
        "📢 <b>Duyuru Yap</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <i>Toplam kullanıcı:</i> <b>{total}</b>\n\n"
        "<blockquote>Göndermek istediğin mesajı yaz. Bot tüm kullanıcılara gönderecek.</blockquote>\n\n"
        "⚠️ <i>HTML desteklidir.</i>"
    )
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def do_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg_text = update.message.text.strip()
    context.user_data["awaiting_broadcast"] = False
    users = list(global_state["users"].keys())
    status = await update.message.reply_text(f"⏳ <i>Duyuru gönderiliyor... (0/{len(users)})</i>", parse_mode="HTML")
    
    sent, failed = 0, 0
    for i, uid in enumerate(users):
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"📢 <b>DUYURU</b>\n━━━━━━━━━━━━━━━━━━\n\n{msg_text}", parse_mode="HTML")
            sent += 1
        except:
            failed += 1
        if (i + 1) % 10 == 0 or (i + 1) == len(users):
            try:
                await status.edit_text(f"⏳ <i>Duyuru gönderiliyor... ({i+1}/{len(users)})</i>", parse_mode="HTML")
            except: pass
        await asyncio.sleep(0.05)
    
    try:
        await status.edit_text(
            f"✅ <b>Duyuru Tamamlandı!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Başarılı: <b>{sent}</b>\n"
            f"❌ Başarısız: <b>{failed}</b>",
            reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]),
            parse_mode="HTML"
        )
    except: pass

# --- PREMIUM VER ---
async def give_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_premium_id"] = True
    text = (
        "💎 <b>Premium Verme</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Premium vermek istediğin kullanıcının <b>ID'sini</b> gönder.</blockquote>\n\n"
        "📌 <i>Örnek:</i> <code>123456789</code>\n\n"
        "<i>İptal için</i> <b>Geri</b> <i>butonuna bas.</i>"
    )
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

async def premium_duration_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    context.user_data["premium_target_id"] = user_id
    text = (
        "💎 <b>Premium Süresi Seçin</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 Hedef Kullanıcı: <code>{user_id}</code>\n\n"
        "<blockquote>Lütfen vermek istediğin süreyi seç:</blockquote>\n\n"
        "• ⭐ <b>1 Hafta</b> — <i>7 gün premium</i>\n"
        "• ⭐ <b>1 Ay</b> — <i>30 gün premium</i>\n"
        "• ⭐ <b>1 Yıl</b> — <i>365 gün premium</i>"
    )
    keyboard = [
        [premium_button("1 Haftalık Ver", "give_prem_7", "⭐", "primary")],
        [premium_button("1 Aylık Ver", "give_prem_30", "⭐", "success")],
        [premium_button("1 Yıllık Ver", "give_prem_365", "💎", "primary")],
        [premium_button("İptal", "admin_panel", "❌", "danger")]
    ]
    entities = parse_entities(text)
    try:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except:
        try:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
        except: pass

async def execute_give_premium(update: Update, context: ContextTypes.DEFAULT_TYPE, days):
    q = update.callback_query
    await q.answer()
    target_id = context.user_data.get("premium_target_id")
    if not target_id:
        return await q.edit_message_text("❌ <b>Hata:</b> Hedef kullanıcı bulunamadı.", parse_mode="HTML")
    
    current = global_state["premium"].get(target_id, 0)
    base = current if current > time.time() else time.time()
    new_expiry = base + days * 86400
    global_state["premium"][target_id] = new_expiry
    save_state()
    
    fmt_date = time.strftime("%d.%m.%Y %H:%M", time.localtime(new_expiry))
    
    try:
        await context.bot.send_message(
            chat_id=int(target_id),
            text=(
                "🎉 <b>Premium Üyelik Aktif!</b>\n"
                "━━━━━━━━━━━━━━━━━━\n\n"
                f"💎 Süre: <b>{days} gün</b>\n"
                f"⏰ Bitiş: <b>{fmt_date}</b>\n\n"
                "<blockquote>Artık <i>5 bota kadar</i> çalıştırabilir ve anında onay alabilirsin! 🚀</blockquote>"
            ),
            parse_mode="HTML"
        )
    except: pass
    
    try:
        await q.edit_message_text(
            f"✅ <b>Premium Verildi!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"👤 Kullanıcı: <code>{target_id}</code>\n"
            f"💎 Süre: <b>{days} gün</b>\n"
            f"⏰ Bitiş: <b>{fmt_date}</b>",
            reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]),
            parse_mode="HTML"
        )
    except: pass

# --- PREMIUM GERİ AL ---
async def revoke_premium_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    context.user_data["awaiting_revoke_id"] = True
    text = (
        "❌ <b>Premium Geri Alma</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Premiumunu iptal etmek istediğin kullanıcının <b>ID'sini</b> gönder.</blockquote>\n\n"
        "📌 <i>Örnek:</i> <code>123456789</code>\n\n"
        "<i>İptal için</i> <b>Geri</b> <i>butonuna bas.</i>"
    )
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except: pass

# --- DOSYA LİSTESİ ---
async def file_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    
    text = (
        "📁 <b>Sistemdeki Tüm Botlar</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if not running_procs:
        text += "<i>Şu an çalışan veya kayıtlı bot yok.</i>"
    else:
        for i, (pk, info) in enumerate(running_procs.items(), 1):
            user_info = global_state["users"].get(info["user_id"], {})
            status = "🟢 Çalışıyor" if info["proc"].poll() is None else "🔴 Durdu"
            uptime = int(time.time() - info["started"])
            uptime_str = f"{uptime//3600}s {uptime%3600//60}dk"
            # Token gizlendi (sadece admin görebilir diye spoiler içinde)
            text += (
                f"<b>{i}. {info['name']}</b>\n"
                f"👤 Sahip: @{user_info.get('username','yok')} (<code>{info['user_id']}</code>)\n"
                f"🔑 Token: <span class=\"tg-spoiler\"><code>{info['token'][:15]}...</code></span>\n"
                f"📊 Durum: {status}\n"
                f"⏱ Süre: <i>{uptime_str}</i>\n\n"
            )
    
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), entities=entities, parse_mode="HTML")
    except Exception as e:
        try:
            await q.edit_message_text(
                text[:4000] + "\n\n<i>... (devamı kırpıldı)</i>",
                reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]),
                parse_mode="HTML"
            )
        except: pass

# --- MY BOTS ---
async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    
    if not bl:
        text = (
            "🤖 <b>Bot Bulunamadı</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "<blockquote>Henüz bir bot yüklemedin.</blockquote>\n\n"
            "Çalıştırmak için <b><code>.py</code></b> dosyanı gönder veya <b>GitHub URL'si</b> ile aktif et."
        )
        entities = parse_entities(text)
        try:
            return await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]), entities=entities, parse_mode="HTML")
        except: return
    
    keyboard = []
    text = "🤖 <b>Aktif Botlarınız</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    for i, pk in enumerate(bl):
        st = "🟢 Çalışıyor" if running_procs[pk]["proc"].poll() is None else "🔴 Durdu"
        text += f"📦 <b>{running_procs[pk]['name']}</b>\n└ <i>{st}</i>\n\n"
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
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Bot listesi hatası: {e}")

async def pip_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (
        "📦 <b>Pip Paket İndirici</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>Alt botlarında eksik modül hatası mı alıyorsun?</blockquote>\n\n"
        "🔍 <b>Nasıl Kullanılır?</b>\n"
        "<i>Aşağıya indirmek istediğin paketin adını yaz.</i>\n"
        "📌 <i>Örnek:</i> <code>aiohttp</code>, <code>beautifulsoup4</code>\n\n"
        "⚡ <b>Hız</b>\n"
        "<i>Paketler arka planda indirilir, botun donmaz.</i>\n\n"
        "👇 <b>Hemen başla</b>\n"
        "<i>Paket adını mesaj olarak yaz.</i>"
    )
    keyboard = [[premium_button("Geri", "back_start", "↩", "danger")]]
    context.user_data["awaiting_pip_package"] = True
    context.user_data.pop("awaiting_github_url", None)
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except: pass

def install_pip_background(package_name, chat_id, context):
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", package_name], capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"✅ <b>Başarılı!</b>\n\n<code>{package_name}</code> paketi yüklendi.", parse_mode="HTML"), bot_loop)
        else:
            err = html.escape(result.stderr[-1000:])
            asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"❌ <b>Hata:</b>\n\n<pre>{err}</pre>", parse_mode="HTML"), bot_loop)
    except Exception as e:
        asyncio.run_coroutine_threadsafe(context.bot.send_message(chat_id=chat_id, text=f"❌ <i>İşlem hatası:</i> <code>{e}</code>", parse_mode="HTML"), bot_loop)

async def start_stopped_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("start_", "")
    if pk in running_procs:
        info = running_procs[pk]
        bot_dir = DATA_DIR / "user_bots" / info["user_id"] / pk
        script_path = bot_dir / f"bot_{pk}.py"
        if script_path.exists():
            log_file = open(info["log_path"], "a", encoding="utf-8")
            env = {**os.environ, "BOT_TOKEN": info["token"]}
            if info.get("start_cmd", "").strip():
                proc = subprocess.Popen(info["start_cmd"], shell=True, stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
            else:
                proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env=env)
            running_procs[pk]["proc"] = proc
            try:
                await q.edit_message_text(f"▶ <b>Bot yeniden başlatıldı!</b>\n\n🤖 <code>{info['name']}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
            except: pass
        else: 
            try: await q.edit_message_text("❌ <i>Bot dosyası bulunamadı.</i>", parse_mode="HTML")
            except: pass
    else: 
        try: await q.edit_message_text("❌ <i>Bot bulunamadı.</i>", parse_mode="HTML")
        except: pass

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("del_", "")
    if pk in running_procs:
        info = running_procs[pk]
        if info["proc"].poll() is None: info["proc"].terminate()
        del running_procs[pk]
        try:
            await q.edit_message_text(f"🗑 <b>Bot silindi!</b>\n\n🤖 <code>{info['name']}</code>", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
        except: pass
    else: 
        try: await q.edit_message_text("❌ <i>Bot zaten yok.</i>", parse_mode="HTML")
        except: pass

# --- GITHUB URL İLE BOT AKTİF ETME ---
async def github_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["awaiting_github_url"] = True
    context.user_data.pop("github_data", None)
    context.user_data.pop("awaiting_pip_package", None)
    text = (
        "🌐 <b>GitHub'dan Bot Aktif Etme</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<blockquote>GitHub repo URL'sini gönder.</blockquote>\n"
        "📌 <i>Örnek:</i> <code>https://github.com/kullanici/repo</code>\n\n"
        "🔍 <i>Repo içindeki <code>.py</code> dosyaları taranır, içinde geçerli Telegram token olan dosya bulunur.</i>\n\n"
        "⚠️ Token'ın şu formatta olmalı: <code>123456789:AA...</code>\n\n"
        "👇 <b>URL'yi mesaj olarak yaz.</b>"
    )
    keyboard = [[premium_button("Geri", "back_start", "↩", "danger")]]
    entities = parse_entities(text)
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except: pass

def github_repo_api(url):
    url = url.strip().rstrip("/")
    m = re.match(r"https?://(?:www\.)?github\.com/([^/\s]+)/([^/\s]+)(?:/tree/([^/\s]+))?", url)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), m.group(3)

def github_headers():
    headers = {"Accept": "application/vnd.github+json"}
    if GITHUB_API_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_API_TOKEN}"
    return headers

def fetch_github_files(user, repo, branch=None):
    headers = github_headers()
    if branch is None:
        r = requests.get(f"https://api.github.com/repos/{user}/{repo}", headers=headers, timeout=15)
        if r.status_code == 401: return None, "GitHub token geçersiz."
        if r.status_code == 403: return None, "GitHub API rate limit aşıldı."
        if r.status_code == 404: return None, "Repo bulunamadı (404)."
        if r.status_code != 200: return None, f"Repo bilgisi alınamadı (HTTP {r.status_code})"
        branch = r.json().get("default_branch", "main")
    r = requests.get(f"https://api.github.com/repos/{user}/{repo}/git/trees/{branch}?recursive=1", headers=headers, timeout=20)
    if r.status_code == 401: return None, "GitHub token geçersiz."
    if r.status_code == 403: return None, "GitHub API rate limit aşıldı."
    if r.status_code != 200: return None, f"Dosya listesi alınamadı (HTTP {r.status_code})"
    return r.json().get("tree", []), None

def download_github_file(user, repo, branch, path):
    url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{path}"
    r = requests.get(url, timeout=20)
    if r.status_code == 200: return r.text
    return None

def extract_and_validate_token(code):
    matches = re.findall(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    for token in matches:
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            data = r.json()
            if data.get("ok"):
                bot_info = data["result"]
                return token, bot_info.get("first_name", "Bot"), bot_info.get("username", "")
        except: continue
    return None, None, None

async def handle_github_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_github_url"): return
    context.user_data["awaiting_github_url"] = False
    url = update.message.text.strip()
    user_id = update.effective_user.id
    uid = str(user_id)
    
    if not check_bot_limit(uid):
        return await update.message.reply_text("⚠️ <b>Bot limitin doldu!</b>\n\n<i>Premium alman lazım.</i>", parse_mode="HTML")
    
    user, repo, branch = github_repo_api(url)
    if not user:
        return await update.message.reply_text("❌ <b>Geçersiz URL!</b>\n\n<i>Örnek:</i> <code>https://github.com/kullanici/repo</code>", parse_mode="HTML")
    
    msg = await update.message.reply_text("🔍 <i>Repo taranıyor, lütfen bekle...</i>", parse_mode="HTML")
    
    def process():
        try:
            files, err = fetch_github_files(user, repo, branch)
            if err:
                asyncio.run_coroutine_threadsafe(msg.edit_text(f"❌ <b>Hata:</b>\n\n<i>{err}</i>", parse_mode="HTML"), bot_loop)
                return
            py_files = [f for f in files if f["type"] == "blob" and f["path"].endswith(".py")]
            if not py_files:
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ <i>Repo içinde <code>.py</code> dosyası bulunamadı.</i>", parse_mode="HTML"), bot_loop)
                return
            asyncio.run_coroutine_threadsafe(msg.edit_text(f"📂 <b>{len(py_files)}</b> <i>Python dosyası bulundu, token aranıyor...</i>", parse_mode="HTML"), bot_loop)
            found = None
            for f in py_files[:30]:
                content = download_github_file(user, repo, branch or "main", f["path"])
                if not content: continue
                token, bot_name, bot_username = extract_and_validate_token(content)
                if token:
                    found = (f["path"], content, token, bot_name, bot_username)
                    break
            if not found:
                asyncio.run_coroutine_threadsafe(msg.edit_text("❌ <i>Repo içinde geçerli Telegram token içeren <code>.py</code> dosyası bulunamadı.</i>\n\n<b>Token formatı:</b> <code>123456789:AA...</code>", parse_mode="HTML"), bot_loop)
                return
            path, code, token, bot_name, bot_username = found
            context.user_data["github_data"] = {
                "url": url, "user": user, "repo": repo, "branch": branch or "main",
                "path": path, "code": code, "token": token,
                "bot_name": bot_name, "bot_username": bot_username, "step": "build"
            }
            asyncio.run_coroutine_threadsafe(
                msg.edit_text(
                    f"✅ <b>Bot Bulundu!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n\n"
                    f"🤖 <b>Bot:</b> {bot_name} (@{bot_username})\n"
                    f"📄 <b>Dosya:</b> <code>{path}</code>\n\n"
                    f"<blockquote>🛠 <b>Build Command</b> girin (bağımlılık kurulumu).\n"
                    f"📌 <i>Örnek:</i> <code>pip install -r requirements.txt</code></blockquote>\n\n"
                    f"<i>Yoksa</i> <code>yok</code> <i>yazın.</i>",
                    reply_markup=InlineKeyboardMarkup([[premium_button("İptal", "back_start", "❌", "danger")]]),
                    parse_mode="HTML"
                ), bot_loop
            )
        except Exception as e:
            logger.error(f"GitHub işlem hatası: {e}")
            asyncio.run_coroutine_threadsafe(msg.edit_text(f"❌ <b>Hata:</b>\n\n<i>{e}</i>", parse_mode="HTML"), bot_loop)
    
    threading.Thread(target=process, daemon=True).start()

# --- TEXT ROUTER ---
async def handle_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    ud = context.user_data
    
    # Admin: ban id bekleniyor mu?
    if ud.get("awaiting_ban_id"):
        ud["awaiting_ban_id"] = False
        if not text.isdigit():
            return await update.message.reply_text("❌ <b>Geçersiz ID!</b>\n\n<i>Sadece sayı gir.</i>", parse_mode="HTML")
        target_id = text
        if target_id == str(ADMIN_ID):
            return await update.message.reply_text("❌ <i>Admini banlayamazsın.</i>", parse_mode="HTML")
        if target_id in global_state["banned"]:
            return await update.message.reply_text("⚠️ <i>Bu kullanıcı zaten banlı.</i>", parse_mode="HTML")
        global_state["banned"].append(target_id)
        save_state()
        try:
            await context.bot.send_message(chat_id=int(target_id), text="🚫 <b>Hesabınız yasaklandı.</b>\n\n<blockquote>Bu botu kullanma yetkiniz kaldırılmıştır.</blockquote>", parse_mode="HTML")
        except: pass
        return await update.message.reply_text(
            f"✅ <b>Kullanıcı Banlandı!</b>\n\n🆔 <code>{target_id}</code>",
            reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]),
            parse_mode="HTML"
        )
    
    # Admin: unban id bekleniyor mu?
    if ud.get("awaiting_unban_id"):
        ud["awaiting_unban_id"] = False
        if not text.isdigit():
            return await update.message.reply_text("❌ <i>Geçersiz ID.</i>", parse_mode="HTML")
        target_id = text
        if target_id in global_state["banned"]:
            global_state["banned"].remove(target_id)
            save_state()
            try:
                await context.bot.send_message(chat_id=int(target_id), text="✅ <b>Banınız kaldırıldı.</b>\n\n<i>Botu tekrar kullanabilirsiniz.</i>", parse_mode="HTML")
            except: pass
            return await update.message.reply_text(
                f"✅ <b>Ban Kaldırıldı!</b>\n\n🆔 <code>{target_id}</code>",
                reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]),
                parse_mode="HTML"
            )
        else:
            return await update.message.reply_text("❌ <i>Bu kullanıcı banlı değil.</i>", parse_mode="HTML")
    
    # Admin: duyuru metni bekleniyor mu?
    if ud.get("awaiting_broadcast"):
        await do_broadcast(update, context)
        return
    
    # Admin: premium id bekleniyor mu?
    if ud.get("awaiting_premium_id"):
        ud["awaiting_premium_id"] = False
        if not text.isdigit():
            return await update.message.reply_text("❌ <i>Geçersiz ID.</i>", parse_mode="HTML")
        await premium_duration_menu(update, context, text)
        return
    
    # Admin: revoke id bekleniyor mu?
    if ud.get("awaiting_revoke_id"):
        ud["awaiting_revoke_id"] = False
        if not text.isdigit():
            return await update.message.reply_text("❌ <i>Geçersiz ID.</i>", parse_mode="HTML")
        target_id = text
        if target_id in global_state["premium"]:
            del global_state["premium"][target_id]
            save_state()
            try:
                await context.bot.send_message(chat_id=int(target_id), text="❌ <b>Premium iptal edildi.</b>\n\n<i>Detaylı bilgi için admin ile iletişime geçin.</i>", parse_mode="HTML")
            except: pass
            return await update.message.reply_text(
                f"✅ <b>Premium Geri Alındı!</b>\n\n🆔 <code>{target_id}</code>",
                reply_markup=InlineKeyboardMarkup([[premium_button("Admin Paneli", "admin_panel", "↩", "primary")]]),
                parse_mode="HTML"
            )
        else:
            return await update.message.reply_text("❌ <i>Bu kullanıcının zaten premiumu yok.</i>", parse_mode="HTML")
    
    # GitHub URL bekleniyor mu?
    if ud.get("awaiting_github_url"):
        if re.match(r"https?://(?:www\.)?github\.com/[^\s]+", text):
            await handle_github_url(update, context)
            return
        else:
            ud["awaiting_github_url"] = False
    
    # GitHub build/start command
    data = ud.get("github_data")
    if data and data.get("step") == "build":
        build_cmd = "" if text.lower() == "yok" else text
        data["build_cmd"] = build_cmd
        data["step"] = "start"
        await update.message.reply_text(
            f"🛠 <b>Build Command:</b> <code>{build_cmd if build_cmd else 'Yok'}</code>\n\n"
            f"🚀 <b>Start Command</b> girin (botu başlatmak için).\n"
            f"📌 <i>Örnek:</i> <code>python bot.py</code>\n\n"
            f"<i>Varsayılan için</i> <code>yok</code> <i>yazın.</i>",
            reply_markup=InlineKeyboardMarkup([[premium_button("İptal", "back_start", "❌", "danger")]]),
            parse_mode="HTML"
        )
        return
    
    if data and data.get("step") == "start":
        start_cmd = "" if text.lower() == "yok" else text
        ud.pop("github_data", None)
        uid = str(update.effective_user.id)
        name = f"{data['bot_name']} (@{data['bot_username']})"
        start_bot_process(uid, data["token"], data["code"], name, data["build_cmd"], start_cmd)
        
        if is_premium(uid):
            premium_msg = "✅ <b>Premium Üye:</b> <i>Bot anında başlatıldı!</i>"
        else:
            premium_msg = "📥 <i>Admin onayına gönderildi.</i>"
            global_state["bot_codes"][uid] = data["code"]; save_state()
            context.bot_data[f"code_{uid}"] = data["code"]
            context.bot_data[f"token_{uid}"] = data["token"]
            context.bot_data[f"name_{uid}"] = name
            context.bot_data[f"build_{uid}"] = data["build_cmd"]
            context.bot_data[f"start_{uid}"] = start_cmd
            try:
                # DİKKAT: Admin'e giden mesajda token spoiler içinde gizlendi
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"📥 <b>GitHub Bot Onayı</b>\n\n👤 {update.effective_user.first_name}\n🆔 <code>{uid}</code>\n🤖 Bot: {name}\n🔗 Repo: {data['url']}\n📄 Dosya: <code>{data['path']}</code>\n🔑 Token: <span class=\"tg-spoiler\"><code>{data['token']}</code></span>\n🛠 Build: <code>{data['build_cmd'] or 'Yok'}</code>\n🚀 Start: <code>{start_cmd or 'Varsayılan'}</code>",
                    reply_markup=InlineKeyboardMarkup([[premium_button("Onayla", f"approve_{uid}", "✅", "success"), premium_button("Reddet", f"reject_{uid}", "❌", "danger")]]),
                    parse_mode="HTML"
                )
            except: pass
        
        await update.message.reply_text(
            f"✅ <b>Bot Başarıyla Aktif Edildi!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🤖 <b>Bot Adı:</b> {data['bot_name']}\n"
            f"👤 <b>Kullanıcı Adı:</b> @{data['bot_username']}\n"
            f"📄 <b>Dosya:</b> <code>{data['path']}</code>\n"
            f"🛠 <b>Build:</b> <code>{data['build_cmd'] or 'Yok'}</code>\n"
            f"🚀 <b>Start:</b> <code>{start_cmd or 'Varsayılan'}</code>\n\n"
            f"{premium_msg}",
            reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Git", "my_bots", "🤖", "primary")]]),
            parse_mode="HTML"
        )
        return
    
    # Pip paket
    if ud.get("awaiting_pip_package"):
        ud["awaiting_pip_package"] = False
        package_name = text
        if not re.match(r"^[a-zA-Z0-9_\-]+$", package_name):
            await update.message.reply_text("❌ <i>Geçersiz paket adı!</i>", parse_mode="HTML")
            return
        await update.message.reply_text(f"⏳ <i><code>{package_name}</code> arka planda yükleniyor...</i>", parse_mode="HTML")
        threading.Thread(target=install_pip_background, args=(package_name, update.effective_chat.id, context)).start()
        return

# --- DOSYA İLE BOT AKTİF ETME ---
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; doc = update.message.document
    if is_banned(user.id):
        return await update.message.reply_text("🚫 <i>Yasaklandınız, bot kullanamazsınız.</i>", parse_mode="HTML")
    if not doc.file_name.endswith(".py"): return await update.message.reply_text("❌ <i>Sadece <code>.py</code> dosyaları kabul edilir.</i>", parse_mode="HTML")
    if not check_bot_limit(str(user.id)): return await update.message.reply_text("⚠️ <b>Limit doldu!</b>\n\n<i>Premium alman lazım.</i>", parse_mode="HTML")
    
    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}.py"
    await file.download_to_drive(tmp)
    code = tmp.read_text(encoding="utf-8", errors="ignore")
    token_match = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,50})", code)
    
    if not token_match: return await update.message.reply_text("❌ <i>Dosyada geçerli bir token bulunamadı!</i>", parse_mode="HTML")
    extracted_token = token_match.group(1).strip().strip("'\"")
    
    try:
        check = requests.get(f"https://api.telegram.org/bot{extracted_token}/getMe", timeout=10)
        if not check.json().get("ok"): return await update.message.reply_text("❌ <i>Dosyadaki token Telegram tarafından reddedildi!</i>", parse_mode="HTML")
    except: return await update.message.reply_text("❌ <i>Token doğrulanamadı.</i>", parse_mode="HTML")
    
    bot_name = doc.file_name.replace(".py", "")
    context.bot_data[f"code_{user.id}"] = code; context.bot_data[f"token_{user.id}"] = extracted_token; context.bot_data[f"name_{user.id}"] = bot_name
    
    if is_premium(user.id):
        global_state["bot_codes"][str(user.id)] = code; save_state()
        pk = start_bot_process(str(user.id), extracted_token, code, bot_name)
        await update.message.reply_text(f"✅ <b>Premium Üye:</b> <i>Dosyanız anında başlatıldı!</i>\n\n🤖 Bot Adı: <code>{bot_name}</code>", parse_mode="HTML")
    else:
        # DİKKAT: Admin'e giden dosya onayında token spoiler içinde gizlendi
        await context.bot.send_document(
            chat_id=ADMIN_ID, document=doc.file_id,
            caption=f"📥 <b>Dosya Onayı</b>\n\n👤 {user.first_name} (@{user.username})\n🆔 <code>{user.id}</code>\n🤖 Token: <span class=\"tg-spoiler\"><code>{extracted_token}</code></span>\n📄 <code>{doc.file_name}</code>",
            reply_markup=InlineKeyboardMarkup([[premium_button("Onayla", f"approve_{user.id}", "✅", "success"), premium_button("Reddet", f"reject_{user.id}", "❌", "danger")]]),
            parse_mode="HTML"
        )
        await update.message.reply_text("⏳ <i>Admin onayına gönderildi.</i>", parse_mode="HTML")

async def approve_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("approve_", "")
    code = context.bot_data.get(f"code_{user_id}"); token = context.bot_data.get(f"token_{user_id}"); name = context.bot_data.get(f"name_{user_id}", "Bot")
    build_cmd = context.bot_data.get(f"build_{user_id}", "")
    start_cmd = context.bot_data.get(f"start_{user_id}", "")
    if code and token:
        global_state["bot_codes"][user_id] = code; save_state()
        pk = start_bot_process(user_id, token, code, name, build_cmd, start_cmd)
        try: await q.edit_message_caption(f"✅ <b>Onaylandı.</b>\n\n🤖 Bot Adı: <code>{name}</code>", parse_mode="HTML")
        except: pass
        try:
            await context.bot.send_message(chat_id=int(user_id), text="✅ <b>Sevgili kullanıcı,</b>\n\n<blockquote>Dosyanız moderatörler tarafından incelendi ve aksilik tespit edilmedi, dosyanız çalışır halde, iyi kullanımlar!</blockquote>", parse_mode="HTML")
        except: pass
    else: 
        try: await q.edit_message_caption("❌ <i>Hata.</i>", parse_mode="HTML")
        except: pass

async def reject_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("reject_", "")
    try: await q.edit_message_caption("❌ <i>Reddedildi.</i>", parse_mode="HTML")
    except: pass
    try:
        await context.bot.send_message(chat_id=int(user_id), text="❌ <b>Sevgili kullanıcı,</b>\n\n<blockquote>Maalesef dosyanız moderatörler tarafından incelendi ve bir aksilik çıkarak reddedildi.</blockquote>", parse_mode="HTML")
    except: pass

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    text = (
        "💎 <b>Premium Üyelik Avantajları</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "👑 <b>Normal Üyelik</b>\n"
        "<blockquote><i>Sadece 1 bot çalıştırabilirsin. Dosyalar admin onayı bekler.</i></blockquote>\n\n"
        "⚡ <b>Premium Üyelik</b>\n"
        "<blockquote><i>5 bota kadar çalıştırabilirsin. Dosyalar anında çalışır!</i></blockquote>\n\n"
        "🚀 <b>Sunucu Önceliği</b>\n"
        "<blockquote><i>Premium üyelerin botları daha hızlı yanıt verir.</i></blockquote>\n\n"
        "👇 <b>Paket Seç</b>"
    )
    keyboard = [
        [premium_button("1 Haftalık - 15 ⭐", "premium_7", "⭐", "primary")], 
        [premium_button("1 Aylık - 40 ⭐", "premium_30", "⭐", "success")], 
        [premium_button("1 Yıllık - 100 ⭐", "premium_365", "💎", "primary")], 
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    entities = parse_entities(text)
    try: await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), entities=entities, parse_mode="HTML")
    except: pass

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    try:
        await context.bot.send_invoice(chat_id=q.from_user.id, title=f"Premium - {days} Gün", description=f"{days} gün premium.", payload=f"premium_{uid}_{days}", provider_token="", currency="XTR", prices=[{"label": "Premium", "amount": stars}])
    except Exception as e:
        try: await q.edit_message_text(f"❌ <b>Hata:</b>\n\n<i>{e}</i>", parse_mode="HTML")
        except: pass

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text(f"✅ <b>Premium aktif!</b>\n\n<i>{parts[2]} gün</i>", parse_mode="HTML")

# --- LOG GÖRÜNTÜLEME (MASKELENMİŞ) ---
async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs:
        try: await q.edit_message_text("❌ <i>Bot bulunamadı.</i>", parse_mode="HTML")
        except: pass
        return
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-3000:]
        if not content.strip(): content = "Henüz log kaydı yok."
    except: content = "Log okunamadı."
    
    # TOKEN MASKELENİYOR
    content = mask_token_in_log(content)
    safe_content = html.escape(content)
    
    text = f"📃 <b>Log: {running_procs[pk]['name']}</b>\n\n<pre>{safe_content}</pre>"
    try:
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Log edit hatası: {e}")
        try:
            await context.bot.send_message(chat_id=q.from_user.id, text=text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), parse_mode="HTML")
        except: pass

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("stop_", "")
    if stop_bot_process(pk): 
        try: await q.edit_message_text(f"🔴 <b>Bot durduruldu.</b>", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]), parse_mode="HTML")
        except: pass
    else: 
        try: await q.edit_message_text("❌ <i>Bot yok.</i>", parse_mode="HTML")
        except: pass

application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
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

# Premium verme süre butonları
async def give_prem_7(update: Update, context: ContextTypes.DEFAULT_TYPE): await execute_give_premium(update, context, 7)
async def give_prem_30(update: Update, context: ContextTypes.DEFAULT_TYPE): await execute_give_premium(update, context, 30)
async def give_prem_365(update: Update, context: ContextTypes.DEFAULT_TYPE): await execute_give_premium(update, context, 365)

application.add_handler(CallbackQueryHandler(give_prem_7, pattern="^give_prem_7$"))
application.add_handler(CallbackQueryHandler(give_prem_30, pattern="^give_prem_30$"))
application.add_handler(CallbackQueryHandler(give_prem_365, pattern="^give_prem_365$"))

application.add_handler(CallbackQueryHandler(github_start, pattern="^github_start$"))
application.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
application.add_handler(CallbackQueryHandler(stop_bot, pattern="^stop_"))
application.add_handler(CallbackQueryHandler(start_stopped_bot, pattern="^start_"))
application.add_handler(CallbackQueryHandler(delete_bot, pattern="^del_"))
application.add_handler(CallbackQueryHandler(approve_file, pattern="^approve_"))
application.add_handler(CallbackQueryHandler(reject_file, pattern="^reject_"))
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
    
    if RENDER_URL:
        webhook_url = f"{RENDER_URL}/webhook/{BOT_TOKEN}"
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={webhook_url}")
            logger.info(f"Webhook ayarlandı: {r.json()}")
        except Exception as e:
            logger.error(f"Webhook ayarlanamadı: {e}")
    
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
