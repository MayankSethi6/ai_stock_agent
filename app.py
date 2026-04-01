import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Pro F&O", layout="wide", page_icon="🏛️")

NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 'search_focus': None}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. FAIL-BACK SYNC ENGINE ---
def get_safe_price(ticker):
    """Triple-check fallback mechanism for NSE/F&O prices."""
    try:
        tk = yf.Ticker(ticker)
        # Attempt 1: Live History
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty: return float(hist['Close'].iloc[-1])
        # Attempt 2: Fast Info (Real-time Metadata)
        if hasattr(tk, 'fast_info') and tk.fast_info.get('last_price'):
            return float(tk.fast_info['last_price'])
        # Attempt 3: Basic Info
        if tk.info.get('regularMarketPrice'):
            return float(tk.info['regularMarketPrice'])
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

# --- 3. SIDEBAR (STAY-ALIVE LOGIC) ---
with st.sidebar:
    st.header("🇮🇳 NSE Alpha v2026")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    user_query = st.text_input("Asset Search", value="Nifty", key="main_search")
    found_asset = strict_nse_search(user_query)
    
    if found_asset:
        st.session_state.search_focus = found_asset
        st.success(f"Focused: {found_asset['name']}")
        
        # PERSISTENT BUTTON: Does not disappear on text change
        if st.button("🔥 RUN AI QUANT INTEL", use_container_width=True):
            try:
                price = get_safe_price(found_asset['symbol'])
                res = st.session_state.client.models.generate_content(
                    model="gemini-3-flash-preview", 
                    contents=[f"NSE Hedge Fund Intel: {found_asset['name']} at ₹{price}. Give trend + strike."]
                )
                st.session_state.curr_trade = {
                    "ticker": found_asset['symbol'], 
                    "name": found_asset['name'], 
                    "report": res.text, 
                    "market_price": price
                }
            except: st.error("AI node saturated. Try again.")

    if st.button("🔄 Emergency Reset", use_container_width=True):
        st.session_state.fund_balance, st.session_state.portfolio = 1000000.0, []
        st.rerun()

# --- 4. TABS ---
t_ai, t_desk, t_port = st.tabs(["🧠 Alpha Strategy", "🚀 Execution Desk", "📊 Active Portfolio"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Initiate search and Run AI Intel.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader(f"Strategy Builder: {tr['name']}")
        
        mode = st.radio("Instrument", ["Cash", "Options (Incl. Spreads)", "Naked Sell/Buy"], horizontal=True)
        
        col_q, col_sl, col_tp = st.columns(3)
        lot_size = NSE_LOTS.get(tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY"), 1)
        lots = col_q.number_input("Lots", min_value=1, value=1)
        sl_pct = col_sl.number_input("SL %", value=10.0)
        tp_pct = col_tp.number_input("TP %", value=25.0)
        
        if "Options" in mode or "Naked" in mode:
            c1, c2, c3 = st.columns(3)
            strike = c1.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            otype = c2.selectbox("Type", ["CE", "PE"])
            expiry = c3.date_input("Expiry", value=date(2026, 4, 30))
            
            opt_tk = get_option_ticker(tr['ticker'], strike, otype, expiry)
            price = get_safe_price(opt_tk) or 150.0
            
            side = st.selectbox("Action", ["BUY", "SELL"])
            margin_req = (150000 * lots) if (side == "SELL" and "Naked" in mode) else (price * lots * lot_size)
            
            if st.button(f"EXECUTE {side} {opt_tk} @ ₹{price}"):
                if st.session_state.fund_balance >= margin_req:
                    st.session_state.fund_balance -= margin_req
                    st.session_state.portfolio.append({
                        "name": f"{side} {strike}{otype}", "ticker": opt_tk, "entry": price, 
                        "qty": lots * lot_size, "side": side, "margin": margin_req,
                        "sl": price * (1.1 if side == "SELL" else 0.9),
                        "tp": price * (0.8 if side == "SELL" else 1.3)
                    })
                    st.toast("Order Executed!")
                    st.rerun()

with t_port:
    if st.session_state.portfolio:
        # LIVE SYNC: Updates every rerun
        st.subheader("Live Order Book")
        total_pnl = 0
        for i, pos in enumerate(st.session_state.portfolio):
            cur = get_safe_price(pos['ticker']) or pos['entry']
            pnl = (cur - pos['entry']) * pos['qty'] if pos['side'] == "BUY" else (pos['entry'] - cur) * pos['qty']
            total_pnl += pnl
            
            color = "green" if pnl >= 0 else "red"
            with st.expander(f"{pos['name']} | :{color}[₹{pnl:,.2f}]"):
                st.write(f"Price: {pos['entry']} → {cur} | Qty: {pos['qty']}")
                if st.button("Close Position", key=f"cls_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.divider()
        st.metric("Total Unrealized P/L", f"₹{total_pnl:,.2f}", delta=total_pnl)
    else: st.info("No active orders in market.")
