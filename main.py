import sqlite3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import time
import os

def init_db():
    """Initializes the SQLite database and creates the jobs table if it doesn't exist."""
    conn = sqlite3.connect('jobs.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            experience TEXT,
            description TEXT,
            deadline TEXT,
            url TEXT UNIQUE,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    return conn

def scrape_hahu_jobs(url):
    # Initialize Database connection
    db_conn = init_db()
    cursor = db_conn.cursor()

    # Set up Chrome to run in "headless" mode
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36")

    print("Launching browser...")
    try:
        driver = webdriver.Chrome(options=chrome_options)
    except Exception as e:
        print(f"Error launching browser: {e}")
        return

    try:
        print(f"Loading URL: {url}")
        driver.get(url)
        print("Waiting for content to load...")
        time.sleep(7) 

        html_content = driver.page_source
        soup = BeautifulSoup(html_content, 'html.parser')

        # Find the job cards using classes
        job_cards = soup.find_all('div', class_=lambda x: x and 'rounded-xl' in x and 'shadow-md' in x)
        
        if not job_cards:
            print("Trying fallback card detection...")
            job_cards = [h3.find_parent('div', class_=lambda x: x and 'rounded-xl' in x) for h3 in soup.find_all('h3')]
            job_cards = [j for j in job_cards if j]

        if not job_cards:
            print("No jobs found on the page.")
            return

        print(f"Found {len(job_cards)} potential job cards. Processing...\n")


        new_jobs_count = 0
        skipped_count = 0
        duplicate_count = 0

        for index, job in enumerate(job_cards):
            try:
                # 1. Extract Title
                title_elem = job.find('h3')
                if not title_elem: continue
                title = title_elem.text.strip()
                
                # 2. Extract Company/Category
                company_elem = title_elem.find_next('p')
                company = company_elem.text.strip() if company_elem else "Unknown"
                
                # 3. Extract Job URL
                link_elem = job.find('a', href=True)
                job_url = "https://www.hahu.jobs" + link_elem['href'] if link_elem else None
                if not job_url: continue

                # 4. Check for Deadline (Case-insensitive search for "Left")
                # We search the whole card text first to be sure
                card_text = job.get_text(separator=' ')
                if 'Left' not in card_text and 'left' not in card_text:
                    skipped_count += 1
                    continue
                
                # Try to find the specific element for a cleaner string
                deadline_elem = job.find(lambda t: t.name in ['p', 'span'] and 'left' in t.text.lower())
                deadline_text = deadline_elem.text.strip() if deadline_elem else "Active (Time Left)"

                # 5. Extract Details (Location, Experience)
                info_elements = job.find_all(['p', 'span'], class_=lambda x: x and ('text-gray-600' in x or 'text-sm' in x))
                details = [el.text.strip() for el in info_elements if len(el.text.strip()) < 50]
                
                location = details[2] if len(details) >= 3 else "N/A"
                experience = details[3] if len(details) >= 4 else "N/A"
                
                # 6. Description
                desc_elem = job.find('p', class_='line-clamp-3')
                description = desc_elem.text.strip() if desc_elem else ""

                # 7. Duplicate Check
                cursor.execute("SELECT id FROM jobs WHERE url = ?", (job_url,))
                if cursor.fetchone():
                    duplicate_count += 1
                    continue

                # 8. Insert into Database
                cursor.execute('''
                    INSERT INTO jobs (title, company, location, experience, description, deadline, url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (title, company, location, experience, description, deadline_text, job_url))
                
                db_conn.commit()
                new_jobs_count += 1
                print(f"[*] [{new_jobs_count}] Saved: {title} | {deadline_text}")

            except Exception:
                continue

        return[job_cards, new_jobs_count, duplicate_count, skipped_count]


    except Exception as e:
        print(f"An error occurred: {e}")
        
    finally:
        db_conn.close()
        driver.quit()

if __name__ == "__main__":
    target_url = "https://www.hahu.jobs/jobs?min_yoe=0&max_yoe=100&page="
    total_prossed = 0
    total_new_jobs = 0
    total_duplicates = 0
    total_skipped = 0
    for i in range(11, 20):
        result = scrape_hahu_jobs(target_url + str(i))
        total_prossed += len(result[0])
        total_new_jobs += result[1]
        total_duplicates += result[2]
        total_skipped += result[3]
    
    print(f"\nTotal Summary:")
    print(f"   - Total Processed: {total_prossed}")
    print(f"   - Total New Jobs Added:  {total_new_jobs}")
    print(f"   - Total Duplicates:      {total_duplicates}")
    print(f"   - Total Skipped (Exp):   {total_skipped}")
    print(f"\nAll data saved to 'jobs.db'")
