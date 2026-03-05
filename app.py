from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from jugaad_data.nse import NSELive, stock_df as jugaad_stock_df
from sqlalchemy.dialects.postgresql import JSON
import decimal
import pandas as pd
from datetime import date
import time,random
import os, requests as http_requests
import yfinance as yf
from dotenv import load_dotenv
load_dotenv()  # loads FINNHUB_API_KEY from .env
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY', '')
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your actual secret key   
all_stocks=pd.read_csv('ind_nifty50list.csv',index_col=0)
all_stocks=all_stocks.drop(['Industry','Series','ISIN Code'],axis=1)

all_stocks_names=all_stocks.index.tolist()
performance=[]


app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
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
    state_watch=db.Column(db.String(255))
    curr_states = db.Column(db.PickleType)

with app.app_context():
    db.create_all()
    
def fetch_live_data_index(symbol):
    return Live_Market.live_index(symbol)['marketStatus']

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
c=0
headings=[]
graphs=[]
curr_stocks={}
stocks_bought=[]
stocks_sold=[]
curr_balance=100000.00
graph_time='1M'
selector='CLOSE'
is_candle=False
state_watch='<a href="#">Empty !</a>'
curr_states=[]

@app.route('/')
def ind():
    return render_template('login.html',headings=headings)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        new_user = User(username=username, password_hash=hashed_password,curr_stocks={},stocks_bought=[],stocks_sold=[],curr_balance=100000.00,state_watch='<a href="#">Empty !</a>',curr_states=[])
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
        user = User.query.filter_by(username=session['username']).first()
        global curr_stocks,stocks_bought,stocks_sold,curr_balance,state_watch,curr_states
        curr_stocks=user.curr_stocks
        stocks_bought=user.stocks_bought
        stocks_sold=user.stocks_sold
        curr_balance=user.curr_balance
        state_watch=user.state_watch
        curr_states=user.curr_states
        return redirect(url_for('main'))
    else:
        flash('Invalid username or password')
        return redirect(url_for('ind'))
    
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    return redirect(url_for('ind'))

@app.route('/main')
def main():
    global headings
    global c
    global graphs,selector,graph_time,curr_balance,fetch_live_data_stock,curr_states
    graphs=[]
    graph_time='1M'
    selector='CLOSE'
    data={"NIFTY 50":fetch_live_data_stock("ASIANPAINT"),"TCS":fetch_live_data_stock("TCS"),"SBIN":fetch_live_data_stock("SBIN")}
    return render_template('main.html',data=data,int=round,all=all_stocks_names,stocks_bought=stocks_bought,all_stocks=all_stocks,bal=curr_balance,stocks_sold=stocks_sold,curr_stocks=curr_stocks,f=fetch_live_data_stock,curr=curr_states,user=session['username'])

@app.route('/allindexes')
def allindexes():
    global all_stocks_names,graphs,selector,graph_time
    graphs=[]
    graph_time='1M'
    selector='CLOSE'

    global fetch_live_data_stock,curr_states
    return render_template('allindices.html',all_stocks=all_stocks,f=fetch_live_data_stock,all=all_stocks_names[:20],curr=curr_states,performance=performance,user=session['username'])

@app.route('/watchlist')
def watchlist():
    return render_template('watchlist.html',state_watch=state_watch)

@app.route('/update_watch',methods=['POST'])
def update_watch():
    global state_watch,curr_states
    new_state=request.form.get('new_state',None)
    f=request.form.get('st',None)
    if f==None:
        curr_states.remove(request.form.get('st1',None))
    else:
        curr_states.append(request.form.get('st',None))
    state_watch=new_state

    user = User.query.filter_by(username=session['username']).first()

    user.curr_stocks=curr_stocks
    user.stocks_bought=stocks_bought
    user.stocks_sold=stocks_sold
    user.curr_balance=curr_balance
    user.state_watch=state_watch
    user.curr_states=curr_states
    db.session.commit()
    return jsonify({"status": "success"})



@app.route('/clear_watchlist', methods=['POST'])
def clear_watchlist():
    global state_watch, curr_states
    state_watch = '<a href="#">Empty !</a>'
    curr_states = []
    user = User.query.filter_by(username=session['username']).first()
    user.state_watch = state_watch
    user.curr_states = curr_states
    db.session.commit()
    return jsonify({'status': 'success'})


@app.route('/update_graph_time',methods=['POST'])
def update_month():
    
    global graph_time
    graph_time=request.form.get('time',None)

    return jsonify({"status": "success"})


# resolution feature removed

@app.route('/update_graph',methods=['POST'])
def update_graph():
    
    global graphs
    graphs.append(all_stocks.loc[request.form.get('st',None)]['Symbol'])

    return jsonify({"status": "success"})

is_candle=False

@app.route('/update_candle',methods=['POST'])
def update_candle():
    
    global is_candle
    is_candle=not is_candle

    return jsonify({"status": "success"})
iswatch=False

@app.route('/link_stock_graph',methods=['POST'])
def link():
    st=all_stocks.loc[request.form.get('st',None)]['Symbol']
    global graphs,selector,graph_time
    graphs=[]
    selector='CLOSE'
    graph_time='1Y'
    return jsonify(st)

@app.route('/selector',methods=['POST'])
def select():
    global selector
    selector=request.form.get('select',None)
    return jsonify({"status": "success"})

@app.route('/update_buy',methods=['POST'])
def update_buy():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    global stocks_bought,curr_balance,curr_stocks
    a=request.form.get('st',None)
    b=request.form.get('pr',None)
    c=request.form.get('q',None)
    d=datetime.now(tz=IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    cost = float(b) * float(c)
    # Reject if balance would go negative
    if curr_balance - cost < 0:
        return jsonify({"status": "error", "reason": "insufficient_balance",
                        "balance": round(curr_balance, 2), "cost": round(cost, 2)})
    curr_balance -= cost
    stocks_bought.append([a,b,c,d])
    if a in curr_stocks:
        curr_stocks[a]+=int(c)
    else:
        curr_stocks[a]=int(c)
    print(stocks_bought)

    user = User.query.filter_by(username=session['username']).first()
    user.curr_stocks=curr_stocks
    user.stocks_bought=stocks_bought
    user.stocks_sold=stocks_sold
    user.curr_balance=curr_balance
    user.state_watch=state_watch
    user.curr_states=curr_states
    db.session.commit()
    return jsonify({"status": "success", "balance": round(curr_balance, 2)})


@app.route('/update_sell',methods=['POST'])
def update_sell():
    from datetime import datetime, timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))
    global stocks_bought,curr_balance,curr_stocks
    a=request.form.get('st',None)
    b=request.form.get('pr',None)
    c=request.form.get('q',None)
    d=datetime.now(tz=IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    qty = int(c)
    owned = curr_stocks.get(a, 0)
    # Reject short-sells
    if qty > owned:
        return jsonify({"status": "error", "reason": "insufficient_shares",
                        "owned": owned, "requested": qty})
    curr_balance += float(b) * qty
    stocks_sold.append([a,b,c,d])
    curr_stocks[a] -= qty
    if curr_stocks[a] <= 0:
        del curr_stocks[a]
    print(stocks_bought)

    user = User.query.filter_by(username=session['username']).first()
    user.curr_stocks=curr_stocks
    user.stocks_bought=stocks_bought
    user.stocks_sold=stocks_sold
    user.curr_balance=curr_balance
    user.state_watch=state_watch
    user.curr_states=curr_states
    db.session.commit()
    return jsonify({"status": "success", "balance": round(curr_balance, 2)})


@app.route('/update_balance',methods=['POST'])
def update_balance():
    global curr_balance
    curr_balance=float(request.form.get('balance',None))
    print(curr_balance)

    user = User.query.filter_by(username=session['username']).first()

    user.curr_stocks=curr_stocks
    user.stocks_bought=stocks_bought
    user.stocks_sold=stocks_sold
    user.curr_balance=curr_balance
    user.state_watch=state_watch
    user.curr_states=curr_states
    db.session.commit()
    return jsonify({"status": "success"})

@app.route('/reset_balance', methods=['POST'])
def reset_balance():
    global curr_balance, curr_stocks, stocks_bought, stocks_sold
    curr_balance  = 100000.00
    curr_stocks   = {}
    stocks_bought = []
    stocks_sold   = []

    user = User.query.filter_by(username=session['username']).first()
    user.curr_stocks   = curr_stocks
    user.stocks_bought = stocks_bought
    user.stocks_sold   = stocks_sold
    user.curr_balance  = curr_balance
    user.state_watch   = state_watch
    user.curr_states   = curr_states
    db.session.commit()
    return jsonify({"status": "success", "balance": curr_balance})

@app.route('/update_performance',methods=['POST'])
def update_performance():
    global all_stocks,performance,all_stocks_names
    all_stocks['live']=[fetch_live_data_stock(sym)['lastPrice'] for sym in all_stocks['Symbol']]
    all_stocks['close']=[fetch_live_data_stock(sym)['previousClose'] for sym in all_stocks['Symbol']]
    all_stocks['perform']=100*(all_stocks['live']-all_stocks['close'])/all_stocks['close']
    all_stocks_names=all_stocks.sort_values(by='perform', ascending=True).index.tolist()
    return jsonify(performance)


@app.route('/allindexes/<symbol>')
def graph(symbol):
    # ── Fast path: render the page shell immediately ──────────────────────────
    # Chart data is fetched asynchronously via /get_chart_data/<symbol>
    global all_stocks_names, iswatch, fetch_live_data_stock

    if (all_stocks.index[all_stocks['Symbol'] == symbol][0]) in curr_states:
        iswatch = True
    else:
        iswatch = False

    try:
        live_info = fetch_live_data_stock(symbol)
    except Exception:
        live_info = MOCK_PRICE_INFO

    w52_high = live_info.get('weekHighLow', {}).get('max', 'N/A')
    w52_low  = live_info.get('weekHighLow', {}).get('min', 'N/A')

    return render_template('eachstock.html',
        script='', div='',
        symbol=symbol,
        all=all_stocks_names,
        is_candle=is_candle,
        gt=graph_time,
        all_stocks=all_stocks,
        iswatch=iswatch,
        f=fetch_live_data_stock,
        live=live_info,
        int=round,
        w52_high=w52_high,
        w52_low=w52_low,
        curr_balance=curr_balance,
        curr_stocks=curr_stocks,
        user=session['username'])


@app.route('/api/finnhub_key')
def finnhub_key():
    """Expose the Finnhub API key to the frontend (for WebSocket use only)."""
    return jsonify({'key': FINNHUB_API_KEY})


@app.route('/get_chart_data/<symbol>')
def get_chart_data(symbol):
    """Fetch NSE historical OHLCV via yfinance and return Chart.js-friendly JSON.
    jugaad-data (NSELive) handles the live price ticker separately.
    """
    import time as _time

    global selector, graphs, graph_time, is_candle
    print(f"\n[chart] ========== NEW REQUEST ==========")
    print(f"[chart] ▶ symbol={symbol} | graph_time={graph_time} | selector={selector} | is_candle={is_candle} | graphs={graphs}")

    # ── In-memory cache (5 min) ───────────────────────────────────────────────
    if not hasattr(app, '_chart_cache'):
        app._chart_cache = {}
    cache_key = f"{symbol}|{graph_time}|{selector}|{is_candle}|{'|'.join(graphs)}"
    cached = app._chart_cache.get(cache_key)
    if cached and (_time.time() - cached['ts']) < 300:
        print(f"[chart] ✅ Cache HIT for key: {cache_key}")
        return jsonify(cached['data'])
    print(f"[chart] ❌ Cache MISS – fetching fresh data from yfinance")

    # ── Period mapping for yfinance Ticker.history() ─────────────────────────
    # .history(period=...) is the recommended, reliable approach for NSE stocks.
    # Period strings: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    period_map = {
        '1D': '5d',    # 5 days so we always get at least 1 trading day; trimmed below
        '1W': '5d',
        '1M': '1mo',
        '1Y': '1y',
        '5Y': '5y',
    }
    yf_period = period_map.get(graph_time, '1mo')
    print(f"[chart] graph_time='{graph_time}'  →  yfinance period='{yf_period}'")

    # ── yfinance column → selector mapping ───────────────────────────────────
    yf_col_map = {
        'CLOSE':  'Close',
        'OPEN':   'Open',
        'VOLUME': 'Volume',
        '52W H':  'High',
        '52W L':  'Low',
    }
    line_col = yf_col_map.get(selector, 'Close')
    print(f"[chart] selector='{selector}'  →  yfinance column='{line_col}'")

    syms = graphs if graphs else [symbol]
    print(f"[chart] Symbols to fetch: {syms}")
    result = {'type': 'line' if not is_candle else 'candle', 'series': []}

    for sym in syms:
        yf_ticker = sym + '.NS'
        print(f"\n[chart]  ── Fetching {sym}  (yfinance ticker: {yf_ticker}) ──")
        raw = None

        # ── Tier 1: yf.download() with period string (fastest) ───────────────
        try:
            print(f"[chart]  [Tier 1] yf.download('{yf_ticker}', period='{yf_period}', progress=False) ...")
            raw = yf.download(yf_ticker, period=yf_period, progress=False, auto_adjust=True)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            if raw is not None and not raw.empty:
                print(f"[chart]  [Tier 1] ✅ Got {len(raw)} rows. Columns: {list(raw.columns)}")
            else:
                print(f"[chart]  [Tier 1] ❌ Empty result (shape={raw.shape}). Trying Tier 2 …")
                raw = None
        except Exception as e1:
            print(f"[chart]  [Tier 1] ❌ Exception: {e1}")
            raw = None

        # ── Tier 2: yf.Ticker().history() ────────────────────────────────────
        if raw is None or raw.empty:
            try:
                print(f"[chart]  [Tier 2] yf.Ticker('{yf_ticker}').history(period='{yf_period}') ...")
                raw = yf.Ticker(yf_ticker).history(period=yf_period)
                if isinstance(raw.columns, pd.MultiIndex):
                    raw.columns = raw.columns.get_level_values(0)
                if raw is not None and not raw.empty:
                    print(f"[chart]  [Tier 2] ✅ Got {len(raw)} rows. Columns: {list(raw.columns)}")
                else:
                    print(f"[chart]  [Tier 2] ❌ Empty result (shape={raw.shape}). Trying Tier 3 …")
                    raw = None
            except Exception as e2:
                print(f"[chart]  [Tier 2] ❌ Exception: {e2}")
                raw = None

        # ── Tier 3: Direct NSE historical API via Live_Market session ─────────
        # Live_Market.nsefetch() reuses the authenticated NSE cookie session
        # that already works for live quotes — bypasses the anti-scraping block.
        if raw is None or raw.empty:
            from datetime import date as _date, timedelta
            jugaad_period_map = {
                '5d':  5, '1mo': 30, '1y': 365, '5y': 5*365,
            }
            days_back = jugaad_period_map.get(yf_period, 30)
            today_d = _date.today()
            from_d  = today_d - timedelta(days=days_back)
            from_str = from_d.strftime('%d-%m-%Y')
            to_str   = today_d.strftime('%d-%m-%Y')
            # NSE historical equity endpoint (same format jugaad_data uses internally)
            nse_url = (
                f'https://www.nseindia.com/api/historical/cm/equity'
                f'?symbol={sym}&series=[%22EQ%22]&from={from_str}&to={to_str}'
            )
            try:
                print(f"[chart]  [Tier 3] NSE historical API via Live_Market.s session ...")
                print(f"[chart]  [Tier 3] URL: {nse_url}")
                # Live_Market.s is the authenticated requests.Session (has NSE cookies)
                resp    = Live_Market.s.get(nse_url, timeout=10)
                print(f"[chart]  [Tier 3] HTTP status: {resp.status_code}  |  Content-Type: {resp.headers.get('Content-Type','?')}")
                print(f"[chart]  [Tier 3] Response preview: {resp.text[:300]}")
                resp_json = resp.json()
                records   = resp_json.get('data', [])
                print(f"[chart]  [Tier 3] Response keys: {list(resp_json.keys())}  |  records: {len(records)}")
                if records:
                    nse_df = pd.DataFrame(records)
                    # Sort ascending by date
                    nse_df = nse_df.sort_values('CH_TIMESTAMP')
                    print(f"[chart]  [Tier 3] ✅ Got {len(nse_df)} rows. Columns: {list(nse_df.columns[:8])}")
                    raw = pd.DataFrame({
                        'Open':   pd.to_numeric(nse_df['CH_OPENING_PRICE'],   errors='coerce'),
                        'High':   pd.to_numeric(nse_df.get('CH_TRADE_HIGH_PRICE', nse_df['CH_OPENING_PRICE']), errors='coerce'),
                        'Low':    pd.to_numeric(nse_df.get('CH_TRADE_LOW_PRICE',  nse_df['CH_OPENING_PRICE']), errors='coerce'),
                        'Close':  pd.to_numeric(nse_df['CH_CLOSING_PRICE'],   errors='coerce'),
                        'Volume': pd.to_numeric(nse_df.get('CH_TOT_TRADED_QTY', 0), errors='coerce'),
                    }, index=pd.to_datetime(nse_df['CH_TIMESTAMP']))
                else:
                    print(f"[chart]  [Tier 3] ❌ NSE returned 0 records. Response: {str(resp_json)[:200]}")
                    raw = None
            except Exception as e3:
                import traceback
                print(f"[chart]  [Tier 3] ❌ Exception: {e3}")
                traceback.print_exc()
                raw = None

        # ── Final: build series or report error ──────────────────────────────
        if raw is None or raw.empty:
            print(f"[chart]  ❌ All 3 tiers failed for {sym}. Skipping.")
            result['series'].append({'symbol': sym, 'error': 'no_data'})
            continue

        try:
            # For 1D, keep only last row (= most recent trading day)
            if graph_time == '1D':
                print(f"[chart]  GraphTime=1D → trimming to last 1 row")
                raw = raw.tail(1)

            timestamps = raw.index.strftime('%Y-%m-%d').tolist()
            print(f"[chart]  Row count after trim: {len(raw)} | range: {timestamps[0]} … {timestamps[-1]}")

            o      = raw['Open'].tolist()
            h      = raw['High'].tolist()
            l      = raw['Low'].tolist()
            c_vals = raw['Close'].tolist()
            v      = raw['Volume'].tolist() if 'Volume' in raw.columns else []

            print(f"[chart]  Last bar OHLC: O={o[-1]:.2f}  H={h[-1]:.2f}  L={l[-1]:.2f}  C={c_vals[-1]:.2f}")

            if line_col in raw.columns:
                line_values = raw[line_col].tolist()
            else:
                print(f"[chart]  ⚠️  '{line_col}' not in columns {list(raw.columns)} – falling back to Close")
                line_values = c_vals

            result['series'].append({
                'symbol':      sym,
                'labels':      timestamps,
                'open':        o,
                'high':        h,
                'low':         l,
                'close':       c_vals,
                'volume':      v,
                'line_values': line_values,
            })
            print(f"[chart]  ✅ Series for {sym} assembled successfully.")

        except Exception as e:
            import traceback
            print(f"[chart]  ❌ EXCEPTION while assembling series for {sym}: {e}")
            traceback.print_exc()
            result['series'].append({'symbol': sym, 'error': str(e)})

    good_series = [s for s in result['series'] if 'labels' in s]
    print(f"\n[chart] ── FINAL RESULT ──")
    print(f"[chart] {len(good_series)}/{len(result['series'])} series have data. type='{result['type']}'")

    if not good_series:
        print(f"[chart] ❌ Returning error to frontend – no data at all.")
        return jsonify({'error': 'No data available for this symbol. NSE may be closed or the symbol is invalid.'})

    print(f"[chart] ✅ Caching and returning result.")
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
            'change':    data.get('change', 0),
            'pChange':   data.get('pChange', 0),
            'high':      data.get('intraDayHighLow', {}).get('max', 'N/A'),
            'low':       data.get('intraDayHighLow', {}).get('min', 'N/A'),
            'open':      data.get('open', 'N/A'),
            'prevClose': data.get('previousClose', 'N/A'),
        }
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True,port=3001)

