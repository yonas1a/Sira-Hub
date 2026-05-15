#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────────────────────
#  scraper_combined.py  —  Unified Job Scraper (Web + Telegram)
#
#  Runs as a standalone service.  Every SCRAPE_INTERVAL_MINUTES minutes it:
#   1. Scrapes configured web URLs (currently Hahu Jobs) with Selenium
#   2. Scrapes configured Telegram channels with Telethon
#
#  Settings are read from the `scraper_config` table in jobs.db so the React
#  dashboard can update them at runtime without restarting this process.
# ─────────────────────────────────────────────────────────────────────────────
import asyncio
import logging
import sys
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from apscheduler.schedulers.background import BackgroundScheduler

from config import DB_PATH
from db import init_db, save_job, get_scraper_config

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("scraper")

# ── Web scraper ───────────────────────────────────────────────────────────────

def _build_driver() -> webdriver.Chrome:
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=opts)


def _parse_cards(soup: BeautifulSoup) -> list:
    cards = soup.find_all(
        "div", class_=lambda x: x and "rounded-xl" in x and "shadow-md" in x
    )
    if not cards:
        cards = [
            h3.find_parent("div", class_=lambda x: x and "rounded-xl" in x)
            for h3 in soup.find_all("h3")
        ]
        cards = [c for c in cards if c]
    return cards


def _extract_job(card) -> dict | None:
    try:
        title_elem = card.find("h3")
        if not title_elem:
            return None
        title = title_elem.text.strip()

        company_elem = title_elem.find_next("p")
        company = company_elem.text.strip() if company_elem else "Unknown"

        link_elem = card.find("a", href=True)
        if not link_elem:
            return None
        job_url = "https://www.hahu.jobs" + link_elem["href"]

        card_text = card.get_text(separator=" ")
        if "left" not in card_text.lower():
            return None

        deadline_elem = card.find(
            lambda t: t.name in ["p", "span"] and "left" in t.text.lower()
        )
        deadline = deadline_elem.text.strip() if deadline_elem else "Active"

        info_elems = card.find_all(
            ["p", "span"],
            class_=lambda x: x and ("text-gray-600" in x or "text-sm" in x),
        )
        details = [el.text.strip() for el in info_elems if len(el.text.strip()) < 50]
        location = details[2] if len(details) >= 3 else "N/A"
        experience = details[3] if len(details) >= 4 else "N/A"

        desc_elem = card.find("p", class_="line-clamp-3")
        description = desc_elem.text.strip() if desc_elem else ""

        return {
            "title": title, "company": company, "location": location,
            "experience": experience, "description": description,
            "deadline": deadline, "url": job_url,
            "source": "web",
        }
    except Exception:
        return None


def scrape_web_page(url: str) -> tuple[int, int]:
    driver = _build_driver()
    new_count = dup_count = 0
    try:
        logger.info(f"  [WEB] → {url}")
        driver.get(url)
        time.sleep(7)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        cards = _parse_cards(soup)
        logger.info(f"    {len(cards)} cards found")
        for card in cards:
            job = _extract_job(card)
            if job is None:
                continue
            if save_job(
                job["title"], job["company"], job["location"],
                job["experience"], job["description"], job["deadline"],
                job["url"], source=job["source"],
            ):
                new_count += 1
                logger.info(f"    ✅ NEW  : {job['title']}")
            else:
                dup_count += 1
    except Exception as e:
        logger.error(f"  [WEB] Page error: {e}")
    finally:
        driver.quit()
    return new_count, dup_count


def run_web_scrape(cfg: dict) -> tuple[int, int]:
    if not cfg.get("web_enabled", True):
        logger.info("  [WEB] Disabled — skipping.")
        return 0, 0

    base_url = cfg.get("web_base_url", "https://www.hahu.jobs/jobs?min_yoe=0&max_yoe=100&page=")
    start_page = int(cfg.get("web_start_page", 1))
    end_page = int(cfg.get("web_end_page", 5))

    logger.info(f"🌐 Web scrape: pages {start_page}–{end_page}")
    total_new = total_dup = 0
    for i in range(start_page, end_page + 1):
        logger.info(f"  📄 Page {i}/{end_page}")
        try:
            new, dup = scrape_web_page(base_url + str(i))
            total_new += new
            total_dup += dup
        except Exception as e:
            logger.error(f"  Page {i} failed: {e}")
    logger.info(f"  Web done — New: {total_new} | Dup: {total_dup}")
    return total_new, total_dup


# ── Telegram scraper ──────────────────────────────────────────────────────────

def _parse_telegram_job(text: str) -> dict:
    """Parses structured Telegram job posts (e.g., from Afriwork/Freelance Ethio)."""
    # 1. Detect Company (often between __________________ lines)
    parts = text.split("__________________")
    main_part = parts[0]
    company = "(via Telegram)"
    
    if len(parts) > 1:
        # The section between lines often contains the company name
        company_section = parts[1].strip()
        c_lines = [l.strip() for l in company_section.splitlines() if l.strip()]
        if c_lines:
            # First line of company section is usually the name
            company = c_lines[0].replace("Verified Company ✅", "").strip()

    # 2. Clean main content and extract fields
    lines = main_part.splitlines()
    structured_keys = ["job title", "job type", "work location", "applicants needed", "salary/compensation", "deadline", "description"]
    
    res = {
        "title": "Job Opportunity",
        "company": company,
        "location": "N/A",
        "experience": "N/A",
        "deadline": "Active",
        "description": ""
    }
    
    desc_lines = []
    in_description_block = False

    for line in lines:
        l = line.strip()
        
        # Eliminate footer handles/links as requested
        if l.lower().startswith("from:") and ("@" in l or "afriwork" in l or "freelance" in l):
            continue
        if l.startswith("@") and ("bot" in l or "afriwork" in l or "freelance" in l):
            continue

        # Extract structured fields
        if ":" in l and not in_description_block:
            key_part, val_part = l.split(":", 1)
            key = key_part.strip().lower()
            val = val_part.strip()
            
            if key == "job title":
                res["title"] = val
                continue
            elif key == "job type":
                res["experience"] = val
                continue
            elif key == "work location":
                res["location"] = val
                continue
            elif key == "deadline":
                res["deadline"] = val
                continue
            elif key == "description":
                in_description_block = True
                if val: desc_lines.append(val)
                continue

        # If we reach this point, it's either description content or other info
        if l or desc_lines: # skip leading empty lines
            desc_lines.append(line)

    res["description"] = "\n".join(desc_lines).strip()
    return res


async def _scrape_telegram_channel(client, channel: str, limit: int) -> tuple[int, int]:
    new_count = dup_count = 0
    logger.info(f"  [TG] Scanning @{channel} (last {limit} msgs)…")
    try:
        async for msg in client.iter_messages(channel, limit=limit):
            if not msg.text:
                continue
            text = msg.text.strip()
            if len(text) < 30:
                continue  # skip noise

            # Parse the structured text
            job_data = _parse_telegram_job(text)
            url = f"https://t.me/{channel}/{msg.id}"

            if save_job(
                title=job_data["title"],
                company=job_data["company"],
                location=job_data["location"],
                experience=job_data["experience"],
                description=job_data["description"],
                deadline=job_data["deadline"],
                url=url,
                source="telegram",
            ):
                new_count += 1
                logger.info(f"    ✅ NEW TG: {job_data['title'][:60]}")
            else:
                dup_count += 1
    except Exception as e:
        logger.error(f"  [TG] Error on @{channel}: {e}")
    return new_count, dup_count


async def run_telegram_scrape_async(cfg: dict) -> tuple[int, int]:
    if not cfg.get("tg_enabled", True):
        logger.info("  [TG] Disabled — skipping.")
        return 0, 0

    channels_raw = cfg.get("tg_channels", "freelance_ethio")
    channels = [c.strip().lstrip("@") for c in channels_raw.split(",") if c.strip()]
    limit = int(cfg.get("tg_message_limit", 30))
    api_id = int(cfg.get("tg_api_id", 0))
    api_hash = cfg.get("tg_api_hash", "")
    session_name = cfg.get("tg_session", "my_session")

    if not api_id or not api_hash:
        logger.warning("  [TG] api_id / api_hash not configured — skipping.")
        return 0, 0

    # Lazy import so the rest of the scraper works without telethon installed
    try:
        from telethon import TelegramClient
    except ImportError:
        logger.error("  [TG] telethon not installed. Run: pip install telethon")
        return 0, 0

    total_new = total_dup = 0
    client = TelegramClient(session_name, api_id, api_hash)
    async with client:
        for ch in channels:
            n, d = await _scrape_telegram_channel(client, ch, limit)
            total_new += n
            total_dup += d
    logger.info(f"  TG done — New: {total_new} | Dup: {total_dup}")
    return total_new, total_dup


def run_telegram_scrape(cfg: dict) -> tuple[int, int]:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(run_telegram_scrape_async(cfg))
    except Exception as e:
        logger.error(f"[TG] Async runner error: {e}")
        return 0, 0


# ── Combined run ──────────────────────────────────────────────────────────────

def run_all():
    logger.info("=" * 60)
    logger.info("🕷  Combined scrape cycle started")
    logger.info("=" * 60)

    cfg = get_scraper_config()

    web_new, web_dup = run_web_scrape(cfg)
    tg_new, tg_dup = run_telegram_scrape(cfg)

    logger.info("=" * 60)
    logger.info(
        f"✅ Cycle done | Web new: {web_new} | TG new: {tg_new} | "
        f"Dup: {web_dup + tg_dup}"
    )
    logger.info("=" * 60)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Combined Job Scraper")
    parser.add_argument(
        "--once", action="store_true",
        help="Run a single scrape cycle then exit (used by dashboard trigger)",
    )
    args = parser.parse_args()

    init_db()

    if args.once:
        logger.info("🔂 Single-run mode (--once)")
        run_all()
        return

    cfg = get_scraper_config()
    interval_minutes = int(cfg.get("scrape_interval_minutes", 5))

    logger.info(f"⏰ Scraper service started — interval: {interval_minutes} min")
    logger.info("   Press Ctrl+C to stop.\n")

    # Run immediately on start
    run_all()

    scheduler = BackgroundScheduler(timezone="Africa/Addis_Ababa")
    scheduler.add_job(
        run_all,
        "interval",
        minutes=interval_minutes,
        id="combined_scrape",
    )
    scheduler.start()

    try:
        while True:
            time.sleep(30)
            # Reload interval dynamically (in case dashboard changed it)
            new_cfg = get_scraper_config()
            new_interval = int(new_cfg.get("scrape_interval_minutes", 5))
            if new_interval != interval_minutes:
                interval_minutes = new_interval
                scheduler.reschedule_job(
                    "combined_scrape", trigger="interval", minutes=interval_minutes
                )
                logger.info(f"⏰ Interval updated to {interval_minutes} min")
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scraper stopped.")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
