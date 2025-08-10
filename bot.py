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

BOT_TOKEN = ""
ADMIN_IDS = [6181430071, 5944937406]  # آیدی مدیرها

# حذف وب‌هوک قبلی (در صورت نیاز)
try:
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook")
except:
    pass

# ————— اتصال به دیتابیس —————

conn = sqlite3.connect("raffle.db", check_same_thread=False)
cursor = conn.cursor()

# جدول کاربران
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    points        INTEGER DEFAULT 0,
    chances       INTEGER DEFAULT 0,
    is_registered INTEGER DEFAULT 0
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
            ["❌ حذف کانال جوین اجباری", "🔄 ریست قرعه‌کشی"],
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

    # بررسی اینکه کاربر قبلاً وجود داشته یا نه (تا در اجرای رفرال از آن استفاده کنیم)
    cursor.execute("SELECT 1 FROM users WHERE user_id=?", (user.id,))
    existed = cursor.fetchone() is not None

    # اگر کاربر جدید است ثبتش کن
    if not existed:
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user.id, user.username or user.first_name),
        )
        conn.commit()

    # سیستم رفرال: فقط وقتی کاربر واقعاً جدید است امتیاز به معرف اضافه کن
    if args:
        try:
            ref_id = int(args[0])
            if ref_id != user.id and not existed:
                cursor.execute("SELECT points, chances FROM users WHERE user_id=?", (ref_id,))
                row = cursor.fetchone()
                if row:
                    pts, chs = (row[0] or 0, row[1] or 0)
                    total = pts + chs
                    if total < 20:
                        add = min(1, 20 - total)  # حداکثر تا سقف ۲۰ اضافه کن
                        cursor.execute("UPDATE users SET points = points + ? WHERE user_id=?", (add, ref_id))
                        conn.commit()
                        # فقط وقتی واقعا امتیاز اضافه شده به معرف پیام بفرست
                        if add > 0:
                            try:
                                await context.bot.send_message(ref_id, "🎉 با دعوت یک کاربر، ۱ امتیاز گرفتید!")
                            except:
                                pass
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
                row = cursor.fetchone()
                name = (row[0] if row and row[0] else str(winner))
                await msg.reply_text(f"🏆 برنده: @{name}")

        # شروع حالت ارسال همگانی
        elif text == "📢 ارسال پیام به همه":
            await msg.reply_text("📤 لطفاً پیام خود را (متن/عکس/ویدیو) ارسال کنید.")
            context.user_data["broadcast"] = True

        # لیست کاربران
        elif text == "📋 لیست کاربران":
            rows = cursor.execute("SELECT username, user_id FROM users").fetchall()
            lines = [f"@{u or 'ناشناس'} ({i})" for u, i in rows]
            await msg.reply_text("👥 لیست کاربران:\n\n" + "\n".join(lines[:100]))

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
            await msg.reply_text("📢 کانال‌های اجباری:\n\n" + ("\n".join(chs) or "—"))

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

        # ریست قرعه‌کشی
        elif text == "🔄 ریست قرعه‌کشی":
            cursor.execute("DELETE FROM raffle")
            cursor.execute("UPDATE users SET is_registered=0, chances=0")
            conn.commit()
            await msg.reply_text("♻️ قرعه‌کشی ریست شد.")

        # لیدربورد کاربران
        elif text == "🏆 لیدربورد کاربران":
            top = cursor.execute(
                "SELECT username, chances FROM users ORDER BY chances DESC LIMIT 10"
            ).fetchall()
            if top:
                lines = [f"{i+1}. @{u or 'ناشناس'} - {c} شانس" for i, (u, c) in enumerate(top)]
                await msg.reply_text("🏆 لیدربورد بر اساس شانس:\n\n" + "\n".join(lines))
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
            cursor.execute("SELECT is_registered, points, chances FROM users WHERE user_id=?", (uid,))
            row = cursor.fetchone()
            if row:
                reg, pts, chs = (row[0], row[1] or 0, row[2] or 0)
            else:
                reg, pts, chs = (0, 0, 0)
            if reg:
                await msg.reply_text("✅ شما از قبل ثبت‌نام کرده‌اید.")
            else:
                # بررسی سقف ۲۰ برای مجموع امتیاز و شانس
                if pts + chs >= 20:
                    await msg.reply_text("⚠️ امکان ثبت‌نام بیشتر وجود ندارد؛ مجموع امتیاز و شانس شما به سقف ۲۰ رسیده است.")
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
            await msg.reply_text("🔗 لینک دعوت شما:\n\n" + link)

        # تبدیل امتیاز به شانس
        elif text == "💳 تبدیل امتیاز به شانس":
            cursor.execute(
                "SELECT points, chances FROM users WHERE user_id=?", (uid,)
            )
            row = cursor.fetchone()
            if not row:
                await msg.reply_text("⚠️ حساب شما پیدا نشد.")
                return
            points, chances = (row[0] or 0, row[1] or 0)
            if points > 0:
                # فضای خالی تا سقف ۲۰ برای شانس‌ها
                space = 20 - chances
                pts_to_convert = min(points, space)
                if pts_to_convert <= 0:
                    await msg.reply_text("⚠️ شما نمی‌توانید بیش از ۲۰ شانس داشته باشید.")
                else:
                    cursor.execute(
                        "UPDATE users SET chances=chances+?, points=points-? WHERE user_id=?",
                        (pts_to_convert, pts_to_convert, uid),
                    )
                    for _ in range(pts_to_convert):
                        cursor.execute("INSERT INTO raffle (user_id) VALUES (?)", (uid,))
                    conn.commit()
                    await msg.reply_text(f"✅ {pts_to_convert} امتیاز تبدیل شد.")
            else:
                await msg.reply_text("⚠️ شما امتیازی ندارید.")

        # اطلاعات حساب
        elif text == "👤 اطلاعات حساب":
            cursor.execute(
                "SELECT username, points, chances, is_registered FROM users WHERE user_id=?",
                (uid,),
            )
            row = cursor.fetchone()
            if row:
                u, pts, chs, reg = row
                st = "✅ ثبت‌نام شده" if reg else "❌ ثبت‌نام نشده"
                await msg.reply_text(
                    f"👤 @{u}\n💎 امتیاز: {pts}\n🎟 شانس: {chs}\nوضعیت: {st}"
                )
            else:
                await msg.reply_text("⚠️ حساب شما پیدا نشد.")

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
                else:
                    # اگر پیام فقط متن بود یا نوع دیگری بود، سعی کن متن را بفرستی
                    if msg.text:
                        await context.bot.send_message(u, msg.text)
                cnt += 1
            except:
                pass
        await msg.reply_text(f"✅ پیام رسانه‌ای برای {cnt} نفر ارسال شد.")
        context.user_data["broadcast"] = False

# ————— اجرای ربات —————

app = Application.builder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(MessageHandler((filters.PHOTO | filters.VIDEO | filters.Text(True)), handle_media))

print("🤖 Bot is running...")
app.run_polling()


