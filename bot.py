import sqlite3
import random
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.constants import ChatMemberStatus

BOT_TOKEN = "8227817016:AAHL4vVYIAOBmBHun6iWhezZdyXSwJBjzY8"
CHANNEL_IDS = ["@fcxter"]  # می‌توان چند کانال داد
ADMIN_IDS = [6181430071, 5944937406]  # آیدی چند مدیر
# اتصال به دیتابیس
conn = sqlite3.connect("raffle.db", check_same_thread=False)
cursor = conn.cursor()

# ایجاد جداول
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    chances INTEGER DEFAULT 0,
    is_registered INTEGER DEFAULT 0
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS raffle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER
)""")
conn.commit()

# بررسی عضویت در تمام کانال‌ها
async def is_member(user_id, context: ContextTypes.DEFAULT_TYPE):
    for channel in CHANNEL_IDS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                return False
        except:
            return False
    return True

# بررسی مدیر بودن
def is_admin(user_id):
    return user_id in ADMIN_IDS

# کیبورد کاربر
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("💎 افزایش امتیاز"), KeyboardButton("👤 اطلاعات حساب")],
        [KeyboardButton("💳 تبدیل امتیاز به شانس")],
        [KeyboardButton("🎰 ثبت نام در قرعه کشی")]
    ], resize_keyboard=True)

# کیبورد مدیر
def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🎯 انتخاب برنده"), KeyboardButton("👥 انتخاب چند برنده")],
        [KeyboardButton("📢 ارسال پیام به همه"), KeyboardButton("📊 آمار")],
        [KeyboardButton("🔄 ریست قرعه‌کشی")]
    ], resize_keyboard=True)

# شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    if not await is_member(user_id, context):
        channels_list = "\n".join([f"🔗 {c}" for c in CHANNEL_IDS])
        await update.message.reply_text(f"🔒 برای استفاده از ربات باید در کانال‌های زیر عضو شوید:\n\n{channels_list}")
        return

    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()

    if is_admin(user_id):
        await update.message.reply_text("📌 پنل مدیریت فعال شد!", reply_markup=admin_menu())
    else:
        await update.message.reply_text("🎉 به ربات قرعه‌کشی خوش آمدید!", reply_markup=main_menu())

# مدیریت پیام‌ها
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    # کاربر عادی
    if not is_admin(user_id):
        if text == "🎰 ثبت نام در قرعه کشی":
            cursor.execute("UPDATE users SET is_registered = 1 WHERE user_id = ?", (user_id,))
            cursor.execute("INSERT INTO raffle (user_id) VALUES (?)", (user_id,))
            conn.commit()
            await update.message.reply_text("✅ شما در قرعه‌کشی ثبت نام شدید!")

        elif text == "💎 افزایش امتیاز":
            link = f"https://t.me/{context.bot.username}?start={user_id}"
            await update.message.reply_text(f"🔗 لینک اختصاصی شما:\n{link}")

        elif text == "💳 تبدیل امتیاز به شانس":
            cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
            points = cursor.fetchone()[0]
            if points > 0:
                cursor.execute("UPDATE users SET points = 0, chances = chances + ? WHERE user_id = ?", (points, user_id))
                for _ in range(points):
                    cursor.execute("INSERT INTO raffle (user_id) VALUES (?)", (user_id,))
                conn.commit()
                await update.message.reply_text("✅ امتیازها به شانس تبدیل شد!")
            else:
                await update.message.reply_text("⚠️ شما امتیازی برای تبدیل ندارید.")

        elif text == "👤 اطلاعات حساب":
            cursor.execute("SELECT points, chances, is_registered FROM users WHERE user_id = ?", (user_id,))
            points, chances, registered = cursor.fetchone()
            status = "بله" if registered else "خیر"
            await update.message.reply_text(f"📊 اطلاعات حساب:\n\nثبت‌نام: {status}\nامتیاز: {points}\nشانس: {chances}")

    # مدیران
    else:
        if text == "🎯 انتخاب برنده":
            cursor.execute("SELECT user_id FROM raffle")
            participants = [row[0] for row in cursor.fetchall()]
            if not participants:
                await update.message.reply_text("⚠️ هنوز کسی در قرعه‌کشی ثبت‌نام نکرده.")
                return
            winner_id = random.choice(participants)
            cursor.execute("SELECT username FROM users WHERE user_id = ?", (winner_id,))
            winner_username = cursor.fetchone()[0]
            await update.message.reply_text(f"🎉 برنده قرعه‌کشی: @{winner_username}")

        elif text == "👥 انتخاب چند برنده":
            cursor.execute("SELECT user_id FROM raffle")
            participants = [row[0] for row in cursor.fetchall()]
            if not participants:
                await update.message.reply_text("⚠️ هیچ شرکت‌کننده‌ای نیست.")
                return
            winners = random.sample(participants, min(3, len(participants)))
            result = []
            for w in winners:
                cursor.execute("SELECT username FROM users WHERE user_id = ?", (w,))
                result.append("@" + cursor.fetchone()[0])
            await update.message.reply_text("🎯 برندگان:\n" + "\n".join(result))

        elif text == "📢 ارسال پیام به همه":
            await update.message.reply_text("✍️ پیام خود را ارسال کنید:")
            context.user_data["broadcast"] = True

        elif text == "📊 آمار":
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users WHERE is_registered = 1")
            registered_users = cursor.fetchone()[0]

            cursor.execute("SELECT SUM(points) FROM users")
            total_points = cursor.fetchone()[0] or 0

            cursor.execute("SELECT SUM(chances) FROM users")
            total_chances = cursor.fetchone()[0] or 0

            await update.message.reply_text(
                f"📊 آمار کلی:\n\n👥 تعداد کاربران: {total_users}\n✅ ثبت‌نامی‌ها: {registered_users}\n💎 مجموع امتیازها: {total_points}\n🎰 مجموع شانس‌ها: {total_chances}"
            )

        elif text == "🔄 ریست قرعه‌کشی":
            cursor.execute("DELETE FROM raffle")
            conn.commit()
            await update.message.reply_text("✅ قرعه‌کشی ریست شد!")

        elif context.user_data.get("broadcast"):
            cursor.execute("SELECT user_id FROM users")
            users = [row[0] for row in cursor.fetchall()]
            for u in users:
                try:
                    await context.bot.send_message(u, text)
                except:
                    pass
            context.user_data["broadcast"] = False
            await update.message.reply_text("✅ پیام به همه ارسال شد!")

# لینک دعوت
async def start_with_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_user_id = update.effective_user.id
    if len(context.args) > 0:
        ref_id = int(context.args[0])
        if ref_id != new_user_id:
            cursor.execute("UPDATE users SET points = points + 1 WHERE user_id = ?", (ref_id,))
            conn.commit()
            # پیام به معرف
            try:
                await context.bot.send_message(ref_id, f"🎉 یک کاربر جدید با لینک شما وارد ربات شد!")
            except:
                pass
    await start(update, context)  # بعد از بررسی ریفرال، منو نشون داده میشه

# اجرای ربات
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_with_referral))
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.run_polling()

if __name__ =="__main__":
    main()
