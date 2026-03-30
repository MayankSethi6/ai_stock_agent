import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Bulletproof Desk", layout="wide", page_icon="🏛️")

USD_INR_2026 = 87.50
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "RELIANCE": 250, "SBIN": 1500, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {
    'fund_balance': 1000000.0, 
    'balance_history': [1000000.0], 
    'portfolio': [], 
    'pnl_ledger': []
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. UTILITIES ---
def get_market_status():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    is_open = now.weekday() < 5 and time(9,15) <= now.time() <= time(15,30)
    return is_open, now.strftime("%H:%M:%S")

def universal_search(query):
    try:
        search = yf.Search(query, max_results=1)
        if search.quotes:
            q = search.quotes[0]
            tk = yf.Ticker(q['symbol'])
            # Defensive check for sector/currency
            return {
                "symbol": q['symbol'], 
                "name": q.get('shortname', q['symbol']),
                "sector": tk.info.get('sector', 'Uncategorized'),
                "currency": tk.info.get('currency', 'INR')
            }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Fund Assets")
    st.metric("Net Liquid Capital", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🗑️ Wipe & Reset Terminal"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        if "curr_trade" in st.session_state: del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Global Search", value="Reliance")
    asset = universal_search(user_query)
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        is_nse = ".NS" in asset['symbol']
        lot_size = NSE_LOTS.get(asset['symbol'].split(".")[0], 1) if is_nse else 1
        lots = st.number_input(f"Execution Size (Lots of {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run Manager Intel"):
            with st.spinner("AI Quant Analysis in Progress..."):
                tk = yf.Ticker(asset['symbol'])
                hist = tk.history(period="1d")
                if not hist.empty:
                    cp = float(hist['Close'].iloc[-1])
                    
                    # --- FIXED NEWS LOGIC ---
                    try:
                        raw_news = tk.news
                        headlines = [n.get('title', 'No Title') for n in raw_news[:3]] if raw_news else ["No recent news found."]
                    except Exception:
                        headlines = ["News currently unavailable from Yahoo Finance."]
                    
                    prompt = f"Hedge Fund Manager. Asset: {asset['name']} @ {cp}. News: {headlines}. Strategy?"
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    
                    st.session_state.curr_trade = {
                        "ticker": asset['symbol'], "name": asset['name'], "sector": asset['sector'],
                        "price": cp, "qty": lots * lot_size, "report": res.text, "currency": asset['currency']
                    }
                    st.rerun()

# --- 4. TABS ---
t1, t2, t3 = st.tabs(["🧠 Strategy", "🚀 Trade Desk", "📊 Performance"])

with t1:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy: {st.session_state.curr_trade['name']}")
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Run 'Manager Intel' in the sidebar to load data.")

with t2:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        fx = USD_INR_2026 if tr['currency'] == 'USD' else 1
        margin = (tr['price'] * fx) * tr['qty'] * 0.10
        
        st.subheader("Order Entry")
        c1, c2, c3 = st.columns(3)
        sl = c1.number_input("Stop Loss", value=tr['price']*0.97)
        tp = c2.number_input("Take Profit", value=tr['price']*1.05)
        c3.metric("Margin Required", f"₹{margin:,.2f}")

        if st.button("EXECUTE BUY"):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "name": tr['name'], "ticker": tr['ticker'], "entry": tr['price'],
                    "qty": tr['qty'], "margin": margin, "sl": sl, "tp": tp,
                    "currency": tr['currency'], "sector": tr['sector']
                })
                st.toast("Success!")
                st.rerun()
            else: st.error("Insufficient Funds.")

    st.divider()
    if st.session_state.portfolio:
        if st.button("🔄 Sync P&L"): st.rerun()
        for i, pos in enumerate(st.session_state.portfolio):
            live = yf.Ticker(pos['ticker']).history(period="1d")
            if not live.empty:
                cp = float(live['Close'].iloc[-1])
                fx = USD_INR_2026 if pos['currency'] == 'USD' else 1
                pnl = (cp - pos['entry']) * pos['qty'] * fx
                status = "🛑 SL HIT" if cp <= pos['sl'] else "🎯 TP HIT" if cp >= pos['tp'] else "🟢 ACTIVE"
                
                with st.expander(f"{pos['name']} | {status} | P&L: ₹{pnl:,.2f}"):
                    if st.button("CLOSE", key=f"c_{i}") or status != "🟢 ACTIVE":
                        st.session_state.fund_balance += (pos['margin'] + pnl)
                        st.session_state.balance_history.append(st.session_state.fund_balance)
                        st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": pnl})
                        st.session_state.portfolio.pop(i)
                        st.rerun()

with t3:
    if st.session_state.pnl_ledger:
        st.plotly_chart(px.line(st.session_state.balance_history, title="Equity Curve"), use_container_width=True)
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
