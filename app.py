import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Pro F&O", layout="wide", page_icon="🏛️")

# Official 2026 NSE Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'history': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. UTILITIES ---
def fetch_live_price(ticker):
    try:
        tk = yf.Ticker(ticker)
        data = tk.history(period="1d")
        if not data.empty: return float(data['Close'].iloc[-1])
        if hasattr(tk, 'fast_info') and tk.fast_info.get('last_price'):
            return float(tk.fast_info['last_price'])
    except: pass
    return 0.0

def strict_nse_search(query):
    q = query.upper().strip()
    if q in ["NIFTY", "NIFTY 50"]: return {"symbol": "^NSEI", "name": "Nifty 50"}
    if q in ["BANKNIFTY", "NIFTY BANK"]: return {"symbol": "^NSEBANK", "name": "Nifty Bank"}
    try:
        search = yf.Search(q + " NSE", max_results=2)
        for res in search.quotes:
            if res.get('exchDisp') == "NSE" or res.get('symbol','').endswith(".NS"):
                return {"symbol": res['symbol'], "name": res.get('shortname', res['symbol'])}
    except: pass
    return None

def get_option_ticker(symbol, strike, opt_type, expiry_date):
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    return f"{prefix}{expiry_date.strftime('%y%m%d')}{'C' if 'CE' in opt_type else 'P'}{int(strike)}.NS"

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Pro Desk")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    # Margin Monitor
    total_margin = sum([p.get('margin', 0) for p in st.session_state.portfolio])
    st.write(f"**Blocked Margin:** ₹{total_margin:,.2f}")
    
    if st.button("🔄 Reset Terminal"):
        st.session_state.fund_balance, st.session_state.portfolio, st.session_state.history = 1000000.0, [], []
        st.rerun()

    user_query = st.text_input("Search Asset", value="Nifty")
    asset = strict_nse_search(user_query)
    
    if asset and st.button("🔥 Run AI Quant Intel"):
        try:
            res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", 
                contents=[f"NSE Analysis: {asset['name']}. Price: {fetch_live_price(asset['symbol'])}."])
            report = res.text
        except: report = "AI Service busy. Proceed with technical defaults."
        st.session_state.curr_trade = {"ticker": asset['symbol'], "name": asset['name'], "report": report, "market_price": fetch_live_price(asset['symbol'])}
        st.rerun()

# --- 4. MAIN INTERFACE ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Strategy", "🚀 Execution", "📊 Portfolio", "📜 History"])

with t_ai:
    if "curr_trade" in st.session_state: st.info(st.session_state.curr_trade['report'])
    else: st.warning("Run AI Intel in the sidebar.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        mode = st.radio("Instrument", ["Cash", "Options", "Naked Sell"], horizontal=True)
        
        c_q, c_sl, c_tp = st.columns(3)
        lot_size = NSE_LOTS.get(tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY"), 1)
        lots = c_q.number_input("Lots", min_value=1, value=1)
        total_qty = lots * lot_size
        sl_pct = c_sl.number_input("SL %", value=5.0)
        tp_pct = c_tp.number_input("TP %", value=15.0)
        expiry = st.date_input("Expiry", value=date(2026, 4, 30))

        if mode in ["Options", "Naked Sell"]:
            c1, c2 = st.columns(2)
            strike = c1.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            otype = c2.selectbox("Type", ["CE", "PE"])
            opt_tk = get_option_ticker(tr['ticker'], strike, otype, expiry)
            live_p = fetch_live_price(opt_tk) or 100.0
            
            if mode == "Options":
                margin = live_p * total_qty
                if st.button(f"BUY {opt_tk} @ {live_p}"):
                    if st.session_state.fund_balance >= margin:
                        st.session_state.fund_balance -= margin
                        st.session_state.portfolio.append({"name": f"{strike}{otype}", "ticker": opt_tk, "entry": live_p, "qty": total_qty, "side": "BUY", "margin": margin, "sl": live_p*(1-sl_pct/100), "tp": live_p*(1+tp_pct/100)})
                        st.rerun()
            else: # Naked Sell
                margin = 150000.0 * lots # Simulating NSE SPAN
                credit = live_p * total_qty
                if st.button(f"SELL {opt_tk} @ {live_p}"):
                    if st.session_state.fund_balance >= (margin - credit):
                        st.session_state.fund_balance -= (margin - credit)
                        st.session_state.portfolio.append({"name": f"NAKED {strike}{otype}", "ticker": opt_tk, "entry": live_p, "qty": total_qty, "side": "SELL", "margin": margin, "sl": live_p*(1+sl_pct/100), "tp": live_p*(1-tp_pct/100)})
                        st.rerun()

with t_port:
    if st.session_state.portfolio:
        if st.button("🚨 SQUARE OFF ALL"):
            st.session_state.portfolio = []
            st.rerun()
        for i, pos in enumerate(st.session_state.portfolio):
            cur = fetch_live_price(pos['ticker']) or pos['entry']
            pnl = (cur - pos['entry']) * pos['qty'] if pos['side'] == "BUY" else (pos['entry'] - cur) * pos['qty']
            
            # Use .get() for safety
            sl, tp = pos.get('sl', 0), pos.get('tp', 999999)
            status = "🚨 SL HIT" if (pos['side']=="BUY" and cur<=sl) or (pos['side']=="SELL" and cur>=sl) else ""
            
            with st.expander(f"{pos['name']} | P&L: ₹{pnl:,.2f} {status}"):
                if st.button("Close", key=f"c_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": pos['name'], "P&L": pnl, "Date": datetime.now().strftime("%H:%M:%S")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
    else: st.info("No active trades.")

with t_hist:
    if st.session_state.history:
        df = pd.DataFrame(st.session_state.history)
        st.table(df)
        st.metric("Total Realized P&L", f"₹{df['P&L'].sum():,.2f}")
    else: st.write("History is clean.")
