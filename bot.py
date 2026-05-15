#  bot.py  —  SiraHub Telegram Bot (Freemium + Referrals)
# ─────────────────────────────────────────────
import asyncio
import logging
import json
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import (
    BOT_TOKEN,
    BOT_USERNAME,
    DAILY_JOB_LIMIT,
    REFERRALS_FOR_PREMIUM,
    NOTIFY_INTERVAL_MINUTES,
)
from db import (
    init_db,
    get_stats,
    create_user,
    get_user,
    update_user_profile,
    set_user_onboarded,
    set_active,
    get_referral_code,
    record_referral,
    get_new_jobs_for_user,
    search_jobs_for_user,
    mark_job_sent,
    increment_jobs_sent,
    can_receive_job,
    remaining_today,
    CATEGORY_KEYWORDS,
)

# Logging
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────
NAME, CONFIRM_NAME, SITUATION, LOCATION, WORK_KIND, AGE, GENDER, EDUCATION = range(8)

# ── Helpers ───────────────────────────────────

def _fmt(job: dict) -> str:
    """Format a job dict into a Telegram Markdown message following the user's custom layout."""
    title = job.get("title", "N/A")
    job_type = job.get("experience", "N/A") # Scraper stores type in experience for TG
    location = job.get("location", "N/A")
    deadline = job.get("deadline", "N/A")
    description = job.get("description", "").strip()
    
    # Attempt to extract Salary/Compensation if it's embedded in the description
    salary = "N/A"
    salary_keys = ["Salary/Compensation:", "Salary:"]
    for key in salary_keys:
        if key in description:
            try:
                parts = description.split(key, 1)
                salary = parts[1].split("\n", 1)[0].strip()
                # Optionally remove it from desc to avoid redundancy
                rem_desc = parts[1].split("\n", 1)[1] if "\n" in parts[1] else ""
                description = (parts[0].strip() + "\n" + rem_desc.strip()).strip()
                break
            except:
                pass

    # Limit description for the preview
    if len(description) > 600:
        description = description[:597] + "..."

    # Build the message in the exact requested format
    msg = [
        f"*Job Title:* {title}",
        f"*Job Type:* {job_type}",
        "",
        f"*Work Location:* {location}",
        "",
        f"*Salary/Compensation:* {salary}",
        "",
        f"*Deadline:* {deadline}",
        "",
        f"*Description:* {description}",
        "",
        f"🔗 [View Full Job Post ➜]({job['url']})"
    ]
    
    return "\n".join(msg)

# ── Command Handlers ──────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Handle Referrals
    referrer_code = None
    if context.args:
        referrer_code = context.args[0]
        logger.info(f"User {chat_id} joined via referral code: {referrer_code}")

    create_user(chat_id, username, referred_by=referrer_code)
    
    # Check if referral needs crediting (only once per new user)
    if referrer_code:
        result = record_referral(referrer_code, chat_id)
        if result:
            ref_id, now_premium = result
            try:
                msg = "🎁 Someone joined using your link!"
                if now_premium:
                    msg += f"\n\n🚀 *Congratulations!* You've reached {REFERRALS_FOR_PREMIUM} referrals and unlocked *PREMIUM*!"
                await context.bot.send_message(chat_id=ref_id, text=msg, parse_mode="Markdown")
            except Exception:
                pass

    user = get_user(chat_id)
    if not user or not user.get("onboarded"):
        # We will reset their state if they use /start again
        await update.message.reply_text(
            "👋 *Selam! Welcome to Sirahub.*\n\n"
            "Finding a good job in today's market is not easy — we know that. That's why we built Sirahub: to bring the right opportunities to you, based on your skills and where you want to go.\n\n"
            "No endless searching. No wasted time. Just real jobs, matched to you.\n\n"
            "Let's find your next step together 🙂",
            parse_mode="Markdown"
        )
        await asyncio.sleep(2)
        await update.message.reply_text(
            "First, what’s your full name?\n"
            "Please enter it in this format:\n"
            "First Name Middle Name Last Name\n\n"
            "Example:\n"
            "Tomase Gemachu Hagose"
        )
        return NAME

    # Fully onboarded -> Show Profile
    jtypes = json.loads(user.get("job_types") or "[]")
    types_str = ", ".join(jtypes) if jtypes else "None"
    
    await update.message.reply_text(
        f"👋 Welcome back, *{user.get('full_name', username)}*!\n\n"
        f"👤 *Your Profile*\n"
        f"**Name:** {user.get('full_name', 'N/A')}\n"
        f"**Situation:** {user.get('situation', 'N/A')}\n"
        f"**Location:** {user.get('preferred_location', 'N/A')}\n"
        f"**Job Types:** {types_str}\n"
        f"**Age:** {user.get('age', 'N/A')}\n"
        f"**Gender:** {user.get('gender', 'N/A')}\n"
        f"**Education:** {user.get('education_level', 'N/A')}\n\n"
        "🚀 I'm monitoring new jobs for you. Use /latest to see current matches.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    context.user_data["name"] = name
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes", callback_data="name_yes"),
         InlineKeyboardButton("No", callback_data="name_no")]
    ])
    await update.message.reply_text(
        f"Is '{name}' correct?",
        reply_markup=keyboard
    )
    return CONFIRM_NAME

async def handle_confirm_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "name_no":
        await query.edit_message_text("Please re-enter your full name:")
        return NAME
    
    name = context.user_data.get("name", "")
    
    situations = [
        "Currently employed",
        "Looking for a new job",
        "Recently graduated",
        "Student",
        "Freelancer",
        "Unemployed"
    ]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(sit, callback_data=f"sit_{sit}")] for sit in situations
    ])
    
    await query.edit_message_text(
        f"Nice to meet you, {name} 👋\n"
        "Now, can you tell me your current situation?",
        reply_markup=keyboard
    )
    return SITUATION

async def handle_situation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    sit = query.data.replace("sit_", "")
    context.user_data["situation"] = sit
    
    await query.edit_message_text(
        "What’s your current location?\n"
        "Please enter it in this format:\n"
        "City, Country\n\n"
        "Examples:\n"
        "Addis Ababa, Ethiopia\n"
        "Dire Dawa, Ethiopia"
    )
    return LOCATION

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loc = update.message.text.strip()
    context.user_data["location"] = loc
    context.user_data["selected_types"] = []
    
    await update.message.reply_text(
        "Thanks 👍\n"
        "What kind of work are you looking for?\n"
        "You can choose one or more options below:",
        reply_markup=get_work_kind_keyboard([])
    )
    return WORK_KIND

def get_work_kind_keyboard(selected):
    types = ["Full-time", "Part-time", "Contract", "Freelance", "Internship"]
    buttons = []
    for t in types:
        prefix = "✅ " if t in selected else ""
        buttons.append([InlineKeyboardButton(f"{prefix}{t}", callback_data=f"wk_{t}")])
    buttons.append([InlineKeyboardButton("✨ DONE", callback_data="wk_done")])
    return InlineKeyboardMarkup(buttons)

async def handle_work_kind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    selected = context.user_data.get("selected_types", [])
    
    if data == "wk_done":
        if not selected:
            await query.answer("Please select at least one!", show_alert=True)
            return WORK_KIND
        
        age_ranges = ["15-20", "21-25", "26-30", "30+"]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(age, callback_data=f"age_{age}")] for age in age_ranges
        ])
        await query.edit_message_text(
            "Enter your age:",
            reply_markup=keyboard
        )
        return AGE

    wk = data.replace("wk_", "")
    if wk in selected:
        selected.remove(wk)
    else:
        selected.append(wk)
    
    context.user_data["selected_types"] = selected
    await query.edit_message_reply_markup(reply_markup=get_work_kind_keyboard(selected))
    return WORK_KIND

async def handle_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    age = query.data.replace("age_", "")
    context.user_data["age"] = age
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Male", callback_data="gen_male"),
         InlineKeyboardButton("Female", callback_data="gen_female")]
    ])
    await query.edit_message_text(
        "Enter your gender:",
        reply_markup=keyboard
    )
    return GENDER

async def handle_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    gender = query.data.replace("gen_", "")
    context.user_data["gender"] = gender
    
    edu_levels = ["12 diploma", "diploma", "bachlor dgree", "masters", "PHD"]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(edu, callback_data=f"edu_{edu}")] for edu in edu_levels
    ])
    await query.edit_message_text(
        "Enter your educational level:",
        reply_markup=keyboard
    )
    return EDUCATION

async def handle_education(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    edu = query.data.replace("edu_", "")
    
    chat_id = update.effective_chat.id
    name = context.user_data.get("name", "User")
    sit = context.user_data.get("situation", "")
    loc = context.user_data.get("location", "")
    w_kinds = context.user_data.get("selected_types", [])
    age = context.user_data.get("age", "")
    gender = context.user_data.get("gender", "")
    
    # Save to database
    update_user_profile(
        chat_id=chat_id,
        full_name=name,
        situation=sit,
        location=loc,
        job_types=w_kinds,
        age=age,
        gender=gender,
        education_level=edu
    )
    set_user_onboarded(chat_id)
    
    await query.edit_message_text("✅ done your profile is 100% done")
    
    user = get_user(chat_id)
    jobs = search_jobs_for_user(user, limit=3)
    
    if jobs:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Here are {len(jobs)} recent jobs that match your profile:"
        )
        for job in jobs:
            await context.bot.send_message(
                chat_id=chat_id,
                text=_fmt(job),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            await asyncio.sleep(0.3)
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="No matching jobs found right now, but I will alert you when they appear!"
        )
        
    return ConversationHandler.END

async def cmd_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_chat.id)
    if not user or not user.get("onboarded"):
        await update.message.reply_text("You haven't completed your profile yet. Please use /start to register.")
        return

    jtypes = json.loads(user.get("job_types") or "[]")
    types_str = ", ".join(jtypes) if jtypes else "None"
    
    await update.message.reply_text(
        f"👤 *Your Profile*\n"
        f"**Name:** {user.get('full_name', 'N/A')}\n"
        f"**Situation:** {user.get('situation', 'N/A')}\n"
        f"**Location:** {user.get('preferred_location', 'N/A')}\n"
        f"**Job Types:** {types_str}\n"
        f"**Age:** {user.get('age', 'N/A')}\n"
        f"**Gender:** {user.get('gender', 'N/A')}\n"
        f"**Education:** {user.get('education_level', 'N/A')}\n\n"
        "*(Note: Profile editing will be added soon!)*",
        parse_mode="Markdown"
    )

async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_chat.id)
    if not user: return
    
    jobs = search_jobs_for_user(user, limit=5)
    if not jobs:
        await update.message.reply_text("No matching jobs found yet. I'll alert you when they appear!")
        return
    
    await update.message.reply_text(f"📋 *Latest {len(jobs)} Matches:*", parse_mode="Markdown")
    for job in jobs:
        await update.message.reply_text(_fmt(job), parse_mode="Markdown", disable_web_page_preview=True)
        await asyncio.sleep(0.3)

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = get_stats()
    await update.message.reply_text(
        "📊 *SiraHub Statistics*\n\n"
        f"💼 Total Jobs in DB: {s['total_jobs']}\n"
        f"📅 Added today: {s['jobs_today']}\n"
        f"👥 Active Users: {s['active_subscribers']}\n"
        f"💎 Premium Users: {s['premium_users']}",
        parse_mode="Markdown"
    )

async def cmd_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    code = get_referral_code(chat_id)
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    
    user = get_user(chat_id)
    count = user.get("referral_count", 0)
    
    msg = (
        "🎁 *Referral Program*\n\n"
        f"Invite {REFERRALS_FOR_PREMIUM} friends to unlock *Premium Features*:\n"
        "✅ Unlimited daily job alerts\n"
        "✅ Real-time notifications\n\n"
        f"📈 Your Referrals: *{count}/{REFERRALS_FOR_PREMIUM}*\n\n"
        "Your unique link:\n"
        f"`{link}`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

# ── Push Notifications ────────────────────────

async def notification_job(context: ContextTypes.DEFAULT_TYPE):
    """Every 5 min: push jobs never-yet-sent to each user based on their categories."""
    logger.info("🔔 Running notification cycle...")
    from db import get_users_for_notification

    users = get_users_for_notification()
    for user in users:
        chat_id = user["chat_id"]

        # Check daily limit for non-premium
        remaining = remaining_today(chat_id)
        if not user["is_premium"] and remaining <= 0:
            continue

        limit = remaining if remaining is not None else 10
        new_jobs = get_new_jobs_for_user(user, limit=limit)

        if not new_jobs:
            continue

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 *Found {len(new_jobs)} new job matches for you!*",
                parse_mode="Markdown"
            )
            for job in new_jobs:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=_fmt(job),
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                # Mark this specific job as sent to this user
                mark_job_sent(job["id"], chat_id)
                increment_jobs_sent(chat_id)
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Failed to notify {chat_id}: {e}")

# ── Main ──────────────────────────────────────

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Onboarding Conversation
    onboard_conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
            CONFIRM_NAME: [CallbackQueryHandler(handle_confirm_name, pattern="^name_")],
            SITUATION: [CallbackQueryHandler(handle_situation, pattern="^sit_")],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_location)],
            WORK_KIND: [CallbackQueryHandler(handle_work_kind, pattern="^wk_")],
            AGE: [CallbackQueryHandler(handle_age, pattern="^age_")],
            GENDER: [CallbackQueryHandler(handle_gender, pattern="^gen_")],
            EDUCATION: [CallbackQueryHandler(handle_education, pattern="^edu_")],
        },
        fallbacks=[CommandHandler("start", cmd_start)],
        allow_reentry=True
    )

    app.add_handler(onboard_conv)
    app.add_handler(CommandHandler("profile", cmd_profile))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("invite", cmd_invite))

    # Schedule notifications every 5 minutes
    if app.job_queue:
        app.job_queue.run_repeating(
            notification_job,
            interval=5 * 60,   # 5 minutes
            first=10
        )

    logger.info("🤖 Bot is starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
