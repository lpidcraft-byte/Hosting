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
from pathlib import Path
from flask import Flask, request, Response

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler
)

# --- Ayarlar ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9053394489:AAEMkxfOuDRVTcTY4mWluMgNdDbj-Y9ryMY")
ADMIN_ID = 8913966694
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

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

def premium_button(text, callback_data, emoji="✅", style=None):
    kw = {"text": text, "callback_data": callback_data}
    if emoji in EMOJI_IDS:
        kw["icon_custom_emoji_id"] = str(EMOJI_IDS[emoji])
    if style:
        kw["style"] = style
    return InlineKeyboardButton(**kw)

def is_premium(user_id):
    return global_state["premium"].get(str(user_id), 0) > time.time()

def check_bot_limit(user_id):
    uid = str(user_id)
    count = sum(1 for k in running_procs if k.startswith(uid + "_"))
    return count < (5 if is_premium(uid) else 1)

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
    proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env={**os.environ, "BOT_TOKEN": bot_token})
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

# --- Ana Menü Fonksiyonu (Hem /start hem Callback için çalışır) ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Eğer komutla (/start) gelindiyse kullanıcıyı kaydet
    if update.message:
        uid = str(user.id)
        global_state["users"][uid] = {"username": user.username or "", "first_name": user.first_name or ""}
        save_state()
    
    keyboard = []
    if user.id == ADMIN_ID:
        keyboard.append([premium_button("Admin Paneli", "admin_panel", "👮‍♀", "primary")])
    keyboard.append([premium_button("Botlarım", "my_bots", "🤖", "success")])
    keyboard.append([premium_button("Premium Al", "buy_premium", "💎", "primary")])
    
    text = f"👋 Merhaba {user.first_name}!\n\nBotunu çalıştırmak için '.py' dosyanı buraya gönder."
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Eğer mesaj komutla geldiyse yeni mesaj at, butonla geldiyse mesajı düzenle
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return await q.edit_message_text("⛔ Yetkisiz.")
    keyboard = [[premium_button("Kullanıcı Listesi", "user_list", "👥", "primary")], [premium_button("Geri", "back_start", "↩", "danger")]]
    await q.edit_message_text("👮‍♀ Admin Paneli", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    text = "👥 Kullanıcı Listesi\n\n"
    for uid, info in list(global_state["users"].items())[:50]:
        ps = "💎" if is_premium(uid) else ""
        text += f"🆔 `{uid}` | @{info.get('username','yok')} | {info.get('first_name','')} {ps}\n"
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "admin_panel", "↩", "danger")]]), parse_mode="Markdown")

async def my_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = str(q.from_user.id)
    bl = [k for k in running_procs if k.startswith(uid + "_")]
    
    if not bl:
        return await q.edit_message_text("🤖 Botun yok. Çalıştırmak için .py dosyanı gönder.", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "back_start", "↩", "danger")]]))
    
    keyboard = []
    text = "🤖 **Botların:**\n\n"
    
    for i, pk in enumerate(bl):
        st = "🟢 Çalışıyor" if running_procs[pk]["proc"].poll() is None else "🔴 Durdu"
        text += f"{i+1}. `{running_procs[pk]['name']}` - {st}\n"
        
        if running_procs[pk]["proc"].poll() is None:
            keyboard.append([
                premium_button(f"Log Al", f"log_{pk}", "📃", "primary"),
                premium_button(f"Durdur", f"stop_{pk}", "⏹", "danger")
            ])
        else:
            keyboard.append([
                premium_button(f"Log Al", f"log_{pk}", "📃", "primary"),
                premium_button(f"Başlat", f"start_{pk}", "▶", "success"),
                premium_button(f"Sil", f"del_{pk}", "🗑", "danger")
            ])
            
    keyboard.append([premium_button("Geri", "back_start", "↩", "danger")])
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def start_stopped_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("start_", "")
    
    if pk in running_procs:
        info = running_procs[pk]
        bot_dir = DATA_DIR / "user_bots" / info["user_id"]
        script_path = bot_dir / f"bot_{pk}.py"
        log_path = info["log_path"]
        
        if script_path.exists():
            log_file = open(log_path, "a", encoding="utf-8")
            proc = subprocess.Popen([sys.executable, str(script_path)], stdout=log_file, stderr=subprocess.STDOUT, cwd=str(bot_dir), env={**os.environ, "BOT_TOKEN": info["token"]})
            running_procs[pk]["proc"] = proc
            await q.edit_message_text(f"▶ Bot yeniden başlatıldı: `{info['name']}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
        else:
            await q.edit_message_text("❌ Bot dosyası bulunamadı. Lütfen tekrar yükleyin.")
    else:
        await q.edit_message_text("❌ Bot bulunamadı.")

async def delete_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    pk = q.data.replace("del_", "")
    
    if pk in running_procs:
        info = running_procs[pk]
        name = info["name"]
        if info["proc"].poll() is None:
            info["proc"].terminate()
        del running_procs[pk]
        await q.edit_message_text(f"🗑 Bot silindi: `{name}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
    else:
        await q.edit_message_text("❌ Bot zaten yok.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    doc = update.message.document
    
    if not doc.file_name.endswith(".py"):
        return await update.message.reply_text("❌ Sadece `.py` uzantılı dosyalar kabul edilir.")
    
    if not check_bot_limit(str(user.id)):
        return await update.message.reply_text("⚠️ Limit doldu! Premium alman lazım.")
    
    file = await context.bot.get_file(doc.file_id)
    tmp = DATA_DIR / f"tmp_{user.id}.py"
    await file.download_to_drive(tmp)
    
    code = tmp.read_text(encoding="utf-8", errors="ignore")
    token_match = re.search(r"(\d+:[A-Za-z0-9_-]+)", code)
    
    if not token_match:
        return await update.message.reply_text(
            "❌ **Hata:** Dosyanın içinde geçerli bir Telegram Bot Token'ı bulunamadı!\n\n"
            "Token şu formatta olmalı: `123456789:ABCdef...`", 
            parse_mode="Markdown"
        )
    
    extracted_token = token_match.group(1)
    bot_name = doc.file_name.replace(".py", "")
    
    context.bot_data[f"code_{user.id}"] = code
    context.bot_data[f"token_{user.id}"] = extracted_token
    context.bot_data[f"name_{user.id}"] = bot_name
    
    if is_premium(user.id):
        global_state["bot_codes"][str(user.id)] = code
        save_state()
        pk = start_bot_process(str(user.id), extracted_token, code, bot_name)
        await update.message.reply_text(f"✅ **Premium Üye:** Dosyanız onay beklenmeden başlatıldı!\nBot Adı: `{bot_name}`", parse_mode="Markdown")
    else:
        await context.bot.send_document(
            chat_id=ADMIN_ID, document=doc.file_id,
            caption=f"📥 **Dosya Onayı (Ücretsiz Üye)**\n\n"
                    f"👤 Kullanıcı: {user.first_name} (@{user.username})\n"
                    f"🆔 ID: `{user.id}`\n"
                    f"🤖 Bulunan Token: `{extracted_token}`\n"
                    f"📄 Dosya: `{doc.file_name}`",
            reply_markup=InlineKeyboardMarkup([[
                premium_button("Onayla", f"approve_{user.id}", "✅", "success"),
                premium_button("Reddet", f"reject_{user.id}", "❌", "danger")
            ]]),
            parse_mode="Markdown"
        )
        await update.message.reply_text("⏳ Dosyan admin onayına gönderildi. Lütfen bekle.")

async def approve_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("approve_", "")
    
    code = context.bot_data.get(f"code_{user_id}")
    token = context.bot_data.get(f"token_{user_id}")
    name = context.bot_data.get(f"name_{user_id}", "Bot")
    
    if code and token:
        global_state["bot_codes"][user_id] = code
        save_state()
        pk = start_bot_process(user_id, token, code, name)
        
        await q.edit_message_caption(f"✅ Onaylandı ve başlatıldı.\nBot Adı: `{name}`", parse_mode="Markdown")
        
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"✅ **Sevgili kullanıcı,**\n\nDosyanız moderatörler tarafından incelendi ve aksilik tespit edilmedi, dosyanız çalışır halde, iyi kullanımlar!"
            )
        except: pass
    else:
        await q.edit_message_caption("❌ Hata: Kod veya token hafızada bulunamadı.")

async def reject_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.from_user.id != ADMIN_ID: return
    user_id = q.data.replace("reject_", "")
    
    await q.edit_message_caption("❌ Reddedildi.")
    
    try:
        await context.bot.send_message(
            chat_id=int(user_id),
            text=f"❌ **Sevgili kullanıcı,**\n\nMaalesef dosyanız moderatörler tarafından incelendi ve bir aksilik çıkarak reddedildi."
        )
    except: pass

async def buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    keyboard = [
        [premium_button("1 Haftalık - 15 ⭐", "premium_7", "⭐", "primary")], 
        [premium_button("1 Aylık - 40 ⭐", "premium_30", "⭐", "success")], 
        [premium_button("1 Yıllık - 100 ⭐", "premium_365", "💎", "primary")], 
        [premium_button("Geri", "back_start", "↩", "danger")]
    ]
    
    text = (
        "💎 **Premium Üyelik Avantajları**\n\n"
        "👑 Normal kullanıcılar sadece **1** bot çalıştırabilir.\n"
        "⚡ Premium üyeler aynı anda **5** bot çalıştırabilir!\n"
        "🚀 Dosya yüklemelerinde **onay beklemez**, anında çalışır!\n"
        "🎁 Sunucu kaynaklarında öncelik verilir.\n\n"
        "Aşağıdan sana uygun paketi seçebilirsin:"
    )
    
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def handle_premium_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); uid = str(q.from_user.id); days = int(q.data.replace("premium_", ""))
    stars = 15 if days == 7 else (40 if days == 30 else 100)
    try:
        await context.bot.send_invoice(chat_id=q.from_user.id, title=f"Premium - {days} Gün", description=f"{days} gün premium.", payload=f"premium_{uid}_{days}", provider_token="", currency="XTR", prices=[{"label": "Premium", "amount": stars}])
    except Exception as e:
        await q.edit_message_text(f"❌ Ödeme sistemi hatası: {e}")

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message; parts = msg.successful_payment.invoice_payload.split("_")
    global_state["premium"][parts[1]] = time.time() + int(parts[2]) * 86400
    save_state()
    await msg.reply_text(f"✅ Premium aktif! {parts[2]} gün.")

async def log_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("log_", "")
    if pk not in running_procs: return await q.edit_message_text("❌ Bot yok.")
    try:
        with open(running_procs[pk]["log_path"], "r", encoding="utf-8", errors="ignore") as f: content = f.read()[-3000:]
    except: content = "Log yok."
    await q.edit_message_text(f"📃 Log: {running_procs[pk]['name']}\n\n```\n{content}\n```", reply_markup=InlineKeyboardMarkup([[premium_button("Geri", "my_bots", "↩", "danger")]]), parse_mode="Markdown")

async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer(); pk = q.data.replace("stop_", "")
    if stop_bot_process(pk): 
        await q.edit_message_text(f"🔴 Bot durduruldu.\nİşlem: `{pk}`", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[premium_button("Botlarıma Dön", "my_bots", "↩", "primary")]]))
    else: 
        await q.edit_message_text("❌ Bot yok.")

# --- Handler Kayıtları ---
application.add_handler(CommandHandler("start", start_command))
application.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
application.add_handler(CallbackQueryHandler(user_list, pattern="^user_list$"))
application.add_handler(CallbackQueryHandler(my_bots, pattern="^my_bots$"))
application.add_handler(CallbackQueryHandler(buy_premium, pattern="^buy_premium$"))
application.add_handler(CallbackQueryHandler(handle_premium_purchase, pattern="^premium_"))
application.add_handler(CallbackQueryHandler(log_view, pattern="^log_"))
application.add_handler(CallbackQueryHandler(stop_bot, pattern="^stop_"))
application.add_handler(CallbackQueryHandler(start_stopped_bot, pattern="^start_"))
application.add_handler(CallbackQueryHandler(delete_bot, pattern="^del_"))
application.add_handler(CallbackQueryHandler(approve_file, pattern="^approve_"))
application.add_handler(CallbackQueryHandler(reject_file, pattern="^reject_"))
# Geri butonu artık özel show_main_menu fonksiyonuna gidiyor
application.add_handler(CallbackQueryHandler(show_main_menu, pattern="^back_start$"))
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
