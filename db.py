# ─────────────────────────────────────────────
#  db.py  —  Shared database layer
#  Used by both bot.py and scraper.py
# ─────────────────────────────────────────────
import hashlib
import json
import sqlite3
import re
from datetime import date

from config import DB_PATH, DAILY_JOB_LIMIT, REFERRALS_FOR_PREMIUM

# ── Category → search keywords ────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "💻 Technology & IT":      ["tech", "it", "software", "developer", "data", "cyber",
                                 "network", "system", "programming", "devops", "cloud"],
    "📊 Marketing & Sales":    ["marketing", "sales", "brand", "digital", "social media",
                                 "seo", "content", "campaign", "advertising"],
    "💰 Finance & Accounting": ["finance", "accounting", "audit", "tax", "financial",
                                 "budget", "bookkeeping", "treasurer"],
    "⚙️ Engineering":          ["engineer", "mechanical", "electrical", "civil",
                                 "construction", "structural", "manufacturing"],
    "🏥 Healthcare":           ["health", "medical", "nurse", "doctor", "clinical",
                                 "pharmacy", "laboratory", "dental", "hospital"],
    "📚 Education & Training": ["education", "teacher", "trainer", "lecturer",
                                 "academic", "tutor", "curriculum", "instructor"],
    "🏢 Admin & HR":           ["admin", "hr", "human resource", "office", "secretary",
                                 "assistant", "coordinator", "receptionist", "clerk"],
    "🎨 Design & Creative":    ["design", "graphic", "ui", "ux", "art", "creative",
                                 "video", "photo", "illustrat", "animation"],
    "⚖️ Legal":                ["legal", "law", "compliance", "lawyer", "attorney",
                                 "contract", "paralegal", "litigation"],
    "🌍 Other":                [],   # wildcard — matches all jobs
}


# ── Connection helper ─────────────────────────

def regexp_func(expr, item):
    if item is None: return False
    reg = re.compile(expr, re.I)
    return reg.search(item) is not None

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.create_function("REGEXP", 2, regexp_func)
    return conn


# ── Schema ────────────────────────────────────

def init_db():
    """Create all tables if they don't exist yet."""
    with _conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT,
                company     TEXT,
                location    TEXT,
                experience  TEXT,
                description TEXT,
                deadline    TEXT,
                url         TEXT UNIQUE,
                source      TEXT DEFAULT 'web',
                scraped_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS users (
                chat_id            INTEGER PRIMARY KEY,
                username           TEXT,
                first_name         TEXT,
                phone              TEXT,
                age                TEXT,
                job_categories     TEXT    DEFAULT "[]",
                experience_level   TEXT,
                job_types          TEXT    DEFAULT "[]",
                preferred_location TEXT,
                is_premium         INTEGER DEFAULT 0,
                onboarded          INTEGER DEFAULT 0,
                active             INTEGER DEFAULT 1,
                referral_code      TEXT    UNIQUE,
                referred_by        TEXT,
                referral_count     INTEGER DEFAULT 0,
                referral_counted   INTEGER DEFAULT 0,
                jobs_sent_today    INTEGER DEFAULT 0,
                last_reset_date    TEXT,
                last_notified_at   TIMESTAMP,
                joined_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Tracks exactly which jobs were sent to which users (never-sent enforcement)
            CREATE TABLE IF NOT EXISTS job_sends (
                job_id  INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (job_id, chat_id),
                FOREIGN KEY (job_id)  REFERENCES jobs(id)  ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            );

            -- Key-value store for scraper runtime configuration
            CREATE TABLE IF NOT EXISTS scraper_config (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
        ''')

        # --- Migrations: add new columns to existing DB if they don't exist ---
        for col in ["first_name", "phone", "age", "gender", "education_level", "situation", "full_name"]:
            try:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT 'web'")
        except sqlite3.OperationalError:
            pass

        # --- Seed default scraper config if empty ---
        defaults = {
            "scrape_interval_minutes": "5",
            "web_enabled": "1",
            "web_base_url": "https://www.hahu.jobs/jobs?min_yoe=0&max_yoe=100&page=",
            "web_start_page": "1",
            "web_end_page": "5",
            "tg_enabled": "1",
            "tg_channels": "freelance_ethio",
            "tg_message_limit": "30",
            "tg_api_id": "37290821",
            "tg_api_hash": "63e861c41a7a30c4a1c10abf4fca00cf",
            "tg_session": "my_session",
        }
        for k, v in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO scraper_config (key, value) VALUES (?, ?)",
                (k, v),
            )

        # --- Custom Groups ---
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS custom_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER,
                chat_id INTEGER,
                PRIMARY KEY (group_id, chat_id),
                FOREIGN KEY (group_id) REFERENCES custom_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
            );
        ''')



# ── Jobs ─────────────────────────────────────

def save_job(title, company, location, experience, description, deadline, url, source="web") -> bool:
    """Insert job. Returns True if new, False if duplicate."""
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT INTO jobs (title,company,location,experience,description,deadline,url,source) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (title, company, location, experience, description, deadline, url, source),
            )
        return True
    except sqlite3.IntegrityError:
        return False


# ── Scraper config ────────────────────────────────────────────────────────────

def get_scraper_config() -> dict:
    """Return all scraper_config rows as a plain dict."""
    with _conn() as conn:
        rows = conn.execute("SELECT key, value FROM scraper_config").fetchall()
    return {r["key"]: r["value"] for r in rows}


def save_scraper_config(updates: dict):
    """Upsert multiple key/value pairs into scraper_config."""
    with _conn() as conn:
        for k, v in updates.items():
            conn.execute(
                "INSERT INTO scraper_config (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, str(v)),
            )


def _profile_where(user: dict) -> tuple[str, list]:
    """Build a WHERE clause that filters jobs by the user's profile."""
    conditions: list[str] = ["1=1"]
    params: list = []

    # --- Category keywords ---
    cats = json.loads(user.get("job_categories") or "[]")
    if cats and "🌍 Other" not in cats:
        keywords: list[str] = []
        for cat in cats:
            keywords.extend(CATEGORY_KEYWORDS.get(cat, []))
        if keywords:
            sub = " OR ".join(
                ["(j.title REGEXP ? OR j.description REGEXP ?)"] * len(keywords)
            )
            conditions.append(f"({sub})")
            for kw in keywords:
                pattern = r'\b' + re.escape(kw.lower()) + r'\b'
                params.extend([pattern, pattern])

    # --- Location ---
    loc = (user.get("preferred_location") or "").strip()
    if loc and loc.lower() not in ("any", ""):
        conditions.append("LOWER(j.location) LIKE ?")
        params.append(f"%{loc.lower()}%")

    # --- Job types (keyword in title/description) ---
    jtypes = json.loads(user.get("job_types") or "[]")
    if jtypes:
        sub = " OR ".join(
            ["(j.title REGEXP ? OR j.description REGEXP ?)"] * len(jtypes)
        )
        conditions.append(f"({sub})")
        for jt in jtypes:
            pattern = r'\b' + re.escape(jt.lower()) + r'\b'
            params.extend([pattern, pattern])

    return " AND ".join(conditions), params


def search_jobs_for_user(user: dict, limit: int = 10) -> list[dict]:
    """All matching jobs — used for /latestjobs command."""
    where, params = _profile_where(user)
    sql = (
        f"SELECT j.title,j.company,j.location,j.experience,"
        f"j.description,j.deadline,j.url "
        f"FROM jobs j WHERE {where} ORDER BY j.scraped_at DESC LIMIT ?"
    )
    params.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def get_new_jobs_for_user(user: dict, limit: int = 10) -> list[dict]:
    """Jobs that have NEVER been sent to this user and match their profile."""
    chat_id = user["chat_id"]
    where, params = _profile_where(user)

    # Exclude jobs already sent to this user
    where += " AND j.id NOT IN (SELECT job_id FROM job_sends WHERE chat_id=?)"
    params.append(chat_id)

    sql = (
        f"SELECT j.id,j.title,j.company,j.location,j.experience,"
        f"j.description,j.deadline,j.url "
        f"FROM jobs j WHERE {where} ORDER BY j.scraped_at ASC LIMIT ?"
    )
    params.append(limit)
    with _conn() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def mark_job_sent(job_id: int, chat_id: int):
    """Record that job_id was sent to chat_id (idempotent)."""
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO job_sends (job_id, chat_id) VALUES (?, ?)",
                (job_id, chat_id),
            )
    except Exception:
        pass


def get_stats() -> dict:
    with _conn() as conn:
        total   = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        today   = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE DATE(scraped_at)=DATE('now')"
        ).fetchone()[0]
        subs    = conn.execute(
            "SELECT COUNT(*) FROM users WHERE active=1 AND onboarded=1"
        ).fetchone()[0]
        premium = conn.execute(
            "SELECT COUNT(*) FROM users WHERE is_premium=1"
        ).fetchone()[0]
    return {"total_jobs": total, "jobs_today": today,
            "active_subscribers": subs, "premium_users": premium}

# ── Custom Groups ─────────────────────────────

def get_custom_groups() -> list[dict]:
    with _conn() as conn:
        groups = conn.execute(
            "SELECT cg.*, COUNT(gm.chat_id) as member_count "
            "FROM custom_groups cg "
            "LEFT JOIN group_members gm ON cg.id = gm.group_id "
            "GROUP BY cg.id"
        ).fetchall()
        return [dict(r) for r in groups]

def create_custom_group(name: str) -> bool:
    try:
        with _conn() as conn:
            conn.execute("INSERT INTO custom_groups (name) VALUES (?)", (name,))
        return True
    except sqlite3.IntegrityError:
        return False

def add_users_to_group(group_id: int, chat_ids: list[int]):
    with _conn() as conn:
        for chat_id in chat_ids:
            try:
                conn.execute("INSERT INTO group_members (group_id, chat_id) VALUES (?, ?)", (group_id, chat_id))
            except sqlite3.IntegrityError:
                pass

def get_group_members(group_id: int) -> list[int]:
    with _conn() as conn:
        rows = conn.execute("SELECT chat_id FROM group_members WHERE group_id=?", (group_id,)).fetchall()
        return [r["chat_id"] for r in rows]

def delete_custom_group(group_id: int):
    with _conn() as conn:
        conn.execute("DELETE FROM group_members WHERE group_id=?", (group_id,))
        conn.execute("DELETE FROM custom_groups WHERE id=?", (group_id,))


# ── Users ─────────────────────────────────────

def _ref_code(chat_id: int) -> str:
    return hashlib.md5(str(chat_id).encode()).hexdigest()[:8].upper()


def create_user(chat_id: int, username: str, referred_by: str | None = None):
    """Insert user row if not already present."""
    code = _ref_code(chat_id)
    with _conn() as conn:
        conn.execute(
            "INSERT INTO users (chat_id,username,referral_code,referred_by) "
            "VALUES (?,?,?,?) ON CONFLICT(chat_id) DO NOTHING",
            (chat_id, username, code, referred_by),
        )


def get_user(chat_id: int) -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,)).fetchone()
    return dict(row) if row else None


def update_user_profile(
    chat_id: int,
    full_name: str,
    situation: str,
    location: str,
    job_types: list,
    age: str,
    gender: str,
    education_level: str
):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET full_name=?,situation=?,preferred_location=?,"
            "job_types=?,age=?,gender=?,education_level=? WHERE chat_id=?",
            (
                full_name, situation, location,
                json.dumps(job_types),
                age, gender, education_level,
                chat_id,
            ),
        )


def set_user_onboarded(chat_id: int):
    with _conn() as conn:
        conn.execute("UPDATE users SET onboarded=1 WHERE chat_id=?", (chat_id,))


def set_active(chat_id: int, active: bool):
    with _conn() as conn:
        conn.execute("UPDATE users SET active=? WHERE chat_id=?", (int(active), chat_id))


def get_referral_code(chat_id: int) -> str:
    with _conn() as conn:
        row = conn.execute(
            "SELECT referral_code FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()
    return row[0] if row else _ref_code(chat_id)


def record_referral(referral_code: str, new_user_chat_id: int) -> tuple[int, bool] | None:
    """
    Credit the referrer for bringing in new_user_chat_id.
    Returns (referrer_chat_id, upgraded_to_premium) or None.
    Each new user can only be counted once.
    """
    with _conn() as conn:
        # Guard: only count once per new user
        already = conn.execute(
            "SELECT referral_counted FROM users WHERE chat_id=?", (new_user_chat_id,)
        ).fetchone()
        if not already or already[0]:
            return None

        referrer = conn.execute(
            "SELECT chat_id,referral_count,is_premium FROM users WHERE referral_code=?",
            (referral_code,),
        ).fetchone()
        if not referrer:
            return None

        # Don't credit self-referrals
        if referrer["chat_id"] == new_user_chat_id:
            return None

        new_count   = referrer["referral_count"] + 1
        now_premium = (not referrer["is_premium"]) and (new_count >= REFERRALS_FOR_PREMIUM)

        conn.execute(
            "UPDATE users SET referral_count=?, is_premium=CASE WHEN ? THEN 1 ELSE is_premium END "
            "WHERE chat_id=?",
            (new_count, now_premium, referrer["chat_id"]),
        )
        conn.execute(
            "UPDATE users SET referral_counted=1 WHERE chat_id=?", (new_user_chat_id,)
        )

    return referrer["chat_id"], now_premium


# ── Daily limit helpers ───────────────────────

def _reset_daily_if_needed(chat_id: int):
    """Reset jobs_sent_today if the date has changed."""
    today = date.today().isoformat()
    with _conn() as conn:
        row = conn.execute(
            "SELECT last_reset_date FROM users WHERE chat_id=?", (chat_id,)
        ).fetchone()
        if row and row[0] != today:
            conn.execute(
                "UPDATE users SET jobs_sent_today=0, last_reset_date=? WHERE chat_id=?",
                (today, chat_id),
            )


def can_receive_job(chat_id: int) -> bool:
    _reset_daily_if_needed(chat_id)
    user = get_user(chat_id)
    if not user:
        return False
    return bool(user["is_premium"]) or user["jobs_sent_today"] < DAILY_JOB_LIMIT


def remaining_today(chat_id: int) -> int | None:
    """Returns jobs remaining today (None means unlimited / premium)."""
    _reset_daily_if_needed(chat_id)
    user = get_user(chat_id)
    if not user:
        return 0
    if user["is_premium"]:
        return None
    return max(0, DAILY_JOB_LIMIT - user["jobs_sent_today"])


def increment_jobs_sent(chat_id: int):
    today = date.today().isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET jobs_sent_today=jobs_sent_today+1, last_reset_date=? "
            "WHERE chat_id=?",
            (today, chat_id),
        )


def update_last_notified(chat_id: int):
    with _conn() as conn:
        conn.execute(
            "UPDATE users SET last_notified_at=CURRENT_TIMESTAMP WHERE chat_id=?",
            (chat_id,),
        )


def get_users_for_notification() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users WHERE active=1 AND onboarded=1"
        ).fetchall()
    return [dict(r) for r in rows]