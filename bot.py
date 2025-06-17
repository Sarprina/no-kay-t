import os, csv, sqlite3, logging
from datetime import datetime
from telegram import Update, Bot, InputFile, ParseMode
from telegram.ext import Updater, CommandHandler, CallbackContext

# ————— AYARLAR —————
TOKEN = os.getenv('TOKEN')
REGISTER_GROUP_ID = int(os.getenv('REGISTER_GROUP_ID'))
ADMIN_GROUP_ID    = int(os.getenv('ADMIN_GROUP_ID'))
ADMINS            = set(os.getenv('ADMINS', '').split(','))
# ————————————————

logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

# Database initialization
conn = sqlite3.connect('users.db', check_same_thread=False)
conn.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    username TEXT,
    name TEXT,
    phone TEXT,
    tag TEXT DEFAULT '',
    created_at TEXT
)
""")
conn.commit()

def send_admin(bot: Bot, text: str):
    bot.send_message(chat_id=ADMIN_GROUP_ID, text=text)

def start(update: Update, ctx: CallbackContext):
    update.message.reply_text("Merhaba! /kayit <Ad> <Soyad> <Telefon> ile kayıt oluşturabilirsiniz.")

def getid(update: Update, ctx: CallbackContext):
    update.message.reply_text(f"Bu sohbetin ID’si: {update.effective_chat.id}")

def help_all(update: Update, ctx: CallbackContext):
    update.message.reply_text(
        "/kayit <Ad> <Soyad> <Telefon>\n"
        "/mynumbers\n"
        "/profile\n"
        "/tag <etiket>\n"
        "/search <isim|telefon>\n"
        "/help <komut>"
    )

def kayit(update: Update, ctx: CallbackContext):
    if update.effective_chat.id != REGISTER_GROUP_ID:
        return
    if len(ctx.args) != 3:
        return update.message.reply_text("Kullanım: /kayit Ad Soyad Telefon")
    ad, soyad, tel = ctx.args
    if not tel.startswith('+'):
        tel = '+90' + tel.lstrip('0')
    now = datetime.utcnow().isoformat()
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name

    conn.execute(
        "INSERT INTO users (telegram_id,username,name,phone,created_at) VALUES (?,?,?,?,?)",
        (uid, uname, f"{ad} {soyad}", tel, now)
    )
    conn.commit()

    try:
        ctx.bot.delete_message(REGISTER_GROUP_ID, update.message.message_id)
    except:
        pass

    # User confirmation
    ctx.bot.send_message(
        REGISTER_GROUP_ID,
        text=f"{update.effective_user.mention_markdown_v2()} kayıt başarı ile oluşturuldu",
        parse_mode=ParseMode.MARKDOWN_V2
    )
    # Notify admins
    send_admin(ctx.bot, f"[KAYIT] @{uname} — {ad} {soyad} — {tel} — {now}")

def mynumbers(update: Update, ctx: CallbackContext):
    uid = update.effective_user.id
    rows = conn.execute("SELECT name,phone,created_at FROM users WHERE telegram_id=?", (uid,)).fetchall()
    if not rows:
        return update.message.reply_text("Henüz kaydınız bulunmamaktadır.")
    update.message.reply_text("\n".join(f"{n} — {p} ({c})" for n,p,c in rows))

def profile(update: Update, ctx: CallbackContext):
    uid = update.effective_user.id
    row = conn.execute(
        "SELECT username,name,phone,created_at,tag FROM users WHERE telegram_id=? ORDER BY id DESC LIMIT 1",
        (uid,)
    ).fetchone()
    if not row:
        return update.message.reply_text("Kayıt bulunamadı.")
    uname,name,phone,created_at,tag = row
    update.message.reply_text(f"@{uname}\n{name}\n{phone}\n{created_at}\nEtiket: {tag or '-'}")

def tag(update: Update, ctx: CallbackContext):
    if len(ctx.args)!=1:
        return update.message.reply_text("Kullanım: /tag <etiket>")
    et = ctx.args[0]
    uid = update.effective_user.id
    conn.execute("UPDATE users SET tag=? WHERE telegram_id=?", (et,uid))
    conn.commit()
    update.message.reply_text(f"Etiketiniz: {et}")

def search(update: Update, ctx: CallbackContext):
    uid = update.effective_user.id
    term = ctx.args[0] if ctx.args else ""
    rows = conn.execute(
        "SELECT name,phone,created_at FROM users WHERE telegram_id=? AND (name LIKE ? OR phone LIKE ?)",
        (uid, f"%{term}%", f"%{term}%")
    ).fetchall()
    if not rows:
        return update.message.reply_text("Sonuç bulunamadı.")
    update.message.reply_text("\n".join(f"{n} — {p} ({c})" for n,p,c in rows))

def is_admin(update: Update):
    uname = (update.effective_user.username or "").lstrip('@')
    return uname in ADMINS

def list_cmd(update: Update, ctx: CallbackContext):
    if not is_admin(update): return
    page = int(ctx.args[0]) if ctx.args else 1
    per = 20; offset=(page-1)*per
    rows = conn.execute("SELECT username,name,phone,created_at,tag FROM users LIMIT ? OFFSET ?", (per,offset)).fetchall()
    if not rows:
        return update.message.reply_text("Sayfa boş.")
    update.message.reply_text("\n".join(f"@{u}: {n} — {p} ({c}) [{t}]" for u,n,p,c,t in rows))

def sil(update: Update, ctx: CallbackContext):
    if not is_admin(update): return
    if not ctx.args:
        return update.message.reply_text("Kullanım: /sil <telefon>")
    cnt=conn.execute("DELETE FROM users WHERE phone=?", (ctx.args[0],)).rowcount
    conn.commit()
    update.message.reply_text(f"{cnt} kayıt silindi.")

def stats(update: Update, ctx: CallbackContext):
    if not is_admin(update): return
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    update.message.reply_text(f"Toplam kayıt: {total}")

def broadcast(update: Update, ctx: CallbackContext):
    if not is_admin(update): return
    msg = " ".join(ctx.args)
    rows = conn.execute("SELECT DISTINCT telegram_id FROM users").fetchall()
    for (tid,) in rows:
        ctx.bot.send_message(tid, msg)

def export(update: Update, ctx: CallbackContext):
    if not is_admin(update): return
    path="export.csv"
    with open(path,"w",newline="",encoding="utf-8") as f:
        cols=["telegram_id","username","name","phone","created_at","tag"]
        writer=csv.writer(f)
        writer.writerow(cols)
        writer.writerows(conn.execute(f"SELECT {','.join(cols)} FROM users"))
    update.message.reply_document(document=InputFile(path))
    os.remove(path)

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("getid", getid))
    dp.add_handler(CommandHandler("help", help_all))
    dp.add_handler(CommandHandler("kayit", kayit))
    dp.add_handler(CommandHandler("mynumbers", mynumbers))
    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("tag", tag))
    dp.add_handler(CommandHandler("search", search))
    dp.add_handler(CommandHandler("list", list_cmd))
    dp.add_handler(CommandHandler("sil", sil))
    dp.add_handler(CommandHandler("stats", stats))
    dp.add_handler(CommandHandler("broadcast", broadcast))
    dp.add_handler(CommandHandler("export", export))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
