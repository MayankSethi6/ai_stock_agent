import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Elite Index Desk", layout="wide", page_icon="🇮🇳")

USD_INR_2026 = 87.50
# 2026 Revised NSE Lot Sizes
NSE_LOTS = {
    "NIFTY": 65, 
    "BANKNIFTY": 30, 
    "FINNIFTY": 60, 
    "RELIANCE": 250, 
    "SBIN": 1500, 
    "TCS": 175, 
    "INFY": 400
}

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

# --- 2. NSE SEARCH LOGIC ---
def nse_friendly_search(query):
    """Filters search to NSE only and handles Index mapping."""
    q = query.upper().strip()
    
    # Handle Nifty Index specifically
    if q in ["NIFTY", "NIFTY 50", "NIFTY50"]:
        return {"symbol": "^NSEI", "name": "Nifty 50 Index", "type": "INDEX"}
    if q in ["BANKNIFTY", "BANK NIFTY"]:
        return {"symbol": "^NSEBANK", "name": "Nifty Bank Index", "type": "INDEX"}

    try:
        # Search and force NSE Exchange
        search = yf.Search(q + " NSE", max_results=3)
        for res in search.quotes:
            if ".NS" in res['symbol']:
                return {
                    "symbol": res['symbol'], 
                    "name": res.get('shortname', res['symbol']),
                    "type": "EQUITY"
                }
    except: return None
    return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Fund Management")
    st.metric("Capital Available", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🗑️ Reset Account"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio = []
        if "curr_trade" in st.session_state: del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Friendly Search (e.g. Nifty, Reliance, SBI)", value="Nifty")
    asset = nse_friendly_search(user_query)
    
    if asset:
        st.success(f"Found: {asset['name']}")
        st.caption(f"Ticker: `{asset['symbol']}`")
        
        # Determine Lot Size
        clean_ticker = asset['symbol'].replace(".NS", "").replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY")
        lot_size = NSE_LOTS.get(clean_ticker, 1)
        
        lots = st.number_input(f"Quantity (Lots of {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run AI Manager Intel"):
            with st.spinner("Analyzing NSE Market..."):
                tk = yf.Ticker(asset['symbol'])
                hist = tk.history(period="1d")
                if not hist.empty:
                    cp = float(hist['Close'].iloc[-1])
                    prompt = f"Hedge Fund Manager. Asset: {asset['name']} @ {cp}. Give a Bullish/Bearish sentiment and suggest a Strike Price for CE/PE."
                    # FIXED: Using gemini-3-flash-preview
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    
                    st.session_state.curr_trade = {
                        "ticker": asset['symbol'], "name": asset['name'], 
                        "market_price": cp, "qty": lots * lot_size, "report": res.text
                    }
                    st.rerun()

# --- 4. DASHBOARD TABS ---
t_ai, t_opt, t_desk, t_perf = st.tabs(["🧠 AI Strategy", "🎯 Option Recs", "🚀 Execution Desk", "📈 Performance"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategic View: {st.session_state.curr_trade['name']}")
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Please search and run Intel to start.")

with t_opt:
    if "curr_trade" in st.session_state:
        cp = st.session_state.curr_trade['market_price']
        atm = round(cp / 50) * 50
        st.subheader("F&O Strategic Strikes")
        c1, c2 = st.columns(2)
        c1.metric("Bullish (ATM CE)", f"{atm} CE")
        c2.metric("Bearish (ATM PE)", f"{atm} PE")
        st.caption("Strikes are rounded to nearest 50 (NSE Standard).")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Institutional Order Entry")
        
        mode = st.radio("Instrument Type", ["Cash/Spot", "Options (Premium)"], horizontal=True)
        
        c_p, c_sl, c_tp = st.columns(3)
        entry_price = c_p.number_input("Entry Price (Limit)", value=float(tr['market_price']) if mode=="Cash/Spot" else 100.0)
        sl = c_sl.number_input("Stop Loss", value=entry_price * 0.95)
        tp = c_tp.number_input("Take Profit", value=entry_price * 1.10)
        
        # Margin: 10% for Cash, 100% for Options
        margin_mult = 0.10 if mode == "Cash/Spot" else 1.0
        req_margin = entry_price * tr['qty'] * margin_mult
        
        st.metric("Margin Required", f"₹{req_margin:,.2f}")

        if st.button("EXECUTE ORDER"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": f"{tr['name']} ({mode})", "ticker": tr['ticker'], 
                    "entry": entry_price, "qty": tr['qty'], "margin": req_margin, 
                    "sl": sl, "tp": tp
                })
                st.toast("Position Opened on NSE Desk")
                st.rerun()
            else: st.error("Insufficient Fund Balance!")

    st.divider()
    for i, pos in enumerate(st.session_state.portfolio):
        with st.expander(f"{pos['name']} | Entry: {pos['entry']} | Qty: {pos['qty']}"):
            if st.button("CLOSE POSITION", key=f"cl_{i}"):
                st.session_state.fund_balance += pos['margin']
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": 0.0})
                st.session_state.portfolio.pop(i)
                st.rerun()

with t_perf:
    if st.session_state.pnl_ledger:
        st.plotly_chart(px.line(st.session_state.balance_history, title="Equity Curve (NSE)"), use_container_width=True)
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
