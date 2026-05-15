# SkilyJob Admin Dashboard (Frontend)

This is the React-based frontend for monitoring the SkilyJob Bot.

## 🛠️ How to Run

1. **Install Dependencies**
   ```bash
   npm install
   ```

2. **Start the Development Server**
   ```bash
   npm run dev
   ```
   The dashboard will be available at [http://localhost:5173](http://localhost:5173).

## 🔌 Connection
This dashboard connects to the FastAPI backend at `http://localhost:8000`. Ensure the backend (`fastapi_app.py`) is running simultaneously.

## 📦 Dependencies
- **Recharts**: For job category visualization.
- **Lucide-React**: For icons.
- **Vite**: For fast development and bundling.
