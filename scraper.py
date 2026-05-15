#!/usr/bin/env python3
# ─────────────────────────────────────────────
#  scraper.py  —  Standalone Hahu Jobs Scraper
#
#  Run once:          python scraper.py
#  Run on schedule:   python scraper.py --schedule
# ─────────────────────────────────────────────
import argparse
import logging
import sys
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from apscheduler.schedulers.blocking import BlockingScheduler

from config import BASE_URL, DB_PATH, END_PAGE, SCRAPE_INTERVAL_HOURS, START_PAGE
from db import init_db, save_job

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("scraper.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("scraper")


# ── Driver ────────────────────────────────────

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


# ── Parsing ───────────────────────────────────

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

        # Skip expired listings
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
        details    = [el.text.strip() for el in info_elems if len(el.text.strip()) < 50]
        location   = details[2] if len(details) >= 3 else "N/A"
        experience = details[3] if len(details) >= 4 else "N/A"

        desc_elem   = card.find("p", class_="line-clamp-3")
        description = desc_elem.text.strip() if desc_elem else ""

        return {
            "title": title, "company": company, "location": location,
            "experience": experience, "description": description,
            "deadline": deadline, "url": job_url,
        }
    except Exception:
        return None


# ── Page scraper ──────────────────────────────

def scrape_page(url: str) -> tuple[int, int]:
    """
    Scrape a single page.
    Returns (new_jobs_count, duplicate_count).
    """
    driver = _build_driver()
    new_count = dup_count = 0

    try:
        logger.info(f"  → {url}")
        driver.get(url)
        time.sleep(7)

        soup  = BeautifulSoup(driver.page_source, "html.parser")
        cards = _parse_cards(soup)
        logger.info(f"    {len(cards)} cards found")

        for card in cards:
            job = _extract_job(card)
            if job is None:
                continue
            if save_job(
                job["title"], job["company"], job["location"],
                job["experience"], job["description"], job["deadline"], job["url"],
            ):
                new_count += 1
                logger.info(f"    ✅ NEW  : {job['title']}")
            else:
                dup_count += 1

    except Exception as e:
        logger.error(f"  Page error: {e}")
    finally:
        driver.quit()

    return new_count, dup_count


# ── Full run ──────────────────────────────────

def run_scrape():
    logger.info("=" * 55)
    logger.info(f"🕷  Scrape started — pages {START_PAGE}–{END_PAGE}")
    logger.info("=" * 55)
    total_new = total_dup = 0

    for i in range(START_PAGE, END_PAGE + 1):
        logger.info(f"📄 Page {i}/{END_PAGE}")
        try:
            new, dup = scrape_page(BASE_URL + str(i))
            total_new += new
            total_dup += dup
        except Exception as e:
            logger.error(f"  Page {i} failed: {e}")

    logger.info("=" * 55)
    logger.info(f"✅ Done  |  New: {total_new}  |  Duplicates: {total_dup}")
    logger.info("=" * 55)


# ── Entry point ───────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hahu Jobs Scraper")
    parser.add_argument(
        "--schedule", action="store_true",
        help=f"Keep running and scrape every {SCRAPE_INTERVAL_HOURS} hour(s)",
    )
    args = parser.parse_args()

    init_db()

    if args.schedule:
        logger.info(f"⏰ Scheduler mode — every {SCRAPE_INTERVAL_HOURS} hour(s). Press Ctrl+C to stop.")
        run_scrape()  # immediate first run

        scheduler = BlockingScheduler(timezone="Africa/Addis_Ababa")
        scheduler.add_job(run_scrape, "interval", hours=SCRAPE_INTERVAL_HOURS)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scraper stopped.")
    else:
        run_scrape()


if __name__ == "__main__":
    main()