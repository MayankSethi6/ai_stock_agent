import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. CONFIG ---
st.set_page_config(page_title="NSE Alpha - Pro F&O", layout="wide", page_icon="🏛️")

NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. ADVANCED UTILITIES ---
def get_option_ticker(symbol, strike, opt_type, expiry_date):
    """Formats NSE Ticker: SYMBOL + YY + MMM + DD + C/P + STRIKE + .NS"""
    # Simplified for the current month for demo purposes
    # Real production would use a lookup table for exact NSE expiry dates
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    expiry_str = expiry_date.strftime("%y%m%d") # e.g., 260416
    suffix = "C" if "CE" in opt_type else "P"
    return f"{prefix}{expiry_str}{suffix}{int(strike)}.NS"

def fetch_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    except: return 0.0

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Pro Desk")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    user_query = st.text_input("Search (Nifty/SBI/Reliance)", value="Nifty")
    try:
        search = yf.Search(user_query + " NSE", max_results=1).quotes[0]
        asset_sym = search['symbol']
        asset_name = search.get('shortname', asset_sym)
    except:
        asset_sym, asset_name = "^NSEI", "Nifty 50"

    st.success(f"Focused: {asset_name}")
    
    if st.button("🔥 Run AI Quant Intel"):
        tk = yf.Ticker(asset_sym)
        cp = tk.history(period="5d")['Close'].iloc[-1]
        res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[f"Analyze {asset_name} at {cp}"])
        st.session_state.curr_trade = {"ticker": asset_sym, "name": asset_name, "market_price": float(cp), "report": res.text}
        st.rerun()

# --- 4. TABS ---
t_ai, t_desk, t_port = st.tabs(["🧠 Alpha Strategy", "🚀 Execution Desk", "📊 Live Portfolio"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Run Intel to see strategy.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Order Entry")
        
        mode = st.radio("Instrument", ["Cash", "Options"], horizontal=True)
        side = st.radio("Action", ["BUY", "SELL"], horizontal=True)
        
        if mode == "Options":
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Type", ["CE", "PE"])
            strike = c2.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            
            # --- LIVE STRIKE PRICE FETCH ---
            # Using a fixed April 2026 expiry for logic
            opt_ticker = get_option_ticker(tr['ticker'], strike, opt_type, datetime(2026, 4, 30))
            
            if 'last_strike_price' not in st.session_state or st.button("🔄 Refresh Strike Price"):
                st.session_state.last_strike_price = fetch_live_price(opt_ticker)
            
            entry_price = c3.number_input("Premium", value=st.session_state.last_strike_price if st.session_state.last_strike_price > 0 else 100.0)
            st.caption(f"Live Premium for {opt_ticker}: ₹{st.session_state.last_strike_price}")
            
            margin_mult = 1.0 if side == "BUY" else 5.0 # Selling options requires ~5x margin
        else:
            entry_price = st.number_input("Price", value=tr['market_price'])
            margin_mult = 0.10 if side == "BUY" else 1.0

        lot_key = tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY").replace("NSEBANK","BANKNIFTY")
        lots = st.number_input("Lots", min_value=1, value=1)
        total_qty = lots * NSE_LOTS.get(lot_key, 1)
        
        req_margin = entry_price * total_qty * margin_mult
        st.metric("Total Margin Required", f"₹{req_margin:,.2f}")

        if st.button(f"CONFIRM {side} {total_qty} UNITS"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": f"{tr['name']} {strike if mode=='Options' else ''} {opt_type if mode=='Options' else ''}",
                    "ticker": opt_ticker if mode=="Options" else tr['ticker'],
                    "entry": entry_price, "qty": total_qty, "side": side, "margin": req_margin, "mode": mode
                })
                st.rerun()
            else: st.error("Insufficient Funds.")

with t_port:
    st.subheader("Current Open Positions")
    if st.button("🔄 Sync Live P&L"): st.rerun()
    
    total_unrealized = 0
    for i, pos in enumerate(st.session_state.portfolio):
        current_price = fetch_live_price(pos['ticker'])
        # P&L Logic: (Current - Entry) * Qty for Buy | (Entry - Current) * Qty for Sell
        if pos['side'] == "BUY":
            pnl = (current_price - pos['entry']) * pos['qty']
        else:
            pnl = (pos['entry'] - current_price) * pos['qty']
        
        total_unrealized += pnl
        
        color = "green" if pnl >= 0 else "red"
        with st.expander(f"{pos['name']} | {pos['side']} | P&L: :{color}[₹{pnl:,.2f}]"):
            st.write(f"Entry: {pos['entry']} | Current: {current_price} | Margin: ₹{pos['margin']:,.2f}")
            if st.button("SQUARE OFF", key=f"sq_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "Final P&L": pnl})
                st.session_state.portfolio.pop(i)
                st.rerun()
    
    st.divider()
    st.metric("Total Unrealized P&L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
