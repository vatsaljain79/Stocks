# Golden Harbor 🏦
> A virtual stock trading simulator using live NSE (National Stock Exchange) data.

Built with **Flask** · **SQLite** · **jugaad-data** · **yfinance** · **Chart.js** · **Bootstrap-free custom CSS**

---

## Features

| Feature | Details |
|---|---|
| 📈 Live prices | NSE live quotes via `jugaad-data`, auto-refreshed every 15 s without page reload |
| 🔐 Auth | Register / Login with hashed passwords (PBKDF2-SHA256) |
| 💰 Virtual balance | Start with ₹1,00,000. Buy stocks (balance deducted) or sell (balance credited) |
| 🛡️ Validations | Cannot buy if insufficient balance · Cannot sell more shares than owned (no short-selling) |
| 📋 Watchlist | Add / remove any NIFTY 50 stock · Clear-all button · Persisted per user |
| 📊 Stock charts | Historical OHLCV charts via yfinance (line or candlestick, multiple time windows) |
| 🔄 Reset | "Reset Balance" wipes all holdings and history, restores ₹1,00,000 |
| 🕐 IST timestamps | Every buy/sell history entry is timestamped in Indian Standard Time |
| 🌐 All Indices page | Full NIFTY 50 table with filters (price range, live price, open), performance sort, and live polling |

---

## Project Structure

```
.
├── app.py                  # Flask application — routes, DB models, live-data helpers
├── ind_nifty50list.csv     # NIFTY 50 company list (name, symbol, industry …)
├── requirements.txt        # Python dependencies
├── .gitignore
│
├── templates/              # Jinja2 HTML templates
│   ├── login.html          # Login page (split-panel, IST clock)
│   ├── register.html       # Registration page
│   ├── main.html           # Dashboard — portfolio, history, balance
│   ├── allindices.html     # NIFTY 50 table with live polling & filters
│   ├── eachstock.html      # Individual stock page — buy / sell sliders
│   ├── watchlist.html      # Watchlist dropdown fragment (loaded via AJAX)
│   └── welcome.html        # Landing / welcome page
│
├── static/                 # Static assets
│   ├── main.css
│   ├── eachstock.css
│   ├── ind.css
│   ├── style.css / styles.css
│   ├── back1.jpg / back2.jpg / back3.jpg   # Background images
│   └── logo.png / icon.png / …
│
└── instance/
    └── users.db            # SQLite database (auto-created on first run)
```

---

## Prerequisites

- **Python 3.10+** (tested on 3.11)
- `pip` and optionally a virtual environment tool (`venv` / `conda`)
- Internet connection — live NSE data is fetched at runtime

---

## Setup & Running

### 1. Clone / download the project

```bash
git clone <your-repo-url>
cd "COP A-1 Task-2"
```

### 2. Create and activate a virtual environment

**Windows (PowerShell)**
```powershell
python -m venv env
.\env\Scripts\Activate.ps1
```

**macOS / Linux**
```bash
python3 -m venv env
source env/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. (Optional) Create a `.env` file

The app uses an optional Finnhub API key. Create a `.env` in the project root if you have one:

```
FINNHUB_API_KEY=your_key_here
```

> The app works without this key — it falls back to NSE live data.

### 5. Run the app

```bash
python app.py
```

Open your browser at **http://127.0.0.1:3001**

> The SQLite database (`instance/users.db`) is created automatically on the first run.

---

## Usage

1. **Register** a new account — you start with ₹1,00,000 virtual balance.
2. Browse **All Indices** to see live NIFTY 50 prices (auto-updates every 15 s).
3. Click any stock symbol to open its detail page and **Buy / Sell** using the sliders.
4. Track your portfolio, transaction history, and current balance on the **Dashboard**.
5. Use the **Watchlist** (top-right dropdown) to bookmark stocks.
6. Use **Reset Balance** on the dashboard to start fresh.

---

## Key Routes

| Route | Method | Description |
|---|---|---|
| `/` | GET | Login page |
| `/register` | GET / POST | Registration |
| `/login` | POST | Authenticate and start session |
| `/logout` | GET | End session |
| `/main` | GET | Dashboard |
| `/allindices` | GET | NIFTY 50 table |
| `/allindexes/<symbol>` | GET | Individual stock page |
| `/update_buy` | POST | Buy stock (validates balance) |
| `/update_sell` | POST | Sell stock (validates ownership) |
| `/reset_balance` | POST | Reset to ₹1,00,000 |
| `/update_watch` | POST | Add / remove from watchlist |
| `/clear_watchlist` | POST | Clear entire watchlist |
| `/api/live_prices` | GET | JSON live prices for `?symbols=SYM1,SYM2` |
| `/get_chart_data/<symbol>` | GET | OHLCV chart data (yfinance, 3-tier fallback) |
| `/api/finnhub_key` | GET | Exposes Finnhub API key for frontend WebSocket |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 2.0 |
| Database | SQLite via Flask-SQLAlchemy |
| Live NSE data | jugaad-data (NSELive) |
| Historical OHLCV data | yfinance (3-tier fallback: `download` → `Ticker.history` → NSE API) |
| Real-time ticker | Finnhub WebSocket (optional — key via `.env`) |
| Charts | Chart.js (rendered in-browser from JSON data) |
| Frontend | Vanilla JS + custom CSS (Inter font) |
| Auth | Werkzeug password hashing (PBKDF2-SHA256) |

---

## Notes

- Live NSE data is only available during **market hours** (Mon–Fri, 9:15 AM – 3:30 PM IST). Outside market hours, prices show the last known values or `N/A`.
- The app is intended for **educational / paper trading** purposes only. No real money is involved.
- The `tempCodeRunnerFile.py` at the root is auto-generated by VS Code's Code Runner extension and can be ignored.
