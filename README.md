# SkilyJob Bot & Dashboard

A comprehensive Telegram bot for job scraping with a premium React-based administrative dashboard and FastAPI backend.

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js (for the dashboard)
- Google Chrome (for the scraper)

### 2. Installation

#### Backend (Bot & API)
```powershell
# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

#### Frontend (Dashboard)
```powershell
cd dashboard
npm install
cd ..
```

### 3. Configuration
Edit `config.py` with your Telegram Bot Token from [@BotFather](https://t.me/BotFather).
```python
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
```

---

## 🛠️ Running the Application

To run the full system, you need to start three components. It's recommended to run them in separate terminal windows.

### 1. The Telegram Bot
This handles job alerts, user onboarding, and the referral system.
```powershell
python bot.py
```

### 2. The Dashboard API (FastAPI)
This provides the data for the dashboard and handles broadcast messages.
```powershell
.\.venv\Scripts\uvicorn fastapi_app:app --reload
```

### 3. The Dashboard Frontend (React)
The visual interface for monitoring activity.
```powershell
cd dashboard
npm run dev
```
Once started, open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 📊 Dashboard Features
- **Overview:** Real-time stats on jobs scraped and active subscribers.
- **Job Charts:** Visual breakdown of jobs by category.
- **User Management:** Detailed activity logs for every user.
- **Broadcast:** Target specific groups (Premium, All, or by Category) with custom messages.

## 📁 Project Structure
- `bot.py`: Main Telegram bot logic.
- `scraper.py`: Selenium-based scraper for job sites.
- `fastapi_app.py`: Backend API for the dashboard.
- `dashboard/`: React frontend source code.
- `db.py`: Shared database layer.
- `config.py`: Centralized configuration.
