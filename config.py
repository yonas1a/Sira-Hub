# ─────────────────────────────────────────────
#  config.py  —  Edit these values before running
# ─────────────────────────────────────────────

# 1. Get your token from @BotFather on Telegram
BOT_TOKEN = "8266439966:AAFd9LYBDOIC4Oz_Pll_P2Z9nAvwBTtXhQU"
BOT_USERNAME = "skilyjob_bot" 

# 2. Scraping schedule
BASE_URL              = "https://www.hahu.jobs/jobs?min_yoe=0&max_yoe=100&page="
START_PAGE            = 1
END_PAGE              = 20
SCRAPE_INTERVAL_HOURS = 3
 
# ── Freemium ──────────────────────────────────
DAILY_JOB_LIMIT       = 10    # jobs/day for standard users
REFERRALS_FOR_PREMIUM = 5     # referrals needed to unlock Premium
 
# ── Database ──────────────────────────────────
DB_PATH = "jobs.db"
 
# ── Bot scheduler ────────────────────────────
NOTIFY_INTERVAL_MINUTES = 30