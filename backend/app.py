from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from jugaad_data.nse import NSELive, stock_df as jugaad_stock_df
from sqlalchemy import JSON   # generic — works with both SQLite and PostgreSQL
import decimal
import pandas as pd
from datetime import date
import time, random
import os, requests as http_requests
import yfinance as yf

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY', 'dev-only-fallback-secret')

# ── CSV path is relative to this file so it works on any server ────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
all_stocks = pd.read_csv(os.path.join(BASE_DIR, 'ind_nifty50list.csv'), index_col=0)
all_stocks = all_stocks.drop(['Industry', 'Series', 'ISIN Code'], axis=1)
all_stocks_names = all_stocks.index.tolist()
performance = []

# ── Database ────────────────────────────────────────────────────────────────
# Render injects DATABASE_URL (PostgreSQL). Falls back to SQLite for local dev.
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "users.db")}')
# SQLAlchemy requires postgresql:// not postgres:// (Render uses the old prefix)
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

Live_Market = NSELive()


def format_inr(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)
    integer_part = int(abs(value))
    decimal_part = f"{abs(value) % 1:.2f}"[1:]  # ".XX"
    s = str(integer_part)
    if len(s) > 3:
        result = s[-3:]
        s = s[:-3]
        while len(s) > 2:
            result = s[-2:] + ',' + result
            s = s[:-2]
        result = s + ',' + result
    else:
        result = s
    sign = '-' if value < 0 else ''
    return f"{sign}₹{result}{decimal_part}"


app.jinja_env.filters['inr'] = format_inr


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    stocks_bought = db.Column(db.PickleType)
    stocks_sold = db.Column(db.PickleType)
    curr_balance = db.Column(db.Float)
    curr_stocks = db.Column(JSON)
    state_watch = db.Column(db.String(255))
    curr_states = db.Column(db.PickleType)


with app.app_context():
    db.create_all()


MOCK_PRICE_INFO = {
    'lastPrice': 'N/A',
    'change': 0,
    'pChange': 0,
    'open': 'N/A',
    'previousClose': 'N/A',
    'intraDayHighLow': {'max': 'N/A', 'min': 'N/A'},
    'weekHighLow': {'max': 'N/A', 'min': 'N/A'},
}


def fetch_live_data_stock(symbol):
    try:
        return Live_Market.stock_quote(symbol)['priceInfo']
    except Exception as e:
        print(f"Warning: NSE live data unavailable for {symbol}: {e}")
        return MOCK_PRICE_INFO


# ── Per-request user state helpers ─────────────────────────────────────────
# Instead of unsafe module-level globals, we read/write the DB every request.

def get_user():
    """Return the current User ORM object or None."""
    if 'username' not in session:
        return None
    return User.query.filter_by(username=session['username']).first()


def save_user(user):
    db.session.commit()


# ── Graph/session state (per-user, per-session, not global) ────────────────
# These are kept in the Flask session (client-side cookie) so each browser
# tab/user gets independent state.

def get_session_graph_time():
    return session.get('graph_time', '1M')

def get_session_selector():
    return session.get('selector', 'CLOSE')

def get_session_graphs():
    return session.get('graphs', [])

def get_session_is_candle():
    return session.get('is_candle', False)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def ind():
    return render_template('login.html', headings=[])


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username already taken. Please choose another.')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(
            username=username,
            password_hash=hashed_password,
            curr_stocks={},
            stocks_bought=[],
            stocks_sold=[],
            curr_balance=100000.00,
            state_watch='<a href="#">Empty !</a>',
            curr_states=[]
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! Please login.')
        return redirect(url_for('ind'))
    return render_template('register.html')


@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        session['user_id'] = user.id
        session['username'] = user.username
        # Reset per-session graph state on login
        session['graph_time'] = '1M'
        session['selector'] = 'CLOSE'
        session['graphs'] = []
        session['is_candle'] = False
        return redirect(url_for('main'))
    else:
        flash('Invalid username or password')
        return redirect(url_for('ind'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('ind'))


@app.route('/main')
def main():
    user = get_user()
    if not user:
        return redirect(url_for('ind'))
    session['graphs'] = []
    session['graph_time'] = '1M'
    session['selector'] = 'CLOSE'
    data = {
        "NIFTY 50": fetch_live_data_stock("ASIANPAINT"),
        "TCS": fetch_live_data_stock("TCS"),
        "SBIN": fetch_live_data_stock("SBIN"),
    }
    return render_template(
        'main.html',
        data=data, int=round,
        all=all_stocks_names,
        stocks_bought=user.stocks_bought or [],
        all_stocks=all_stocks,
        bal=user.curr_balance,
        stocks_sold=user.stocks_sold or [],
        curr_stocks=user.curr_stocks or {},
        f=fetch_live_data_stock,
        curr=user.curr_states or [],
        user=session['username']
    )


@app.route('/allindexes')
def allindexes():
    user = get_user()
    if not user:
        return redirect(url_for('ind'))
    session['graphs'] = []
    session['graph_time'] = '1M'
    session['selector'] = 'CLOSE'
    return render_template(
        'allindices.html',
        all_stocks=all_stocks,
        f=fetch_live_data_stock,
        all=all_stocks_names[:20],
        curr=user.curr_states or [],
        performance=performance,
        user=session['username']
    )


@app.route('/watchlist')
def watchlist():
    user = get_user()
    if not user:
        return redirect(url_for('ind'))
    return render_template('watchlist.html', state_watch=user.state_watch)


@app.route('/update_watch', methods=['POST'])
def update_watch():
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    curr_states = list(user.curr_states or [])
    new_state = request.form.get('new_state', None)
    f = request.form.get('st', None)
    if f is None:
        st1 = request.form.get('st1', None)
        if st1 in curr_states:
            curr_states.remove(st1)
    else:
        curr_states.append(f)
    user.state_watch = new_state
    user.curr_states = curr_states
    save_user(user)
    return jsonify({"status": "success"})


@app.route('/clear_watchlist', methods=['POST'])
def clear_watchlist():
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    user.state_watch = '<a href="#">Empty !</a>'
    user.curr_states = []
    save_user(user)
    return jsonify({'status': 'success'})


@app.route('/update_graph_time', methods=['POST'])
def update_month():
    session['graph_time'] = request.form.get('time', '1M')
    return jsonify({"status": "success"})


@app.route('/update_graph', methods=['POST'])
def update_graph():
    graphs = get_session_graphs()
    st = request.form.get('st', None)
    if st:
        graphs.append(all_stocks.loc[st]['Symbol'])
        session['graphs'] = graphs
    return jsonify({"status": "success"})


@app.route('/update_candle', methods=['POST'])
def update_candle():
    session['is_candle'] = not get_session_is_candle()
    return jsonify({"status": "success"})


@app.route('/link_stock_graph', methods=['POST'])
def link():
    st = all_stocks.loc[request.form.get('st', None)]['Symbol']
    session['graphs'] = []
    session['selector'] = 'CLOSE'
    session['graph_time'] = '1Y'
    return jsonify(st)


@app.route('/selector', methods=['POST'])
def select():
    session['selector'] = request.form.get('select', 'CLOSE')
    return jsonify({"status": "success"})


@app.route('/update_buy', methods=['POST'])
def update_buy():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    a = request.form.get('st', None)
    b = request.form.get('pr', None)
    c = request.form.get('q', None)
    d = datetime.now(tz=IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    cost = float(b) * float(c)
    curr_balance = user.curr_balance
    if curr_balance - cost < 0:
        return jsonify({"status": "error", "reason": "insufficient_balance",
                        "balance": round(curr_balance, 2), "cost": round(cost, 2)})
    curr_balance -= cost
    stocks_bought = list(user.stocks_bought or [])
    stocks_bought.append([a, b, c, d])
    curr_stocks = dict(user.curr_stocks or {})
    if a in curr_stocks:
        curr_stocks[a] += int(c)
    else:
        curr_stocks[a] = int(c)
    user.curr_balance = curr_balance
    user.stocks_bought = stocks_bought
    user.curr_stocks = curr_stocks
    save_user(user)
    return jsonify({"status": "success", "balance": round(curr_balance, 2)})


@app.route('/update_sell', methods=['POST'])
def update_sell():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    a = request.form.get('st', None)
    b = request.form.get('pr', None)
    c = request.form.get('q', None)
    d = datetime.now(tz=IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    qty = int(c)
    curr_stocks = dict(user.curr_stocks or {})
    owned = curr_stocks.get(a, 0)
    if qty > owned:
        return jsonify({"status": "error", "reason": "insufficient_shares",
                        "owned": owned, "requested": qty})
    curr_balance = user.curr_balance + float(b) * qty
    stocks_sold = list(user.stocks_sold or [])
    stocks_sold.append([a, b, c, d])
    curr_stocks[a] -= qty
    if curr_stocks[a] <= 0:
        del curr_stocks[a]
    user.curr_balance = curr_balance
    user.stocks_sold = stocks_sold
    user.curr_stocks = curr_stocks
    save_user(user)
    return jsonify({"status": "success", "balance": round(curr_balance, 2)})


@app.route('/update_balance', methods=['POST'])
def update_balance():
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    user.curr_balance = float(request.form.get('balance', 0))
    save_user(user)
    return jsonify({"status": "success"})


@app.route('/reset_balance', methods=['POST'])
def reset_balance():
    user = get_user()
    if not user:
        return jsonify({"status": "error"}), 401
    user.curr_balance = 100000.00
    user.curr_stocks = {}
    user.stocks_bought = []
    user.stocks_sold = []
    save_user(user)
    return jsonify({"status": "success", "balance": 100000.00})


@app.route('/update_performance', methods=['POST'])
def update_performance():
    global all_stocks, performance, all_stocks_names
    all_stocks['live'] = [fetch_live_data_stock(sym)['lastPrice'] for sym in all_stocks['Symbol']]
    all_stocks['close'] = [fetch_live_data_stock(sym)['previousClose'] for sym in all_stocks['Symbol']]
    all_stocks['perform'] = 100 * (all_stocks['live'] - all_stocks['close']) / all_stocks['close']
    all_stocks_names = all_stocks.sort_values(by='perform', ascending=True).index.tolist()
    return jsonify(performance)


@app.route('/allindexes/<symbol>')
def graph(symbol):
    user = get_user()
    if not user:
        return redirect(url_for('ind'))
    curr_states = user.curr_states or []
    iswatch = (all_stocks.index[all_stocks['Symbol'] == symbol][0]) in curr_states
    try:
        live_info = fetch_live_data_stock(symbol)
    except Exception:
        live_info = MOCK_PRICE_INFO
    w52_high = live_info.get('weekHighLow', {}).get('max', 'N/A')
    w52_low = live_info.get('weekHighLow', {}).get('min', 'N/A')
    return render_template(
        'eachstock.html',
        script='', div='',
        symbol=symbol,
        all=all_stocks_names,
        is_candle=get_session_is_candle(),
        gt=get_session_graph_time(),
        all_stocks=all_stocks,
        iswatch=iswatch,
        f=fetch_live_data_stock,
        live=live_info,
        int=round,
        w52_high=w52_high,
        w52_low=w52_low,
        curr_balance=user.curr_balance,
        curr_stocks=user.curr_stocks or {},
        user=session['username']
    )


@app.route('/get_chart_data/<symbol>')
def get_chart_data(symbol):
    """Fetch NSE historical OHLCV via yfinance and return Chart.js-friendly JSON."""
    import time as _time

    graph_time = get_session_graph_time()
    selector = get_session_selector()
    graphs = get_session_graphs()
    is_candle = get_session_is_candle()

    print(f"\n[chart] ========== NEW REQUEST ==========")
    print(f"[chart] symbol={symbol} | graph_time={graph_time} | selector={selector} | is_candle={is_candle} | graphs={graphs}")

    if not hasattr(app, '_chart_cache'):
        app._chart_cache = {}
    cache_key = f"{symbol}|{graph_time}|{selector}|{is_candle}|{'|'.join(graphs)}"
    cached = app._chart_cache.get(cache_key)
    if cached and (_time.time() - cached['ts']) < 300:
        print(f"[chart] Cache HIT for key: {cache_key}")
        return jsonify(cached['data'])
    print(f"[chart] Cache MISS – fetching fresh data")

    period_map = {
        '1D': '5d',
        '1W': '5d',
        '1M': '1mo',
        '1Y': '1y',
        '5Y': '5y',
    }
    yf_period = period_map.get(graph_time, '1mo')

    yf_col_map = {
        'CLOSE': 'Close',
        'OPEN': 'Open',
        'VOLUME': 'Volume',
        '52W H': 'High',
        '52W L': 'Low',
    }
    line_col = yf_col_map.get(selector, 'Close')

    syms = graphs if graphs else [symbol]
    result = {'type': 'line' if not is_candle else 'candle', 'series': []}

    for sym in syms:
        yf_ticker = sym + '.NS'
        raw = None

        # Tier 1: yf.download()
        try:
            raw = yf.download(yf_ticker, period=yf_period, progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            if raw is None or raw.empty:
                raw = None
        except Exception as e1:
            print(f"[chart] Tier1 failed: {e1}")
            raw = None

        # Tier 2: yf.Ticker().history()
        if raw is None or raw.empty:
            try:
                raw = yf.Ticker(yf_ticker).history(period=yf_period)
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                if raw is None or raw.empty:
                    raw = None
            except Exception as e2:
                print(f"[chart] Tier2 failed: {e2}")
                raw = None

        # Tier 3: NSE historical API via Live_Market session
        if raw is None or raw.empty:
            from datetime import date as _date, timedelta
            jugaad_period_map = {'5d': 5, '1mo': 30, '1y': 365, '5y': 5 * 365}
            days_back = jugaad_period_map.get(yf_period, 30)
            today_d = _date.today()
            from_d = today_d - timedelta(days=days_back)
            from_str = from_d.strftime('%d-%m-%Y')
            to_str = today_d.strftime('%d-%m-%Y')
            nse_url = (
                f'https://www.nseindia.com/api/historical/cm/equity'
                f'?symbol={sym}&series=[%22EQ%22]&from={from_str}&to={to_str}'
            )
            try:
                resp = Live_Market.s.get(nse_url, timeout=10)
                resp_json = resp.json()
                records = resp_json.get('data', [])
                if records:
                    nse_df = pd.DataFrame(records).sort_values('CH_TIMESTAMP')
                    raw = pd.DataFrame({
                        'Open': pd.to_numeric(nse_df['CH_OPENING_PRICE'], errors='coerce'),
                        'High': pd.to_numeric(nse_df.get('CH_TRADE_HIGH_PRICE', nse_df['CH_OPENING_PRICE']), errors='coerce'),
                        'Low': pd.to_numeric(nse_df.get('CH_TRADE_LOW_PRICE', nse_df['CH_OPENING_PRICE']), errors='coerce'),
                        'Close': pd.to_numeric(nse_df['CH_CLOSING_PRICE'], errors='coerce'),
                        'Volume': pd.to_numeric(nse_df.get('CH_TOT_TRADED_QTY', 0), errors='coerce'),
                    }, index=pd.to_datetime(nse_df['CH_TIMESTAMP']))
                else:
                    raw = None
            except Exception as e3:
                print(f"[chart] Tier3 failed: {e3}")
                raw = None

        if raw is None or raw.empty:
            result['series'].append({'symbol': sym, 'error': 'no_data'})
            continue

        try:
            if graph_time == '1D':
                raw = raw.tail(1)
            timestamps = raw.index.strftime('%Y-%m-%d').tolist()
            o = raw['Open'].tolist()
            h = raw['High'].tolist()
            l = raw['Low'].tolist()
            c_vals = raw['Close'].tolist()
            v = raw['Volume'].tolist() if 'Volume' in raw.columns else []
            line_values = raw[line_col].tolist() if line_col in raw.columns else c_vals
            result['series'].append({
                'symbol': sym,
                'labels': timestamps,
                'open': o, 'high': h, 'low': l, 'close': c_vals,
                'volume': v, 'line_values': line_values,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            result['series'].append({'symbol': sym, 'error': str(e)})

    good_series = [s for s in result['series'] if 'labels' in s]
    if not good_series:
        return jsonify({'error': 'No data available for this symbol. NSE may be closed or the symbol is invalid.'})

    app._chart_cache[cache_key] = {'data': result, 'ts': _time.time()}
    return jsonify(result)


@app.route('/api/live_prices', methods=['GET'])
def api_live_prices():
    """Return latest live prices for a comma-separated list of symbols."""
    symbols = request.args.get('symbols', '')
    result = {}
    for sym in [s.strip() for s in symbols.split(',') if s.strip()]:
        data = fetch_live_data_stock(sym)
        result[sym] = {
            'lastPrice': data.get('lastPrice', 'N/A'),
            'change': data.get('change', 0),
            'pChange': data.get('pChange', 0),
            'high': data.get('intraDayHighLow', {}).get('max', 'N/A'),
            'low': data.get('intraDayHighLow', {}).get('min', 'N/A'),
            'open': data.get('open', 'N/A'),
            'prevClose': data.get('previousClose', 'N/A'),
        }
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=3001)
