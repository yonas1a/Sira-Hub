from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
import subprocess
import sys
import requests
import json
import os
import re
import db
import config

db.init_db()
app = FastAPI(title="Job Bot Dashboard API")

# Allow CORS for dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def get_db_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = dict_factory
    return conn

@app.get("/api/stats")
def get_stats():
    return db.get_stats()

@app.get("/api/users")
def get_users():
    with get_db_conn() as conn:
        users = conn.execute("SELECT * FROM users ORDER BY joined_at DESC").fetchall()
        for u in users:
            try:
                u['job_categories'] = json.loads(u.get('job_categories') or '[]')
            except:
                u['job_categories'] = []
            try:
                u['job_types'] = json.loads(u.get('job_types') or '[]')
            except:
                u['job_types'] = []
        return users

@app.get("/api/jobs-chart")
def get_jobs_chart():
    # Count jobs matching category keywords
    with get_db_conn() as conn:
        jobs = conn.execute("SELECT title, description FROM jobs").fetchall()
    
    counts = {cat: 0 for cat in db.CATEGORY_KEYWORDS.keys()}
    counts["Other"] = 0
    
    for job in jobs:
        text = f"{job['title']} {job['description']}".lower()
        matched = False
        for cat, keywords in db.CATEGORY_KEYWORDS.items():
            if not keywords: continue
            for kw in keywords:
                if re.search(r'\b' + re.escape(kw.lower()) + r'\b', text):
                    counts[cat] += 1
                    matched = True
                    break
            if matched:
                break
        if not matched:
            counts["🌍 Other"] += 1

    chart_data = [{"category": k.split(' ', 1)[-1] if ' ' in k else k, "count": v} for k, v in counts.items() if v > 0]
    return chart_data

@app.get("/api/jobs")
def get_jobs(limit: int = 50):
    with get_db_conn() as conn:
        jobs = conn.execute("SELECT * FROM jobs ORDER BY scraped_at DESC LIMIT ?", (limit,)).fetchall()
        return jobs

class MessageConditions(BaseModel):
    access_type: str = "all" # all, premium, standard
    age_range: str = "all"   # all, <18, 18-24, 25-34, 35+
    job_type: str = "all"    # all, Remote, Full-time, etc
    category: str = "all"    # all, IT, Sales, etc
    custom_group_id: int | None = None

class CreateGroupReq(BaseModel):
    name: str

@app.get("/api/groups")
def get_groups():
    return db.get_custom_groups()

@app.post("/api/groups")
def create_group(req: CreateGroupReq):
    if db.create_custom_group(req.name):
        return {"status": "created"}
    raise HTTPException(status_code=400, detail="Group name already exists")

class AddUsersReq(BaseModel):
    chat_ids: list[int]

@app.post("/api/groups/{group_id}/add-users")
def add_users(group_id: int, req: AddUsersReq):
    db.add_users_to_group(group_id, req.chat_ids)
    return {"status": "added"}

class MessageRequest(BaseModel):
    conditions: MessageConditions
    message: str


def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except:
        pass

def process_message_sending(req: MessageRequest):
    conds = req.conditions

    if conds.custom_group_id:
        chat_ids = db.get_group_members(conds.custom_group_id)
        for cid in chat_ids:
            send_telegram_message(cid, req.message)
        return

    with get_db_conn() as conn:
        users = conn.execute("SELECT chat_id, is_premium, job_categories, job_types, age FROM users WHERE active=1").fetchall()
    
    for u in users:
        send_it = True
        
        # Access type check
        if conds.access_type == "premium" and not u['is_premium']:
            send_it = False
        elif conds.access_type == "standard" and u['is_premium']:
            send_it = False
            
        # Age range check
        if send_it and conds.age_range != "all":
            try:
                age = int(u['age'])
                if conds.age_range == "<18" and age >= 18: send_it = False
                elif conds.age_range == "18-24" and (age < 18 or age > 24): send_it = False
                elif conds.age_range == "25-34" and (age < 25 or age > 34): send_it = False
                elif conds.age_range == "35+" and age < 35: send_it = False
            except:
                send_it = False # If age is missing or invalid
                
        # Category check
        if send_it and conds.category != "all":
            try:
                user_cats = json.loads(u.get('job_categories') or '[]')
                # Extract simple category name for matching
                simple_cats = [c.split(' ', 1)[-1] if ' ' in c else c for c in user_cats]
                if conds.category not in simple_cats:
                    send_it = False
            except:
                send_it = False
                
        # Job Type check
        if send_it and conds.job_type != "all":
            try:
                user_jtypes = json.loads(u.get('job_types') or '[]')
                if conds.job_type not in user_jtypes:
                    send_it = False
            except:
                send_it = False
                
        if send_it:
            send_telegram_message(u['chat_id'], req.message)


@app.post("/api/send-message")
def send_message(req: MessageRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(process_message_sending, req)
    return {"status": "sending in background"}


# ── Scraper Config ────────────────────────────────────────────────────────────

@app.get("/api/scraper-config")
def get_scraper_config():
    return db.get_scraper_config()


class ScraperConfigUpdate(BaseModel):
    scrape_interval_minutes: str | None = None
    web_enabled: str | None = None
    web_base_url: str | None = None
    web_start_page: str | None = None
    web_end_page: str | None = None
    tg_enabled: str | None = None
    tg_channels: str | None = None
    tg_message_limit: str | None = None
    tg_api_id: str | None = None
    tg_api_hash: str | None = None
    tg_session: str | None = None


@app.post("/api/scraper-config")
def update_scraper_config(body: ScraperConfigUpdate):
    updates = {k: v for k, v in body.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided")
    db.save_scraper_config(updates)
    return {"status": "saved", "updated": list(updates.keys())}


@app.post("/api/scraper/trigger")
def trigger_scraper(background_tasks: BackgroundTasks):
    """Launch the combined scraper as a background subprocess (fire-and-forget)."""
    def _run():
        try:
            subprocess.Popen(
                [sys.executable, "scraper_combined.py", "--once"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            pass
    background_tasks.add_task(_run)
    return {"status": "triggered"}


# ── User Profile (Webapp) ─────────────────────────────────────────────────────

@app.get("/api/user/{chat_id}")
def get_user_profile(chat_id: int):
    user = db.get_user(chat_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        user["job_categories"] = json.loads(user.get("job_categories") or "[]")
    except Exception:
        user["job_categories"] = []
    try:
        user["job_types"] = json.loads(user.get("job_types") or "[]")
    except Exception:
        user["job_types"] = []
    return user


class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    age: Optional[str] = None
    job_categories: Optional[List[str]] = None
    job_types: Optional[List[str]] = None
    preferred_location: Optional[str] = None


@app.put("/api/user/{chat_id}")
def update_user_profile(chat_id: int, body: UserProfileUpdate):
    user = db.get_user(chat_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    with get_db_conn() as conn:
        fields, vals = [], []
        if body.first_name is not None:
            fields.append("first_name=?"); vals.append(body.first_name)
        if body.age is not None:
            fields.append("age=?"); vals.append(body.age)
        if body.job_categories is not None:
            fields.append("job_categories=?"); vals.append(json.dumps(body.job_categories))
        if body.job_types is not None:
            fields.append("job_types=?"); vals.append(json.dumps(body.job_types))
        if body.preferred_location is not None:
            fields.append("preferred_location=?"); vals.append(body.preferred_location)
        if fields:
            vals.append(chat_id)
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE chat_id=?", vals)
    return {"status": "updated"}


# ── Categories list ───────────────────────────────────────────────────────────

@app.get("/api/categories")
def get_categories():
    return list(db.CATEGORY_KEYWORDS.keys())


# ── Job Search (Webapp) ───────────────────────────────────────────────────────

@app.get("/api/jobs/search")
def search_jobs(
    q: str = "",
    category: str = "all",
    source: str = "all",
    location: str = "",
    page: int = 1,
    limit: int = 20,
):
    with get_db_conn() as conn:
        conditions = ["1=1"]
        params = []

        if q.strip():
            conditions.append("(title LIKE ? OR description LIKE ? OR company LIKE ?)")
            params += [f"%{q}%", f"%{q}%", f"%{q}%"]

        if category != "all":
            kws = db.CATEGORY_KEYWORDS.get(category, [])
            if kws:
                sub = " OR ".join(
                    ["(title LIKE ? OR description LIKE ?)"] * len(kws)
                )
                conditions.append(f"({sub})")
                for kw in kws:
                    params += [f"%{kw}%", f"%{kw}%"]

        if source != "all":
            conditions.append("source=?")
            params.append(source)

        if location.strip():
            conditions.append("location LIKE ?")
            params.append(f"%{location}%")

        where = " AND ".join(conditions)
        offset = (page - 1) * limit

        total_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM jobs WHERE {where}", params
        ).fetchone()
        total = total_row["cnt"] if total_row else 0

        jobs = conn.execute(
            f"SELECT id,title,company,location,experience,deadline,url,source,scraped_at "
            f"FROM jobs WHERE {where} ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {"total": total, "page": page, "limit": limit, "jobs": jobs}


# ── Jobs by Source (Dashboard chart) ─────────────────────────────────────────

@app.get("/api/jobs/by-source")
def jobs_by_source():
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT COALESCE(source,'web') as source, COUNT(*) as count "
            "FROM jobs GROUP BY source ORDER BY count DESC"
        ).fetchall()
    return rows


# ── Serve User Webapp ─────────────────────────────────────────────────────────

WEBAPP_PATH = os.path.join(os.path.dirname(__file__), "webapp", "index.html")

@app.get("/app", include_in_schema=False)
@app.get("/app/{path:path}", include_in_schema=False)
def serve_webapp(path: str = ""):
    if os.path.exists(WEBAPP_PATH):
        return FileResponse(WEBAPP_PATH)
    raise HTTPException(status_code=404, detail="Webapp not built yet")
