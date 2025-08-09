# -*- coding: utf-8 -*-
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

# -------------------- تنظیمات --------------------
BOT_TOKEN = "8322293345:AAHQp4Lk57wc6KrT6rv9qTMkSMATST_O1XE"   # <- این را عوض کن
ADMIN_IDS = [6181430071, 5944937406]        # آیدی مدیرها (در صورت نیاز ویرایش کن)
MAX_CHANCES = 20                            # سقف تعداد شانس
MAX_REFERRAL_TOTAL = 50                     # اگر مجموع (points+chances) >= این مقدار، رفرال امتیاز نمیدهد

# حذف وبهوک قبلی تا با polling تداخل نداشته باشه
try:
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", timeout=5)
except Exception:
    pass

# -------------------- دیتابیس --------------------
conn = sqlite3.connect("raffle.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    points INTEGER DEFAULT 0,
    chances INTEGER DEFAULT 0,
    is_registered INTEGER DEFAULT 0,
    referred_by INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS raffle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE
)
""")

conn.commit()

# -------------------- منوها --------------------
def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["💎 افزایش امتیاز", "👤 اطلاعات حساب"],
            ["💳 تبدیل امتیاز به شانس", "🎰 ثبت نام در قرعه کشی"],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["🎯 انتخاب برنده", "📊 آمار"],
            ["📢 ارسال پیام به همه", "📋 لیست کاربران"],
            ["➕ افزودن کانال", "📋 لیست کانال‌های جوین اجباری"],
            ["❌ حذف کانال جوین اجباری", "🔄 ریست قرعه‌کشی"],
            ["🏆 لیدربورد کاربران", "⛔ بن از قرعه کشی"],
            ["➕ امتیاز به همه", "➕ امتیاز به کاربر"],
            ["➖ کسر امتیاز از کاربر"]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

# -------------------- کمکی‌ها --------------------
async def get_required_channels():
    cursor.execute("SELECT username FROM channels")
    return [row[0] for row in cursor.fetchall()]

async def is_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channels = await get_required_channels()
    if not channels:
        return True  # اگر هیچ کانالی تعریف نشده، شرط عضویت را دور می‌زنیم
    for ch in channels:
        try:
            member = await context.bot.get_chat_member(ch, user_id)
            if member.status not in ("member", "administrator", "creator", "owner"):
                return False
        except Exception:
            # اگر ارور گرفتیم (مثلاً ربات دسترسی نداشته) فرض می‌کنیم عضو نیست
            return False
    return True

def normalize_username(text: str) -> str:
    if not text:
        return text
    return text.lstrip("@").strip().lower()

def find_user_by_username_input(text: str):
    uname = normalize_username(text)
    cursor.execute("SELECT user_id, username FROM users WHERE lower(username)=? OR username=?", (uname, text, ))
    row = cursor.fetchone()
    if row:
        return row[0], row[1]
    return None, None

def insert_raffle_entries(user_id: int, count: int):
    if count <= 0:
        return
    cursor.executemany("INSERT INTO raffle (user_id) VALUES (?)", [(user_id,) for _ in range(count)])
    conn.commit()

# -------------------- /start --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    uname = user.username or user.first_name or ""
    args = context.args or []

    # آیا کاربر قبلاً وجود داشته؟
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (uid,))
    exists = cursor.fetchone() is not None

    if not exists:
        # ذخیره کاربر جدید
        cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
            (uid, uname, None)
        )
        conn.commit()

        # اگر آرگومان استارت (ریف) وجود دارد و عددی است، امتیاز به معرف بده
        if args:
            try:
                ref_id = int(args[0])
                if ref_id != uid:
                    cursor.execute("SELECT points, chances FROM users WHERE user_id=?", (ref_id,))
                    row = cursor.fetchone()
                    if row:
                        total = (row[0] or 0) + (row[1] or 0)
                        if total < MAX_REFERRAL_TOTAL:
                            cursor.execute("UPDATE users SET points = points + 1 WHERE user_id=?", (ref_id,))
                            cursor.execute("UPDATE users SET referred_by = ? WHERE user_id=?", (ref_id, uid))
                            conn.commit()
                            try:
                                await context.bot.send_message(ref_id, "🎉 یک کاربر جدید با لینک شما استارت زد — ۱ امتیاز گرفتید!")
                            except Exception:
                                pass
            except Exception:
                pass
    else:
        # اگر از قبل بود، آپدیت یوزرنیم کن (کاربر ممکنه یوزرنیمشو تغییر داده باشه)
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (uname, uid))
        conn.commit()

    # نمایش منو (همیشه نمایش داده شود؛ ولی عملکرد دکمه‌ها برای کاربران چک می‌شود)
    if uid in ADMIN_IDS:
        await update.message.reply_text("👑 پنل مدیریت فعال شد.", reply_markup=admin_menu())
    else:
        await update.message.reply_text("🎉 به ربات خوش آمدید!", reply_markup=main_menu())

# -------------------- پیام‌ها (متن، عکس، ویدئو) --------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    text = (msg.text or "").strip()
    uid = update.effective_user.id

    # ---------- اگر ادمین ----------
    if uid in ADMIN_IDS:
        # اگر در حالت ارسال همگانی باشیم (هم متن، هم عکس/ویدئو)
        if context.user_data.get("broadcast"):
            context.user_data.pop("broadcast", None)
            users = cursor.execute("SELECT user_id FROM users").fetchall()
            success = 0
            for (u,) in users:
                try:
                    if msg.photo:
                        await context.bot.send_photo(u, photo=msg.photo[-1].file_id, caption=msg.caption or "")
                    elif msg.video:
                        await context.bot.send_video(u, video=msg.video.file_id, caption=msg.caption or "")
                    else:
                        await context.bot.send_message(u, text=msg.text or "")
                    success += 1
                except Exception:
                    continue
            await msg.reply_text(f"✅ پیام برای {success} کاربر ارسال شد.", reply_markup=admin_menu())
            return

        # آمار
        if text == "📊 آمار":
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
            registered = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM raffle")
            total_chances = cursor.fetchone()[0]
            await msg.reply_text(f"📊 آمار:\n\n👥 کل کاربران: {total}\n✅ ثبت‌نامی‌ها: {registered}\n🎟️ مجموع شانس‌ها: {total_chances}", reply_markup=admin_menu())
            return

        # انتخاب برنده
        if text == "🎯 انتخاب برنده":
            cursor.execute("SELECT user_id FROM raffle")
            participants = [r[0] for r in cursor.fetchall()]
            if not participants:
                await msg.reply_text("⚠️ هنوز هیچ شرکت‌کننده‌ای در قرعه‌کشی ثبت نشده.", reply_markup=admin_menu())
                return
            winner_id = random.choice(participants)
            cursor.execute("SELECT username FROM users WHERE user_id=?", (winner_id,))
            row = cursor.fetchone()
            winner_name = ("@" + row[0]) if row and row[0] else str(winner_id)
            await msg.reply_text(f"🏆 برنده: {winner_name}", reply_markup=admin_menu())
            try:
                await context.bot.send_message(winner_id, "🎉 تبریک! شما برنده قرعه‌کشی شدید!")
            except Exception:
                pass
            return

        # لیست کاربران
        if text == "📋 لیست کاربران":
            rows = cursor.execute("SELECT username, user_id FROM users").fetchall()
            if not rows:
                await msg.reply_text("📋 هیچ کاربری ثبت نشده.", reply_markup=admin_menu())
                return
            lines = [f"@{r[0] or 'ناشناس'} ({r[1]})" for r in rows]
            await msg.reply_text("📋 لیست کاربران:\n\n" + "\n".join(lines[:200]), reply_markup=admin_menu())
            return

        # افزودن کانال
        if text == "➕ افزودن کانال":
            context.user_data["add_channel"] = True
            await msg.reply_text("🔗 لطفاً یوزرنیم کانال را با @ ارسال کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("add_channel"):
            context.user_data.pop("add_channel", None)
            ch = text.strip()
            if ch.startswith("@"):
                cursor.execute("INSERT OR IGNORE INTO channels (username) VALUES (?)", (ch,))
                conn.commit()
                await msg.reply_text(f"✅ کانال {ch} اضافه شد.", reply_markup=admin_menu())
            else:
                await msg.reply_text("⚠️ آیدی کانال باید با @ شروع شود.", reply_markup=admin_menu())
            return

        # لیست کانال‌ها
        if text == "📋 لیست کانال‌های جوین اجباری":
            cursor.execute("SELECT username FROM channels")
            chs = [r[0] for r in cursor.fetchall()]
            await msg.reply_text("📢 کانال‌های اجباری:\n\n" + ("\n".join(chs) if chs else "—"), reply_markup=admin_menu())
            return

        # حذف کانال
        if text == "❌ حذف کانال جوین اجباری":
            cursor.execute("SELECT username FROM channels")
            chs = [r[0] for r in cursor.fetchall()]
            if not chs:
                await msg.reply_text("⚠️ هیچ کانالی ثبت نشده.", reply_markup=admin_menu())
                return
            context.user_data["delete_channel"] = True
            await msg.reply_text("🔗 لطفاً آیدی کانال برای حذف را با @ ارسال کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("delete_channel"):
            context.user_data.pop("delete_channel", None)
            ch = text.strip()
            cursor.execute("DELETE FROM channels WHERE username=?", (ch,))
            conn.commit()
            await msg.reply_text(f"✅ اگر کانال {ch} وجود داشت، حذف شد.", reply_markup=admin_menu())
            return

        # ریست قرعه‌کشی (دو مرحله‌ای)
        if text == "🔄 ریست قرعه‌کشی":
            context.user_data["confirm_reset"] = True
            await msg.reply_text("⚠️ برای انجام ریست کامل بنویسید: ریست\nبرای لغو بنویسید: خیر", reply_markup=admin_menu())
            return
        if context.user_data.get("confirm_reset"):
            if text == "ریست":
                cursor.execute("DELETE FROM raffle")
                cursor.execute("UPDATE users SET is_registered=0, chances=0")
                conn.commit()
                context.user_data.pop("confirm_reset", None)
                context.user_data["confirm_reset_delete"] = True
                await msg.reply_text("✅ قرعه‌کشی ریست شد. اگر می‌خواهید کاربران را هم حذف کنید بنویسید: پاک کن\nبرای نگه داشتن کاربران بنویسید: خیر", reply_markup=admin_menu())
            else:
                context.user_data.pop("confirm_reset", None)
                await msg.reply_text("❌ عملیات ریست لغو شد.", reply_markup=admin_menu())
            return
        if context.user_data.get("confirm_reset_delete"):
            if text == "پاک کن":
                cursor.execute("DELETE FROM raffle")
                cursor.execute("DELETE FROM users")
                conn.commit()
                await msg.reply_text("🗑️ همه کاربران و اطلاعات مربوطه پاک شدند.", reply_markup=admin_menu())
            else:
                await msg.reply_text("ℹ️ کاربران حفظ شدند — ریست کامل انجام نشد.", reply_markup=admin_menu())
            context.user_data.pop("confirm_reset_delete", None)
            return

        # لیدربورد (فقط برای ادمین)
        if text == "🏆 لیدربورد کاربران":
            rows = cursor.execute("SELECT username, chances FROM users ORDER BY chances DESC LIMIT 10").fetchall()
            if not rows:
                await msg.reply_text("⚠️ داده‌ای برای نمایش وجود ندارد.", reply_markup=admin_menu())
                return
            lines = [f"{i+1}. @{r[0] or 'ناشناس'} — {r[1]} شانس" for i, r in enumerate(rows)]
            await msg.reply_text("🏆 لیدربورد (بر اساس شانس):\n\n" + "\n".join(lines), reply_markup=admin_menu())
            return

        # بن از قرعه کشی
        if text == "⛔ بن از قرعه کشی":
            context.user_data["ban_waiting"] = True
            await msg.reply_text("🔒 لطفاً یوزرنیم کاربر را با @ وارد کنید تا از قرعه‌کشی بن شود و امتیازاتش پاک شود.", reply_markup=admin_menu())
            return
        if context.user_data.get("ban_waiting"):
            context.user_data.pop("ban_waiting", None)
            if not text.startswith("@"):
                await msg.reply_text("⚠️ لطفاً یوزرنیم را با @ ارسال کنید.", reply_markup=admin_menu())
                return
            uname = normalize_username(text)
            cursor.execute("SELECT user_id FROM users WHERE lower(username)=?", (uname,))
            row = cursor.fetchone()
            if not row:
                await msg.reply_text("⚠️ کاربر پیدا نشد.", reply_markup=admin_menu())
                return
            tid = row[0]
            cursor.execute("DELETE FROM raffle WHERE user_id=?", (tid,))
            cursor.execute("UPDATE users SET points=0, chances=0, is_registered=0 WHERE user_id=?", (tid,))
            conn.commit()
            await msg.reply_text(f"✅ کاربر {text} از قرعه‌کشی بن شد و امتیازاتش پاک شد.", reply_markup=admin_menu())
            return

        # ➕ امتیاز به همه
        if text == "➕ امتیاز به همه":
            context.user_data["add_all_waiting"] = True
            await msg.reply_text("🔢 لطفاً عدد امتیاز را وارد کنید تا به همه اضافه شود.", reply_markup=admin_menu())
            return
        if context.user_data.get("add_all_waiting"):
            context.user_data.pop("add_all_waiting", None)
            try:
                amt = int(text)
                cursor.execute("UPDATE users SET points = points + ?", (amt,))
                conn.commit()
                await msg.reply_text(f"✅ به همه کاربران {amt} امتیاز اضافه شد.", reply_markup=admin_menu())
            except:
                await msg.reply_text("⚠️ مقدار نامعتبر است. یک عدد صحیح وارد کنید.", reply_markup=admin_menu())
            return

        # ➕ امتیاز به کاربر
        if text == "➕ امتیاز به کاربر":
            context.user_data["add_one_wait_user"] = True
            await msg.reply_text("🔒 لطفاً یوزرنیم کاربر را با @ ارسال کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("add_one_wait_user"):
            context.user_data.pop("add_one_wait_user", None)
            if not text.startswith("@"):
                await msg.reply_text("⚠️ یوزرنیم باید با @ شروع شود.", reply_markup=admin_menu())
                return
            context.user_data["add_one_username"] = normalize_username(text)
            context.user_data["add_one_wait_amount"] = True
            await msg.reply_text("🔢 حالا عدد امتیاز را وارد کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("add_one_wait_amount"):
            context.user_data.pop("add_one_wait_amount", None)
            uname = context.user_data.pop("add_one_username", None)
            try:
                amt = int(text)
                cursor.execute("SELECT user_id FROM users WHERE lower(username)=?", (uname,))
                row = cursor.fetchone()
                if not row:
                    await msg.reply_text("⚠️ کاربر یافت نشد.", reply_markup=admin_menu())
                    return
                tid = row[0]
                cursor.execute("UPDATE users SET points = points + ? WHERE user_id=?", (amt, tid))
                conn.commit()
                await msg.reply_text(f"✅ {amt} امتیاز به @{uname} اضافه شد.", reply_markup=admin_menu())
            except:
                await msg.reply_text("⚠️ مقدار نامعتبر است.", reply_markup=admin_menu())
            return

        # ➖ کسر امتیاز از کاربر
        if text == "➖ کسر امتیاز از کاربر":
            context.user_data["sub_one_wait_user"] = True
            await msg.reply_text("🔒 لطفاً یوزرنیم کاربر را با @ ارسال کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("sub_one_wait_user"):
            context.user_data.pop("sub_one_wait_user", None)
            if not text.startswith("@"):
                await msg.reply_text("⚠️ یوزرنیم باید با @ شروع شود.", reply_markup=admin_menu())
                return
            context.user_data["sub_one_username"] = normalize_username(text)
            context.user_data["sub_one_wait_amount"] = True
            await msg.reply_text("🔢 حالا عدد امتیاز برای کسر را وارد کنید.", reply_markup=admin_menu())
            return
        if context.user_data.get("sub_one_wait_amount"):
            context.user_data.pop("sub_one_wait_amount", None)
            uname = context.user_data.pop("sub_one_username", None)
            try:
                amt = int(text)
                cursor.execute("SELECT user_id, points FROM users WHERE lower(username)=?", (uname,))
                row = cursor.fetchone()
                if not row:
                    await msg.reply_text("⚠️ کاربر یافت نشد.", reply_markup=admin_menu())
                    return
                tid, cur_points = row[0], row[1] or 0
                new_points = max(0, cur_points - amt)
                cursor.execute("UPDATE users SET points = ? WHERE user_id=?", (new_points, tid))
                conn.commit()
                await msg.reply_text(f"✅ {amt} امتیاز از @{uname} کسر شد. امتیاز جدید: {new_points}", reply_markup=admin_menu())
            except:
                await msg.reply_text("⚠️ مقدار نامعتبر است.", reply_markup=admin_menu())
            return

        # هر دستور دیگری: نمایش منو دوباره
        await msg.reply_text("🔧 لطفاً یکی از گزینه‌های منو را انتخاب کنید.", reply_markup=admin_menu())
        return

    # ---------- اگر کاربر عادی ----------
    # اول چک عضویت؛ اگر عضو نبود فقط دکمه‌های عضویت نمایش داده می‌شود و هیچ عملیات دیگری انجام نمی‌شود
    if not await is_member(uid, context):
        channels = await get_required_channels()
        if channels:
            buttons = [[InlineKeyboardButton(f"عضویت در {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in channels]
            await msg.reply_text("🔒 برای استفاده از ربات باید در کانال(های) زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await msg.reply_text("🔒 برای استفاده از این بخش باید شرایط عضویت برقرار باشد (کانالی تنظیم نشده).")
        return

if text == "🎰 ثبت نام در قرعه کشی":
        row = cursor.execute("SELECT is_registered FROM users WHERE user_id=?", (uid,)).fetchone()
        already = row and row[0]
        if already:
            await msg.reply_text("✅ شما قبلاً در قرعه‌کشی ثبت‌نام کرده‌اید.", reply_markup=main_menu())
            return
        # ثبت و یک شانس اضافه کن (تا سقف MAX_CHANCES)
        cursor.execute("SELECT chances FROM users WHERE user_id=?", (uid,))
        row = cursor.fetchone()
        cur_chances = row[0] if row else 0
        if cur_chances < MAX_CHANCES:
            add = 1
            new_chances = min(MAX_CHANCES, cur_chances + add)
            added = new_chances - cur_chances
            cursor.execute("UPDATE users SET is_registered=1, chances=chances+? WHERE user_id=?", (added, uid))
            insert_raffle_entries(uid, added)
            conn.commit()
            await msg.reply_text("🎉 شما با موفقیت در قرعه‌کشی ثبت‌نام شدید!", reply_markup=main_menu())
        else:
            await msg.reply_text(f"⚠️ شما قبلاً به حداکثرِ {MAX_CHANCES} شانس رسیده‌اید.", reply_markup=main_menu())
        return

    # افزایش امتیاز (لینک رفرال)
    if text == "💎 افزایش امتیاز":
        link = f"https://t.me/{(await context.bot.get_me()).username}?start={uid}"
        await msg.reply_text(f"🔗 لینک دعوت شما:\n{link}\n\nتذکر: امتیاز فقط وقتی به معرف تعلق می‌گیرد که شما برای اولین بار استارت بزنید.", reply_markup=main_menu())
        return

    # تبدیل امتیاز به شانس
    if text == "💳 تبدیل امتیاز به شانس":
        cursor.execute("SELECT points, chances FROM users WHERE user_id=?", (uid,))
        row = cursor.fetchone()
        pts = (row[0] or 0) if row else 0
        cur_chances = (row[1] or 0) if row else 0
        if pts <= 0:
            await msg.reply_text("⚠️ شما امتیازی برای تبدیل ندارید.", reply_markup=main_menu())
            return
        allowed = MAX_CHANCES - cur_chances
        to_convert = min(pts, allowed)
        if to_convert <= 0:
            await msg.reply_text(f"⚠️ شما به سقف {MAX_CHANCES} شانس رسیده‌اید؛ امکان تبدیل وجود ندارد.", reply_markup=main_menu())
            return
        cursor.execute("UPDATE users SET points = points - ?, chances = chances + ? WHERE user_id=?", (to_convert, to_convert, uid))
        insert_raffle_entries(uid, to_convert)
        conn.commit()
        await msg.reply_text(f"✅ تعداد {to_convert} امتیاز شما به شانس تبدیل شد.", reply_markup=main_menu())
        return

    # اطلاعات حساب
    if text == "👤 اطلاعات حساب":
        row = cursor.execute("SELECT username, points, chances, is_registered FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row:
            await msg.reply_text("⚠️ حساب شما پیدا نشد. لطفاً /start را بزنید.", reply_markup=main_menu())
            return
        uname_db, points, chances, reg = row
        reg_status = "✅ ثبت‌نام شده" if reg else "❌ ثبت‌نام نشده"
        await msg.reply_text(f"👤 @{uname_db}\n💎 امتیاز: {points}\n🎟️ شانس: {chances}\nوضعیت: {reg_status}", reply_markup=main_menu())
        return

    # اگر پیام متن دیگری بود، فقط منو نشان بده
    await msg.reply_text("🔧 لطفاً از دکمه‌های منو استفاده کنید.", reply_markup=main_menu())
    return

# -------------------- راه‌اندازی اپ --------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
