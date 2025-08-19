import sqlite3
import random
import requests
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ————— تنظیمات —————
BOT_TOKEN = "8322293345:AAHQp4Lk57wc6KrT6rv9qTMkSMATST_O1XE"
ADMIN_IDS = [6181430071, 5944937406]  # آیدی مدیرها

# حذف وب‌هوک قبلی (در صورت نیاز)
requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")

# ————— اتصال به دیتابیس —————
conn = sqlite3.connect("raffle.db", check_same_thread=False)
cursor = conn.cursor()

# جدول کاربران (با referrer_id برای تشخیص دعوت‌کننده)
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    points        INTEGER DEFAULT 0,
    chances       INTEGER DEFAULT 0,
    is_registered INTEGER DEFAULT 0,
    referrer_id   INTEGER
)
""")

# جدول قرعه‌کشی
cursor.execute("""
CREATE TABLE IF NOT EXISTS raffle (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER
)
""")

# جدول کانال‌های اجباری
cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE
)
""")

conn.commit()

# ————— منوها —————
def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["💎 افزایش امتیاز", "👤 اطلاعات حساب"],
            ["💳 تبدیل امتیاز به شانس", "🎰 ثبت نام در قرعه کشی"],
        ],
        resize_keyboard=True,
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["🎯 انتخاب برنده", "📊 آمار"],
            ["📢 ارسال پیام به همه", "📋 لیست کاربران"],
            ["➕ افزودن کانال", "📋 لیست کانال‌های جوین اجباری"],
            ["❌ حذف کانال جوین اجباری"],
            ["🏆 لیدربورد کاربران"]
        ],
        resize_keyboard=True,
    )

# ————— بررسی عضویت در کانال‌های اجباری —————
async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    cursor.execute("SELECT username FROM channels")
    for (ch,) in cursor.fetchall():
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

# ————— هندلر /start —————
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # بررسی وجود کاربر
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    existing = cursor.fetchone()

    # ثبت اولیه کاربر
    if not existing:
        cursor.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)",
            (user.id, user.username or user.first_name),
        )
        conn.commit()

        # سیستم رفرال فقط برای کاربر جدید
        if args:
            try:
                ref_id = int(args[0])
                if ref_id != user.id:
                    cursor.execute(
                        "UPDATE users SET points = points + 1 WHERE user_id=?",
                        (ref_id,),
                    )
                    cursor.execute(
                        "UPDATE users SET referrer_id=? WHERE user_id=?",
                        (ref_id, user.id),
                    )
                    conn.commit()
                    await context.bot.send_message(
                        ref_id, "🎉 با دعوت یک کاربر جدید، ۱ امتیاز گرفتید!"
                    )
            except:
                pass

    # نمایش منو بر اساس نقش
    if user.id in ADMIN_IDS:
        await update.message.reply_text("👑 پنل مدیریت", reply_markup=admin_menu())
    else:
        await update.message.reply_text("🎉 خوش آمدید!", reply_markup=main_menu())

# ————— هندلر پیام‌های متنی —————
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text or ""
    uid = update.effective_user.id

    # === بخش مدیر ===
    if uid in ADMIN_IDS:

        # آمار کلی
        if text == "📊 آمار":
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
            reg = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM raffle")
            chances = cursor.fetchone()[0]
            await msg.reply_text(f"👥 کاربران: {total}\n✅ ثبت‌نام: {reg}\n🎟 شانس‌ها: {chances}")

        # انتخاب برنده
        elif text == "🎯 انتخاب برنده":
            cursor.execute("SELECT user_id FROM raffle")
            parts = [r[0] for r in cursor.fetchall()]
            if not parts:
                await msg.reply_text("⚠️ شرکت‌کننده‌ای نیست.")
            else:
                winner = random.choice(parts)
                cursor.execute("SELECT username FROM users WHERE user_id=?", (winner,))
                name = cursor.fetchone()[0] or str(winner)
                await msg.reply_text(f"🏆 برنده: @{name}")

        # شروع حالت ارسال همگانی
        elif text == "📢 ارسال پیام به همه":
            await msg.reply_text("📤 لطفاً پیام خود را (متن/عکس/ویدیو) ارسال کنید.")
            context.user_data["broadcast"] = True

        # لیست کاربران
        elif text == "📋 لیست کاربران":
            rows = cursor.execute("SELECT username, user_id FROM users").fetchall()
            lines = [f"@{u or 'ناشناس'} ({i})" for u, i in rows]
            await msg.reply_text("👥 لیست کاربران:\n" + "\n".join(lines[:100]))

        # افزودن کانال
        elif text == "➕ افزودن کانال":
            await msg.reply_text("🔗 لطفاً یوزرنیم کانال را با @ ارسال کنید.")
            context.user_data["add_ch"] = True

        elif context.user_data.get("add_ch"):
            ch = text.strip()
            if ch.startswith("@"):
                cursor.execute("INSERT OR IGNORE INTO channels (username) VALUES (?)", (ch,))
                conn.commit()
                await msg.reply_text(f"✅ کانال {ch} اضافه شد.")
            else:
                await msg.reply_text("⚠️ یوزرنیم باید با @ شروع شود.")
            context.user_data["add_ch"] = False

        # لیست کانال‌های جوین اجباری
        elif text == "📋 لیست کانال‌های جوین اجباری":
            chs = [c[0] for c in cursor.execute("SELECT username FROM channels")]
            await msg.reply_text("📢 کانال‌های اجباری:\n" + ("\n".join(chs) or "—"))

        # حذف کانال
        elif text == "❌ حذف کانال جوین اجباری":
            await msg.reply_text("🔗 لطفاً یوزرنیم کانال برای حذف را با @ ارسال کنید.")
            context.user_data["del_ch"] = True

        elif context.user_data.get("del_ch"):
            ch = text.strip()
            cursor.execute("DELETE FROM channels WHERE username=?", (ch,))
            conn.commit()
            await msg.reply_text(f"✅ اگر کانال {ch} وجود داشت، حذف شد.")
            context.user_data["del_ch"] = False

        # لیدر بورد کاربران
        elif text == "🏆 لیدربورد کاربران":
            top = cursor.execute(
                "SELECT username, chances FROM users ORDER BY chances DESC LIMIT 10"
            ).fetchall()
            if top:
                lines = [f"{i+1}. @{u or 'ناشناس'} - {c} شانس" for i, (u, c) in enumerate(top)]
                await msg.reply_text("🏆 لیدربورد بر اساس شانس:\n" + "\n".join(lines))
            else:
                await msg.reply_text("⚠️ هیچ داده‌ای برای نمایش نیست.")

    # === بخش کاربر ===
    else:

        # بررسی عضویت
        if not await is_member(uid, context):
            chs = [c[0] for c in cursor.execute("SELECT username FROM channels")]
            btns = [
                [InlineKeyboardButton(f"عضویت در {c}", url=f"https://t.me/{c[1:]}")]
                for c in chs
            ]
            await msg.reply_text("🔒 لطفاً عضو شوید:", reply_markup=InlineKeyboardMarkup(btns))
            return

        # ثبت‌نام در قرعه‌کشی
        if text == "🎰 ثبت نام در قرعه کشی":
            reg = cursor.execute(
                "SELECT is_registered FROM users WHERE user_id=?", (uid,)
            ).fetchone()[0]
            if reg:
                await msg.reply_text("✅ شما از قبل ثبت‌نام کرده‌اید.")
            else:
                cursor.execute(
                    "UPDATE users SET is_registered=1, chances=chances+1 WHERE user_id=?",
                    (uid,),
                )
                cursor.execute("INSERT INTO raffle (user_id) VALUES (?)", (uid,))
                conn.commit()
                await msg.reply_text("🎉 ثبت‌نام شما انجام شد.")

        # افزایش امتیاز (لینک رفرال)
        elif text == "💎 افزایش امتیاز":
            link = f"https://t.me/{context.bot.username}?start={uid}"
            await msg.reply_text("🔗 لینک دعوت شما:\n" + link)

        # تبدیل امتیاز به شانس
        elif text == "💳 تبدیل امتیاز به شانس":
            pts = cursor.execute(
                "SELECT points FROM users WHERE user_id=?", (uid,)
            ).fetchone()[0]
            if pts > 0:
                cursor.execute(
                    "UPDATE users SET chances=chances+?, points=0 WHERE user_id=?",
                    (pts, uid),
                )
                for _ in range(pts):
                    cursor.execute("INSERT INTO raffle (user_id) VALUES (?)", (uid,))
                conn.commit()
                await msg.reply_text(f"✅ {pts} امتیاز تبدیل شد.")
            else:
                await msg.reply_text("⚠️ شما امتیازی ندارید.")

        # اطلاعات حساب
        elif text == "👤 اطلاعات حساب":
            u, pts, chs, reg = cursor.execute(
                "SELECT username, points, chances, is_registered FROM users WHERE user_id=?",
                (uid,),
            ).fetchone()
            st = "✅ ثبت‌نام شده" if reg else "❌ ثبت‌نام نشده"
            await msg.reply_text(
                f"👤 @{u}\n💎 امتیاز: {pts}\n🎟 شانس: {chs}\nوضعیت: {st}"
            )

# ————— هندلر ارسال رسانه در حالت همگانی —————
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = msg.from_user.id

    if uid in ADMIN_IDS and context.user_data.get("broadcast"):
        users = cursor.execute("SELECT user_id FROM users").fetchall()
        cnt = 0
        for (u,) in users:
            try:
                if msg.photo:
                    await context.bot.send_photo(u, photo=msg.photo[-1].file_id, caption=msg.caption or "")
                elif msg.video:
                    await context.bot.send_video(u, video=msg.video.file_id, caption=msg.caption or "")
                cnt += 1
            except:
                pass
        await msg.reply_text(f"✅ پیام رسانه‌ای برای {cnt} نفر ارسال شد.")
        context.user_data["broadcast"] = False

# ————— اجرای ربات —————
app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media))

print("🤖 Bot is running...")
app.run_polling()
