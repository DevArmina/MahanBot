from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, CallbackContext, ConversationHandler,
    MessageHandler, filters, CallbackQueryHandler
)
from datetime import datetime, timedelta
import re

# توکن ربات و رمز عبور ادمین
TOKEN = ""
ADMIN_PASSWORD = "#5214255#"

# حالت‌های مکالمه
# اضافه شدن حالت جدید VOTE_GENDER_SELECTION برای انتخاب گروه در رأی‌دهی
# همچنین دو حالت جدید برای نمایش قوانین و درباره ما داریم که در MAIN_MENU مدیریت می‌شوند.
RULES_ACCEPTANCE, MAIN_MENU, ADMIN_PASSWORD_STATE, ADMIN_MENU, ADD_MALE, ADD_FEMALE, REMOVE_MALE, REMOVE_FEMALE, VOTE_GENDER_SELECTION, VOTE_SELECTION = range(10)

# دیکشنری‌های شرکت‌کنندگان
participants_male = {}
participants_female = {}

admin_failures = {}
results_announced = False  # رای‌گیری فعال تا پایان آن
PER_PAGE = 10             # تعداد شرکت‌کننده در هر صفحه بخش رأی‌دهی
SCOREBOARD_PER_PAGE = 10  # تعداد رکورد در هر صفحه تابلو امتیاز

def get_scoreboard_list(participants_dict: dict) -> list:
    """لیست امتیازات از یک دیکشنری شرکت‌کننده."""
    lst = []
    for name, votes in participants_dict.items():
        score = votes["positive"] - votes["negative"]
        lst.append((name, votes["positive"], votes["negative"], score))
    lst.sort(key=lambda x: x[3], reverse=True)
    return lst

def get_full_scoreboard_list() -> list:
    """ترکیب امتیازات شرکت‌کننده‌های آقا و خانم و مرتب‌سازی نهایی."""
    lst = get_scoreboard_list(participants_male) + get_scoreboard_list(participants_female)
    lst.sort(key=lambda x: x[3], reverse=True)
    return lst

def build_scoreboard_page(page: int, items: list) -> (str, InlineKeyboardMarkup):
    """ساخت صفحه‌ای از تابلو امتیاز با ناوبری."""
    total = len(items)
    start_index = page * SCOREBOARD_PER_PAGE
    end_index = start_index + SCOREBOARD_PER_PAGE
    page_items = items[start_index:end_index]
    text = "🏆 *تابلو امتیاز* 🏆\n\n"
    for idx, (name, pos, neg, score) in enumerate(page_items, start=start_index+1):
        text += f"{idx}. *{name}*\n   👍: {pos}   👎: {neg}   امتیاز: {score}\n\n"
    kb = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("صفحه قبل", callback_data="sb_prev_page"))
    if end_index < total:
        nav.append(InlineKeyboardButton("صفحه بعد", callback_data="sb_next_page"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("بازگشت به منو", callback_data="back_main")])
    return text, InlineKeyboardMarkup(kb)

async def show_scoreboard_page(update: Update, context: CallbackContext, scoreboard: list, page: int) -> None:
    """نمایش یک صفحه از تابلو امتیاز."""
    text, reply_markup = build_scoreboard_page(page, scoreboard)
    if hasattr(update, "callback_query"):
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

def build_vote_keyboard(context: CallbackContext, vote_gender: str) -> InlineKeyboardMarkup:
    """ساخت کیبورد رأی‌دهی با صفحه‌بندی برای جنسیت مشخص."""
    participants = participants_male if vote_gender == "male" else participants_female
    votes = context.user_data.get("votes", {})
    current_page = context.user_data.get("current_page", 0)
    all_names = list(participants.keys())
    total = len(all_names)
    start_index = current_page * PER_PAGE
    end_index = start_index + PER_PAGE
    page_names = all_names[start_index:end_index]
    keyboard = []
    for name in page_names:
        vote = votes.get(name)
        pos_text = "👍" + ("✓" if vote == "vote_positive" else "")
        neg_text = "👎" + ("✓" if vote == "vote_negative" else "")
        keyboard.append([InlineKeyboardButton(f"{name} ({'آقا' if vote_gender=='male' else 'خانم'})", callback_data="noop")])
        keyboard.append([
            InlineKeyboardButton(pos_text, callback_data=f"vote_positive:{name}"),
            InlineKeyboardButton(neg_text, callback_data=f"vote_negative:{name}")
        ])
    nav_buttons = []
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("صفحه قبل", callback_data="prev_page"))
    if end_index < total:
        nav_buttons.append(InlineKeyboardButton("صفحه بعد", callback_data="next_page"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    # دکمه ثبت رأی به همراه دکمه بازگشت به منو
    keyboard.append([
        InlineKeyboardButton("📩 ثبت نهایی رأی‌ها", callback_data="final_vote"),
        InlineKeyboardButton("بازگشت به منو", callback_data="back_main")
    ])
    return InlineKeyboardMarkup(keyboard)

async def show_vote_list(update: Update, context: CallbackContext) -> None:
    """نمایش لیست رأی‌دهی برای گروه انتخاب‌شده؛ در صورت خالی بودن، به منوی اصلی بازگردد."""
    vote_gender = context.user_data.get("vote_gender")
    participants = participants_male if vote_gender == "male" else participants_female
    if not participants:
        if hasattr(update, "callback_query"):
            await update.callback_query.edit_message_text("هیچ شرکت‌کننده‌ای در این گروه وجود ندارد.")
        await send_main_menu(update, context)
        return
    keyboard = build_vote_keyboard(context, vote_gender)
    if hasattr(update, "callback_query"):
        await update.callback_query.edit_message_text("لطفاً برای هر شرکت‌کننده رأی خود را انتخاب کنید:", reply_markup=keyboard)
    else:
        await update.message.reply_text("لطفاً برای هر شرکت‌کننده رأی خود را انتخاب کنید:", reply_markup=keyboard)

async def send_main_menu(update_or_query, context: CallbackContext) -> None:
    """ارسال منوی اصلی به کاربر."""
    kb = [
        [InlineKeyboardButton("ورود به رای‌گیری", callback_data="vote_entry")],
        [InlineKeyboardButton("ورود داوران (ادمین)", callback_data="admin_entry")],
        [InlineKeyboardButton("تابلو امتیاز کلی", callback_data="scoreboard_view")],
        [InlineKeyboardButton("اعلان نتایج آقایان", callback_data="announce_results_male")],
        [InlineKeyboardButton("اعلان نتایج خانم", callback_data="announce_results_female")],
        [InlineKeyboardButton("قوانین", callback_data="rules_info"), InlineKeyboardButton("درباره ما", callback_data="about_info")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    if hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text("لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=reply_markup)
    else:
        await update_or_query.message.reply_text("لطفاً یکی از گزینه‌ها را انتخاب کنید:", reply_markup=reply_markup)

async def start(update: Update, context: CallbackContext) -> int:
    """پیام خوش‌آمدگویی و درخواست پذیرش قوانین با دکمه‌های مربوطه."""
    text = (
        "سلام به ربات آموزشگاه بازیگری ماهان خوش اومدی! 🎭\n"
        "ما اینجاییم که در کنارت باشیم و کمکت کنیم.\n"
        "در حال حاضر در حال برگذاری یک مسابقه هستیم.\n\n"
        "لطفاً قوانین زیر رو مطالعه کن و بهشون عمل کن:\n"
        "1️⃣ هر شرکت‌کننده فقط یک بار می‌تونه رای بده. در صورت رای دوباره، ایدی شما ثبت و به عنوان متقلب شناخته می‌شه.\n"
        "2️⃣ پس از ثبت رای، فرصت مجدد نیست.\n"
        "3️⃣ تنها دانشجویان ماهان قادر به رای دادن هستند.\n\n"
        "👇 برای ادامه روی دکمه «قبول می‌کنم» کلیک کن."
    )
    kb = [
        [InlineKeyboardButton("قبول می‌کنم", callback_data="accept_rules")],
        [InlineKeyboardButton("قوانین", callback_data="rules_info"), InlineKeyboardButton("درباره ما", callback_data="about_info")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return RULES_ACCEPTANCE

async def rules_accept_callback(update: Update, context: CallbackContext) -> int:
    """پس از کلیک روی «قبول می‌کنم»، منوی اصلی نمایش داده می‌شود."""
    query = update.callback_query
    await query.answer()
    await send_main_menu(query, context)
    return MAIN_MENU

async def rules_info_callback(update: Update, context: CallbackContext) -> int:
    """نمایش متن قوانین به کاربر به همراه دکمه بازگشت."""
    query = update.callback_query
    await query.answer()
    rules_text = (
        "📜 *قوانین مسابقه:*\n\n"
        "1️⃣ هر شرکت‌کننده فقط یک بار می‌تونه رای بده. در صورت رای دوباره، ایدی شما ثبت و به عنوان متقلب شناخته می‌شه.\n"
        "2️⃣ پس از ثبت رای، فرصت مجدد نیست.\n"
        "3️⃣ تنها دانشجویان ماهان قادر به رای دادن هستند.\n"
    )
    kb = [[InlineKeyboardButton("بازگشت به منو", callback_data="back_main")]]
    await query.message.edit_text(rules_text, reply_markup=InlineKeyboardMarkup(kb))
    return MAIN_MENU

async def about_info_callback(update: Update, context: CallbackContext) -> int:
    """نمایش اطلاعات درباره ربات."""
    query = update.callback_query
    await query.answer()
    about_text = "🤖 این ربات توسط آموزشگاه بازیگری ماهان توسعه یافته است. جهت اطلاعات بیشتر با ما در تماس باشید."
    kb = [[InlineKeyboardButton("بازگشت به منو", callback_data="back_main")]]
    await query.message.edit_text(about_text, reply_markup=InlineKeyboardMarkup(kb))
    return MAIN_MENU

async def main_menu_callback(update: Update, context: CallbackContext) -> int:
    """پردازش گزینه‌های منوی اصلی."""
    global results_announced
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "admin_entry":
        await query.message.reply_text("لطفاً رمز عبور ادمین را وارد کنید:")
        return ADMIN_PASSWORD_STATE

    elif data == "vote_entry":
        kb = [
            [InlineKeyboardButton("رای گیری آقایان", callback_data="vote_male"),
             InlineKeyboardButton("رای گیری خانم", callback_data="vote_female")],
            [InlineKeyboardButton("بازگشت به منو", callback_data="back_main")]
        ]
        await query.message.edit_text("لطفاً گروه مورد نظر برای رأی‌دهی را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(kb))
        return VOTE_GENDER_SELECTION

    elif data == "scoreboard_view":
        scoreboard = get_full_scoreboard_list()
        context.user_data["scoreboard_page"] = 0
        if not scoreboard:
            await query.message.edit_message_text("هیچ داده‌ای برای نمایش وجود ندارد.")
            await send_main_menu(query, context)
            return MAIN_MENU
        await show_scoreboard_page(update, context, scoreboard, 0)
        return MAIN_MENU

    elif data == "announce_results_male":
        if not results_announced:
            await query.message.edit_message_text("⚠️ اعلان نتایج هنوز فعال نشده است.")
            await send_main_menu(query, context)
        else:
            lst = get_scoreboard_list(participants_male)[:10]
            text = "🏆 *اعلان نتایج آقایان (10 نفر اول)* 🏆\n\n"
            for idx, (name, pos, neg, score) in enumerate(lst, start=1):
                text += f"{idx}. *{name}*\n   👍: {pos}   👎: {neg}   امتیاز: {score}\n\n"
            await query.message.edit_message_text(text)
        return MAIN_MENU

    elif data == "announce_results_female":
        if not results_announced:
            await query.message.edit_message_text("⚠️ اعلان نتایج هنوز فعال نشده است.")
            await send_main_menu(query, context)
        else:
            lst = get_scoreboard_list(participants_female)[:10]
            text = "🏆 *اعلان نتایج خانم (10 نفر اول)* 🏆\n\n"
            for idx, (name, pos, neg, score) in enumerate(lst, start=1):
                text += f"{idx}. *{name}*\n   👍: {pos}   👎: {neg}   امتیاز: {score}\n\n"
            await query.message.edit_message_text(text)
        return MAIN_MENU

    elif data == "rules_info":
        return await rules_info_callback(update, context)

    elif data == "about_info":
        return await about_info_callback(update, context)

    elif data == "back_main":
        await send_main_menu(query, context)
        return MAIN_MENU

async def vote_gender_selection_callback(update: Update, context: CallbackContext) -> int:
    """پردازش انتخاب جنسیت برای رأی‌دهی."""
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "vote_male":
        context.user_data["vote_gender"] = "male"
    elif data == "vote_female":
        context.user_data["vote_gender"] = "female"
    context.user_data["current_page"] = 0
    await show_vote_list(update, context)
    return VOTE_SELECTION

async def vote_callback(update: Update, context: CallbackContext) -> int:
    """پردازش رویدادهای مربوط به رأی‌دهی."""
    query = update.callback_query
    await query.answer()
    data = query.data
    vote_gender = context.user_data.get("vote_gender")

    if data == "noop":
        return VOTE_SELECTION

    if data == "next_page":
        context.user_data["current_page"] = context.user_data.get("current_page", 0) + 1
        await show_vote_list(update, context)
        return VOTE_SELECTION

    if data == "prev_page":
        context.user_data["current_page"] = max(context.user_data.get("current_page", 0) - 1, 0)
        await show_vote_list(update, context)
        return VOTE_SELECTION

    if data.startswith("vote_positive:") or data.startswith("vote_negative:"):
        try:
            vote_type, name = data.split(":", 1)
        except ValueError:
            await query.message.reply_text("داده نامعتبر دریافت شد.")
            return VOTE_SELECTION
        participants = participants_male if vote_gender == "male" else participants_female
        if name not in participants:
            await query.message.reply_text("این شرکت‌کننده وجود ندارد.")
            return VOTE_SELECTION
        context.user_data.setdefault("votes", {})[name] = vote_type
        await show_vote_list(update, context)
        return VOTE_SELECTION

    if data == "final_vote":
        votes = context.user_data.get("votes", {})
        if not votes:
            await query.message.edit_message_text("هیچ رأی‌ای ثبت نشده است.")
            await send_main_menu(query, context)
            return MAIN_MENU
        participants = participants_male if vote_gender == "male" else participants_female
        for name, vote_type in votes.items():
            if name in participants:
                if vote_type == "vote_positive":
                    participants[name]["positive"] += 1
                elif vote_type == "vote_negative":
                    participants[name]["negative"] += 1
        text = get_full_scoreboard_text()
        await query.message.edit_message_text(f"✅ رأی‌ها ثبت شدند.\n\n{text}")
        context.user_data.pop("votes", None)
        return ConversationHandler.END

    if data in ("sb_next_page", "sb_prev_page", "back_main"):
        sb_page = context.user_data.get("scoreboard_page", 0)
        scoreboard = get_full_scoreboard_list()
        if data == "sb_next_page":
            sb_page += 1
        elif data == "sb_prev_page":
            sb_page = max(sb_page - 1, 0)
        context.user_data["scoreboard_page"] = sb_page
        await show_scoreboard_page(update, context, scoreboard, sb_page)
        return MAIN_MENU

    return VOTE_SELECTION

def get_full_scoreboard_text() -> str:
    lst = get_full_scoreboard_list()
    text = "🏆 *تابلو امتیاز کلی* 🏆\n\n"
    for idx, (name, pos, neg, score) in enumerate(lst, start=1):
        text += f"{idx}. *{name}*\n   👍: {pos}   👎: {neg}   امتیاز: {score}\n\n"
    return text

async def admin_password(update: Update, context: CallbackContext) -> int:
    """ورود به پنل ادمین با بررسی رمز عبور."""
    chat_id = update.message.chat_id
    now = datetime.now()
    if chat_id in admin_failures:
        lock_until = admin_failures[chat_id].get("lock_until")
        if lock_until and now < lock_until:
            remaining = (lock_until - now).seconds // 60
            await update.message.reply_text(f"به دلیل ورودهای ناموفق، شما برای {remaining} دقیقه قفل شده‌اید.")
            return ConversationHandler.END
    text = update.message.text.strip()
    if text == ADMIN_PASSWORD:
        admin_failures.pop(chat_id, None)
        kb = [
            [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
             InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
            [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
             InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
            [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
            [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
            [InlineKeyboardButton("خروج", callback_data="admin_exit")]
        ]
        reply_markup = InlineKeyboardMarkup(kb)
        await update.message.reply_text("ورود ادمین با موفقیت انجام شد. منوی ادمین:", reply_markup=reply_markup)
        return ADMIN_MENU
    else:
        failures = admin_failures.get(chat_id, {"fail_count": 0, "lock_until": None})
        failures["fail_count"] += 1
        if failures["fail_count"] >= 2:
            failures["lock_until"] = now + timedelta(minutes=30)
            await update.message.reply_text("رمز عبور نادرست. شما به مدت 30 دقیقه قفل شدید.")
            admin_failures[chat_id] = failures
            return ConversationHandler.END
        else:
            admin_failures[chat_id] = failures
            await update.message.reply_text("رمز عبور نادرست. لطفاً مجدداً وارد کنید:")
            return ADMIN_PASSWORD_STATE

async def admin_menu_callback(update: Update, context: CallbackContext) -> int:
    """پردازش گزینه‌های پنل ادمین."""
    global results_announced
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_male":
        await query.message.reply_text("❌ لطفاً لیست شرکت‌کننده‌های مرد را به صورت زیر وارد کنید (حداکثر 20 نفر):\nمثال:\n1- آرمان فرجزاده\n2- امیرحسین خواجوی")
        return ADD_MALE
    elif data == "add_female":
        await query.message.reply_text("❌ لطفاً لیست شرکت‌کننده‌های زن را به صورت زیر وارد کنید (حداکثر 20 نفر):\nمثال:\n1- سپیده پلنگی\n2- الناز عسکری")
        return ADD_FEMALE
    elif data == "remove_male":
        await query.message.reply_text("لطفاً نام شرکت‌کننده‌ی مردی که می‌خواهید حذف کنید را وارد کنید:")
        return REMOVE_MALE
    elif data == "remove_female":
        await query.message.reply_text("لطفاً نام شرکت‌کننده‌ی زنی که می‌خواهید حذف کنید را وارد کنید:")
        return REMOVE_FEMALE
    elif data == "view_scoreboard":
        scoreboard = get_full_scoreboard_list()
        context.user_data["scoreboard_page"] = 0
        if not scoreboard:
            await query.message.reply_text("هیچ داده‌ای برای نمایش وجود ندارد.")
            await send_main_menu(query, context)
            return ADMIN_MENU
        await show_scoreboard_page(update, context, scoreboard, 0)
        return ADMIN_MENU
    elif data == "end_voting":
        results_announced = True
        await query.message.reply_text("✅ پایان رای گیری انجام شد. اعلان نتایج فعال شد.")
        kb = [
            [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
             InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
            [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
             InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
            [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
            [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
            [InlineKeyboardButton("خروج", callback_data="admin_exit")]
        ]
        reply_markup = InlineKeyboardMarkup(kb)
        await query.message.reply_text("منوی ادمین:", reply_markup=reply_markup)
        return ADMIN_MENU
    elif data == "admin_exit":
        await send_main_menu(query, context)
        return MAIN_MENU

async def add_male(update: Update, context: CallbackContext) -> int:
    text_input = update.message.text.strip()
    added, skipped, names = [], [], []
    if re.search(r'\d+\s*-\s*', text_input):
        names = re.findall(r'\d+\s*-\s*(.+)', text_input)
    else:
        names = re.split(r'[,\n]+', text_input)
    names = [n.strip() for n in names if n.strip()]
    for name in names:
        if name in participants_male:
            skipped.append(name)
        else:
            participants_male[name] = {"positive": 0, "negative": 0}
            added.append(name)
    msg = ""
    if added:
        msg += f"✅ شرکت‌کننده‌های مرد زیر اضافه شدند:\n{', '.join(added)}\n"
    if skipped:
        msg += f"⚠️ این شرکت‌کننده‌های مرد قبلاً وجود داشتند:\n{', '.join(skipped)}"
    if not msg:
        msg = "هیچ نام معتبر وارد نشد."
    kb = [
        [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
         InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
        [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
         InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
        [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
        [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
        [InlineKeyboardButton("خروج", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(msg)
    await update.message.reply_text("منوی ادمین:", reply_markup=reply_markup)
    return ADMIN_MENU

async def add_female(update: Update, context: CallbackContext) -> int:
    text_input = update.message.text.strip()
    added, skipped, names = [], [], []
    if re.search(r'\d+\s*-\s*', text_input):
        names = re.findall(r'\d+\s*-\s*(.+)', text_input)
    else:
        names = re.split(r'[,\n]+', text_input)
    names = [n.strip() for n in names if n.strip()]
    for name in names:
        if name in participants_female:
            skipped.append(name)
        else:
            participants_female[name] = {"positive": 0, "negative": 0}
            added.append(name)
    msg = ""
    if added:
        msg += f"✅ شرکت‌کننده‌های زن زیر اضافه شدند:\n{', '.join(added)}\n"
    if skipped:
        msg += f"⚠️ این شرکت‌کننده‌های زن قبلاً وجود داشتند:\n{', '.join(skipped)}"
    if not msg:
        msg = "هیچ نام معتبر وارد نشد."
    kb = [
        [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
         InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
        [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
         InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
        [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
        [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
        [InlineKeyboardButton("خروج", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text(msg)
    await update.message.reply_text("منوی ادمین:", reply_markup=reply_markup)
    return ADMIN_MENU

async def remove_male(update: Update, context: CallbackContext) -> int:
    name = update.message.text.strip()
    if name in participants_male:
        del participants_male[name]
        await update.message.reply_text(f"❌ شرکت‌کننده مرد '{name}' حذف شد.")
    else:
        await update.message.reply_text("⚠️ این شرکت‌کننده‌ی مرد وجود ندارد.")
    kb = [
        [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
         InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
        [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
         InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
        [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
        [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
        [InlineKeyboardButton("خروج", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text("منوی ادمین:", reply_markup=reply_markup)
    return ADMIN_MENU

async def remove_female(update: Update, context: CallbackContext) -> int:
    name = update.message.text.strip()
    if name in participants_female:
        del participants_female[name]
        await update.message.reply_text(f"❌ شرکت‌کننده زن '{name}' حذف شد.")
    else:
        await update.message.reply_text("⚠️ این شرکت‌کننده‌ی زن وجود ندارد.")
    kb = [
        [InlineKeyboardButton("افزودن شرکت‌کننده (مرد)", callback_data="add_male"),
         InlineKeyboardButton("افزودن شرکت‌کننده (زن)", callback_data="add_female")],
        [InlineKeyboardButton("حذف شرکت‌کننده (مرد)", callback_data="remove_male"),
         InlineKeyboardButton("حذف شرکت‌کننده (زن)", callback_data="remove_female")],
        [InlineKeyboardButton("مشاهده تابلو امتیاز کلی", callback_data="view_scoreboard")],
        [InlineKeyboardButton("پایان رای گیری", callback_data="end_voting")],
        [InlineKeyboardButton("خروج", callback_data="admin_exit")]
    ]
    reply_markup = InlineKeyboardMarkup(kb)
    await update.message.reply_text("منوی ادمین:", reply_markup=reply_markup)
    return ADMIN_MENU

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("عملیات لغو شد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    app = Application.builder().token(TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            RULES_ACCEPTANCE: [CallbackQueryHandler(rules_accept_callback, pattern="^accept_rules$"),
                               CallbackQueryHandler(rules_info_callback, pattern="^rules_info$"),
                               CallbackQueryHandler(about_info_callback, pattern="^about_info$")],
            MAIN_MENU: [CallbackQueryHandler(
                main_menu_callback, 
                pattern="^(admin_entry|vote_entry|scoreboard_view|announce_results_male|announce_results_female|rules_info|about_info|back_main)$"
            )],
            ADMIN_PASSWORD_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_password)],
            ADMIN_MENU: [CallbackQueryHandler(
                admin_menu_callback, 
                pattern="^(add_male|add_female|remove_male|remove_female|view_scoreboard|admin_exit|end_voting)$"
            )],
            ADD_MALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_male)],
            ADD_FEMALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_female)],
            REMOVE_MALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_male)],
            REMOVE_FEMALE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_female)],
            VOTE_GENDER_SELECTION: [CallbackQueryHandler(vote_gender_selection_callback, pattern="^(vote_male|vote_female)$")],
            VOTE_SELECTION: [CallbackQueryHandler(
                vote_callback, 
                pattern="^(noop|next_page|prev_page|vote_positive:.*|vote_negative:.*|final_vote|sb_next_page|sb_prev_page|back_main)$"
            )]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
