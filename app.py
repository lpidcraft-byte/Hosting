import os
import sys
import json
import subprocess
import threading
import time
import re
import logging
from pathlib import Path
from flask import Flask

# --- Flask (Render port dinleme zorunluluğu) ---
flask_app = Flask(__name__)

@flask_app.route("/")
@flask_app.route("/health")
def health():
    return "Bot is running", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

threading.Thread(target=run_flask, daemon=True).start()

# --- Bot Kodu ---
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9053394489:AAEMkxfOuDRVTcTY4mWluMgNdDbj-Y9ryMY")
ADMIN_ID = 8913966694

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

# ✅ KALICI DİZİN: Render'da mount path /data olarak ayarlanacak
DATA_DIR = Path("/data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

USERS_FILE = DATA_DIR / "users.json"
PREMIUM_FILE = DATA_DIR / "premium.json"
TOKENS_FILE = DATA_DIR / "pending_tokens.json"
BOTS_DIR = DATA_DIR / "user_bots"
BOTS_DIR.mkdir(exist_ok=True)

def load_json(path, default=None):
    if default is None: default = {}
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return default
    return default

def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

users = load_json(USERS_FILE)
premium_users = load_json(PREMIUM_FILE)
pending_tokens = load_json(TOKENS_FILE)  # {user_id: token}
running_procs = {}

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def premium_button(text, callback_data, emoji="✅", style=None):
    kw = {"text": text, "callback_data": callback_data}
    if emoji in EMOJI_IDS:
        kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style:
        kw["style"] = style
    return InlineKeyboardButton(**kw)

def is_premium(user_id):
    uid = str(user_id)
    return premium_users.get(uid, 0) > time.time()

def check_bot_limit(user_id):
    uid = str(user_id)
    user_bots = [b for b in running_procs.keys() if b.startswith(uid + "_")]
    if is_premium(user_id):
        return len(user_bots) < 5
    return len(user_bots) < 1

def validate_token(token):
    return bool(re.match(r"^\d+:[A-Za-z0-9_-]+$", token.strip()))

def start_bot_process(user_id, bot_token, bot_script_content=None):
    uid = str(user_id)
    proc_key = f"{uid}_{int(time.time())}"
    bot_dir = BOTS_DIR / uid
    bot_dir.mkdir(parents=True, exist_ok=True)
    script_path = bot_dir / f"bot_{proc_key}.py"
    log_path = bot_dir / f"log_{proc_key}.txt"
    
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(bot_script_content or "# placeholder\nimport time\nwhile True:\n    print('running...')\n    time.sleep(5)\n")
    
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script_path)],
        stdout=log_file, stderr=subprocess.STDOUT,
        cwd=str(bot_dir),
        env={**os.environ, "BOT_TOKEN": bot_token}
    )
    running_procs[proc_key] = {
        "proc": proc, "log_path": str(log_path),
        "token": bot_token, "started": time.time(), "user_id": uid
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

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    if uid not in users:
        users[uid] = {"username": user.username or "", "first_name": user.first_name or "", "last_name": user.last_name or "", "joined": time.time()}
        save_json(USERS_FILE, users)
    keyboard = []
    if user.id == ADMIN_ID:
        keyboard.append([premium_button("Admin Paneli", "admin_panel", "👮‍♀", "primary")])
    keyboard.append([premium_button("Botlarım", "my_bots", "🤖", "success")])
    keyboard.append([premium_button("Premium Al", "buy_premium", "💎", "primary")])
    await update.message.reply_text(f"👋 Merhaba {user.first_name}!\n\nBot yönetim paneline hoş geldin.", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: await q.edit_message_text("⛔ Yetkisiz."); return
    keyboard = [
        [premium_button("Kullanıcı Listesi", "user_list", "👥", "primary")],
        [premium_button("Çalışan Botlar", "admin_bots", "🤖", "success")],
        [premium_button("Geri", "back_start", "↩", "danger")],
    ]
    await q.edit_message_text("👮‍♀ Admin Paneli", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: await q.edit_message_text("⛔ Yetkisiz."); return
    text = "👥 Kullanıcı Listesi\n\n"
    for uid, info in list(users.items())[:50]:
        ps = "💎" if is_premium(uid) else ""
        text += f"🆔 `{uid}` | @{info.get('username','yok')} | {info.get('first_name','')} {ps}\n"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), parse_mode="Markdown")

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    if not bl:
        await q.edit_message_text("🤖 Henüz botun yok.", reply_markup=InlineKeyboardMarkup([[premium_button("Yeni Bot Ekle", "add_bot", "➕", "success")],[premium_button("Geri", "back_start", "↩", "danger")]]))
        return
    keyboard = []; text = "🤖 Botların:\n\n"
    for i, pk in enumerate(bl):
        st = "🟢 Çalışıyor" if running_procs[pk]["proc"].poll() is None else "🔴 Durdu"
        text += f"{i+1}. `{pk}` - {st}\n"
        keyboard.append([premium_button(f"Log #{i+1}", f"log_{pk}", "📃", "primary")])
        keyboard.append([premium_button(f"Durdur #{i+1}", f"stop_{pk}", "⏹", "danger")])
    keyboard.append([premium_button("Yeni Bot Ekle", "add_bot", "➕", "success")])
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def add_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if not check_bot_limit(str(q.from_user.id)):
        await q.edit_message_text("⚠️ Limit doldu! Premium al.", reply_markup=InlineKeyboardMarkup([[premium_button("Premium Al", "buy_premium", "💎", "success")],[premium_button("Geri", "my_bots", "↩", "danger")]]))
        return
    context.user_data["awaiting_token"] = True
    await q.edit_message_text("📥 Bot tokenini gönder.\nFormat: `123456789:ABCdef...`", parse_mode="Markdown")

async def handle_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_token"): return
    token = update.message.text.strip()
    if not validate_token(token):
        await update.message.reply_text("❌ Geçersiz format! `123456:ABC...` şeklinde olmalı.", parse_mode="Markdown"); return
    context.user_data["awaiting_token"] = False
    uid = str(update.effective_user.id)
    pending_tokens[uid] = token
    save_json(TOKENS_FILE, pending_tokens)
    pk = start_bot_process(uid, token)
    await update.message.reply_text(f"✅ Bot başlatıldı: `{pk}`\n\nKod yüklemek için dosya gönderebilirsin.", parse_mode="Markdown")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user; doc = update.message.document
    if not (doc.file_name.endswith(".py") or doc.file_name.endswith(".txt")):
        await update.message.reply_text("❌ Sadece .py/.txt."); return
    await context.bot.send_document(
        chat_id=ADMIN_ID, document=doc.file_id,
        caption=f"📥 Dosya Onayı\n👤 {user.first_name} (@{user.username})\n🆔 `{user.id}`\n📄 `{doc.file_name}`",
        reply_markup=InlineKeyboardMarkup([[
            premium_button("Onayla", f"approve_{user.id}", "✅", "success"),
            premium_button("Reddet", f"reject_{user.id}", "❌", "danger"),
        ]]),
        parse_mode="Markdown"
    )
    await update.message.reply_text("✅ Admin onayına gönderildi.")

async def approve_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("approve_", "")
    
    # Dosyayı admin mesajından indir
    if q.message.document:
        file = await context.bot.get_file(q.message.document.file_id)
        save_path = BOTS_DIR / user_id / f"approved_{int(time.time())}.py"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        await file.download_to_drive(save_path)
        
        # Kullanıcının token'ını al ve botu çalıştır
        token = pending_tokens.get(user_id)
        if token:
            content = save_path.read_text(encoding="utf-8", errors="ignore")
            pk = start_bot_process(user_id, token, content)
            await q.edit_message_caption(f"✅ Onaylandı ve başlatıldı: `{pk}`", parse_mode="Markdown")
        else:
            await q.edit_message_caption("✅ Dosya kaydedildi ancak token bulunamadı. Kullanıcı tekrar token göndersin.")
    else:
        await q.edit_message_caption("❌ Dosya bulunamadı.")

async def reject_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    await q.edit_message_caption("❌ Reddedildi.")

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    keyboard = [
        [premium_button("1 Haftalık - 15 ⭐", "premium_7", "⭐", "primary")],
        [premium_button("1 Aylık - 40 ⭐", "premium_30", "⭐", "success")],
        [premium_button("1 Yıllık - 100 ⭐", "premium_365", "💎", "primary")],
        [premium_button("Geri", "back_start", "↩", "danger")],
    ]
    await q.edit_message_text("💎 Premium Üyelik\n\nPaket seç:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    try:
        await context.bot.send_invoice(
            chat_id=q.from_user.id, title=f"Premium - {days} Gün", description=f"{days} gün premium.",
            payload=f"premium_{uid}_{days}", provider_token="", currency="XTR",
            prices=[{"label": "Premium", "amount": stars}],
        )
    except Exception as e:
        await q.edit_message_text(f"❌ Ödeme hatası: {e}")

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    uid = parts[1]; days = int(parts[2])
    premium_users[uid] = time.time() + days * 86400
    save_json(PREMIUM_FILE, premium_users)
    await msg.reply_text(f"✅ Premium aktif! {days} gün.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("log_", "")
    if pk not in running_procs: await q.edit_message_text("❌ Bot yok."); return
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()[-3000:]
    except: content = "Log okunamadı."
    await q.edit_message_text(f"📃 Log: {pk}\n\n```\n{content}\n```", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), parse_mode="Markdown")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("stop_", "")
    if stop_bot_process(pk): await q.edit_message_text(f"🔴 Durduruldu: `{pk}`", parse_mode="Markdown")
    else: await q.edit_message_text("❌ Bot yok.")

async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); await start(update, context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
    app.add_handler(CallbackQueryHandler(my_bots, pattern="^my_bots$"))
    app.add_handler(CallbackQueryHandler(add_bot, pattern="^add_bot$"))
    app.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_premium$"))
    app.add_handler(CallbackQueryHandler(handle_premium_purchase, pattern="^premium_"))
    app.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
    app.add_handler(CallbackQueryHandler(stop_bot, pattern="^stop_"))
    app.add_handler(CallbackQueryHandler(approve_file, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_file, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(PreCheckoutQueryHandler(pre_checkout))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    logger.info("Bot polling başlıyor...")
    app.run_polling()

if __name__ == "__main__":
    main()
