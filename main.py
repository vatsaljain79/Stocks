from flask import Flask, render_template, request, redirect, url_for, flash, session,jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from jugaad_data.nse import stock_df
from jugaad_data.nse import NSELive
from sqlalchemy.dialects.postgresql import JSON
import decimal
import pandas as pd
from datetime import date
import time,random
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

def fetch_live_data_stock(symbol):
    return Live_Market.stock_quote(symbol)['priceInfo']
# print(fetch_live_data_stock("TCS"))
c=0
headings=[]
graphs=[]
curr_stocks={}
stocks_bought=[]
stocks_sold=[]
curr_balance=100000.00
graph_time='1Y'
selector='CLOSE'
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
    graph_time='1Y'
    selector='CLOSE'
    data={"NIFTY 50":fetch_live_data_stock("ASIANPAINT"),"TCS":fetch_live_data_stock("TCS"),"SBIN":fetch_live_data_stock("SBIN")}
    return render_template('main.html',data=data,int=round,all=all_stocks_names,stocks_bought=stocks_bought,all_stocks=all_stocks,bal=curr_balance,stocks_sold=stocks_sold,curr_stocks=curr_stocks,f=fetch_live_data_stock,curr=curr_states,user=session['username'])

@app.route('/allindexes')
def allindexes():
    global all_stocks_names,graphs,selector,graph_time
    graphs=[]
    graph_time='1Y'
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
    from datetime import datetime
    global stocks_bought,curr_balance,curr_stocks
    a=request.form.get('st',None)
    b=request.form.get('pr',None)
    c=request.form.get('q',None)
    d=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    curr_balance-=(float(b)*float(c))
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
    return jsonify({"status": "success"})


@app.route('/update_sell',methods=['POST'])
def update_sell():
    from datetime import datetime
    global stocks_bought,curr_balance,curr_stocks
    a=request.form.get('st',None)
    b=request.form.get('pr',None)
    c=request.form.get('q',None)
    d=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    curr_balance+=(float(b)*float(c))
    stocks_sold.append([a,b,c,d])
    curr_stocks[a]-=int(c)
    if curr_stocks[a]<=0:
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
    return jsonify({"status": "success"})


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
    from bokeh.plotting import figure, output_file, show
    from bokeh.models import HoverTool,ColumnDataSource,Range1d
    from bokeh.plotting import figure
    from bokeh.resources import CDN
    from bokeh.embed import components
    from datetime import date
    from datetime import datetime,timedelta
    stock_data=[]
    global selector
    colors = ["blue", "green", "red", "purple", "orange"]
    lab={'CLOSE':"Closing Price",'OPEN':"Opening Price",'VOLUME':"Volume of Stocks",'52W H':"52 Week High",'52W L':"52 Week Low"}
    print(graph_time,"HI")
    p = figure(title=symbol+ " Stock Price", x_axis_label="Date", y_axis_label=lab[selector], x_axis_type='datetime',width=850,height=450)
    overall_min_date = None
    if len(graphs)==0:
        graphs.append(symbol)
    
    for i,sym in enumerate(graphs):
        if graph_time=="1Y":
            stock_data = stock_df(symbol=sym,from_date=date(date.today().year-1,date.today().month,date.today().day),to_date=date.today(),series="EQ")
        elif graph_time=="1M":
            stock_data = stock_df(symbol=sym,from_date=date.today()-timedelta(days=30),to_date=date.today(),series="EQ")
        elif graph_time=="5Y":
            stock_data = stock_df(symbol=sym,from_date=date(date.today().year-5,date.today().month,date.today().day),to_date=date.today(),series="EQ")
        elif graph_time=="1W":
            stock_data = stock_df(symbol=sym,from_date=date.today()-timedelta(days=7)  ,to_date=date.today(),series="EQ")
        elif graph_time=="1D":
            # For 1 day, request data from yesterday to today (daily series)
            stock_data = stock_df(symbol=sym, from_date=date.today()-timedelta(days=1), to_date=date.today(), series="EQ")
        else:
            # fallback to 1Y if an unknown graph_time is set
            stock_data = stock_df(symbol=sym,from_date=date(date.today().year-1,date.today().month,date.today().day),to_date=date.today(),series="EQ")
        # stock_df can sometimes return a list (or dict) instead of a DataFrame.
        # Normalize the result to a pandas DataFrame and ensure the date column
        # is a datetime index. Preserve a 'DATE' column for candlestick plotting.
        if isinstance(stock_data, list):
            if len(stock_data) == 0:
                # no data for this symbol/time-range, skip plotting it
                continue
            stock_data = pd.DataFrame(stock_data)
        elif isinstance(stock_data, dict):
            stock_data = pd.DataFrame([stock_data])

        # If still not a DataFrame (unexpected), skip
        if not hasattr(stock_data, 'columns'):
            continue

        # Normalize column names to uppercase for consistent access
        stock_data.columns = [c.upper() for c in stock_data.columns]

        # Choose the date column: prefer 'DATE' if present, otherwise first column
        date_col = 'DATE' if 'DATE' in stock_data.columns else stock_data.columns[0]

        # Convert to datetime and set index
        try:
            stock_data[date_col] = pd.to_datetime(stock_data[date_col])
        except Exception:
            # If conversion fails, skip this dataset
            continue

        stock_data.set_index(date_col, inplace=True)
        # keep a column with datetime values for bokeh's ColumnDataSource used in candles
        stock_data['DATE'] = stock_data.index
        # defensive: drop any rows whose DATE (calendar date) is after today's date
        try:
            # ensure DATE is datetime and data is sorted
            stock_data['DATE'] = pd.to_datetime(stock_data['DATE'])
            stock_data.sort_index(inplace=True)
            now_ts = pd.Timestamp.now()
            # compare full timestamps to ensure rows after 'now' are removed
            mask = stock_data['DATE'] <= now_ts
            dropped = int((~mask).sum())
            if dropped > 0:
                print(f"Dropping {dropped} future rows for {sym} (last index before drop: {stock_data.index.max()})")
            stock_data = stock_data.loc[mask]
            if stock_data.shape[0] == 0:
                continue
            # enforce x-axis not to extend into future
            # enforce x-axis not to extend into future (use p.x_range.end)
            try:
                p.x_range.end = now_ts.to_pydatetime()
            except Exception:
                # ignore if Bokeh doesn't accept direct datetime here
                pass
        except Exception as e:
            print("Warning while filtering future dates:", e)
            pass
        # print(stock_data)
        # print(selector)
        
        if not is_candle:
            p.line(stock_data.index, stock_data[selector], line_width=2, line_color=colors[i%len(colors)], legend_label=sym)
            try:
                this_min = stock_data.index.min()
                if overall_min_date is None or this_min < overall_min_date:
                    overall_min_date = this_min
            except Exception:
                pass
            hover = HoverTool()
            hover.tooltips = [("Date", "@x{%F}"),("Week", "@x{%A}"),("Month", "@x{%B}"), ("Closing Price", "@y{0.00}")]
            hover.formatters = {'@x': 'datetime'}
            p.add_tools(hover)

        else:
            # Ensure we reference uppercase column names
            stock_data['color'] = ['red' if open_val > close_val else 'rgb(5,173,117)' for open_val, close_val in zip(stock_data['OPEN'], stock_data['CLOSE'])]
            # Avoid a conflict where the DataFrame index has the same name as a
            # column (e.g. 'DATE'). ColumnDataSource will try to insert the
            # index using its name which raises ValueError if that column
            # already exists. Clear the index name in that case.
            if stock_data.index.name and stock_data.index.name in stock_data.columns:
                stock_data.index.name = None
            source = ColumnDataSource(stock_data)
            try:
                this_min = stock_data.index.min()
                if overall_min_date is None or this_min < overall_min_date:
                    overall_min_date = this_min
            except Exception:
                pass
            p.segment(x0='DATE', y0='HIGH', x1='DATE', y1='LOW', line_color="color", source=source)
            # choose vbar width based on resolution (ms). For intraday intervals
            # smaller widths are required; default to ~12 hours for daily view.
            width_ms = 24*60*60*1000 // 2  # default half-day width
            # Use a reasonable fixed width for daily candles
            width_ms = int(24*60*60*1000 * 0.5)
            vbar=p.vbar(x='DATE', width=width_ms, top='OPEN', bottom='CLOSE', fill_color="color",line_color='color', source=source)
            hover = HoverTool(renderers=[vbar], tooltips=[
                ("Date", "@DATE{%F}"),
                ("Open", "@OPEN{0.00}"),
                ("High", "@HIGH{0.00}"),
                ("Low", "@LOW{0.00}"),
                ("Close", "@CLOSE{0.00}")
            ], formatters={'@DATE': 'datetime'}, mode='vline')
            p.add_tools(hover)


    p.xaxis.major_label_orientation = 45
    # clamp x-axis to not extend into the future
    try:
        if overall_min_date is not None:
            p.x_range = Range1d(start=overall_min_date.to_pydatetime(), end=pd.Timestamp.now().to_pydatetime())
    except Exception:
        pass
    p.grid.grid_line_alpha = 0.3

    p.legend.location = "top_left"
    p.legend.click_policy="hide"

    script, div = components(p, CDN,"3.3.3")
    global all_stocks_names
    global iswatch,fetch_live_data_stock
    # print(state_watch,all_stocks.index[all_stocks['Symbol'] == symbol][0])
    if (all_stocks.index[all_stocks['Symbol'] == symbol][0]) in curr_states:
        iswatch=True
    else:
        iswatch=False
    # print(iswatch)
    # print(symbol)
    w52_high_low=stock_df(symbol=symbol,from_date=date.today()-timedelta(days=1),to_date=date.today(),series="EQ")
    
    return render_template('eachstock.html', script=script, div=div,symbol=symbol,all=all_stocks_names,is_candle=is_candle,gt=graph_time,all_stocks=all_stocks,iswatch=iswatch,f=fetch_live_data_stock,int=round,w52=w52_high_low,curr_balance=curr_balance,user=session['username'])
    
if __name__ == '__main__':
    app.run(debug=True,port=3001)
