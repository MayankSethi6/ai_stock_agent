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
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. UTILITIES ---
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

def fetch_live_price(ticker):
    try:
        tk = yf.Ticker(ticker)
        data = tk.history(period="1d")
        if not data.empty: return float(data['Close'].iloc[-1])
        if tk.fast_info.get('last_price'): return float(tk.fast_info['last_price'])
    except: pass
    return 0.0

def get_option_ticker(symbol, strike, opt_type, expiry_date):
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    return f"{prefix}{expiry_date.strftime('%y%m%d')}{'C' if 'CE' in opt_type else 'P'}{int(strike)}.NS"

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Pro Desk")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🔄 Full System Reset"):
        for k in ['fund_balance', 'portfolio', 'pnl_ledger', 'curr_trade']:
            if k in st.session_state: del st.session_state[k]
        st.rerun()

    user_query = st.text_input("Search Asset", value="Nifty")
    asset = strict_nse_search(user_query)
    
    if asset and st.button("🔥 Run AI Quant Intel"):
        try:
            res = st.session_state.client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=[f"Quick NSE Analysis: {asset['name']}. Give sentiment & key levels."]
            )
            report = res.text
        except: report = "AI Service busy. Using technical defaults."
        
        st.session_state.curr_trade = {"ticker": asset['symbol'], "name": asset['name'], "report": report, "market_price": fetch_live_price(asset['symbol'])}
        st.rerun()

# --- 4. MAIN INTERFACE ---
t_ai, t_desk, t_port = st.tabs(["🧠 Alpha Strategy", "🚀 Execution Desk", "📊 Live Portfolio"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Select an asset in sidebar.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader(f"Trading: {tr['name']}")
        
        mode = st.radio("Type", ["Cash", "Options", "Spreads"], horizontal=True)
        
        col_q, col_sl, col_tp = st.columns(3)
        lot_size = NSE_LOTS.get(tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY"), 1)
        lots = col_q.number_input("Lots", min_value=1, value=1)
        total_qty = lots * lot_size
        
        # Risk Management Inputs
        sl_pct = col_sl.number_input("Stop Loss %", value=5.0, step=0.5)
        tp_pct = col_tp.number_input("Take Profit %", value=15.0, step=0.5)
        
        expiry = st.date_input("Expiry", value=date(2026, 4, 30))
        
        if mode == "Options":
            c1, c2 = st.columns(2)
            strike = c1.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            otype = c2.selectbox("Type", ["CE", "PE"])
            opt_tk = get_option_ticker(tr['ticker'], strike, otype, expiry)
            
            price = fetch_live_price(opt_tk) or 100.0
            margin = price * total_qty
            
            if st.button(f"BUY {opt_tk}"):
                if st.session_state.fund_balance >= margin:
                    st.session_state.fund_balance -= margin
                    st.session_state.portfolio.append({
                        "name": f"{tr['name']} {strike}{otype}", "ticker": opt_tk, "entry": price, 
                        "qty": total_qty, "side": "BUY", "margin": margin, 
                        "sl": price * (1 - sl_pct/100), "tp": price * (1 + tp_pct/100)
                    })
                    st.rerun()

        elif mode == "Spreads":
            # Payoff Visualizer with updated 2026 syntax
            atm = int(round(tr['market_price']/50)*50)
            s_range = np.linspace(atm-300, atm+300, 50)
            payoff = (np.maximum(s_range - atm, 0) - 100) * total_qty # Dummy placeholder
            
            fig = go.Figure(go.Scatter(x=s_range, y=payoff, line=dict(color='cyan')))
            fig.update_layout(title="Strategy Payoff Preview", template="plotly_dark", height=300)
            
            # --- FIX: Updated width parameter ---
            st.plotly_chart(fig, width='stretch') 
            
            if st.button("Execute Default Bull Spread"):
                st.toast("Executing Spread legs...")

with t_port:
    st.subheader("Active Positions")
    for i, pos in enumerate(st.session_state.portfolio):
        cur = fetch_live_price(pos['ticker']) or pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if pos['side'] == "BUY" else (pos['entry'] - cur) * pos['qty']
        
        # UI Alerts for SL/TP
        status = ""
        if cur <= pos['sl']: status = "🚨 STOP LOSS HIT"
        if cur >= pos['tp']: status = "🎯 TARGET HIT"
        
        with st.expander(f"{pos['name']} | P&L: ₹{pnl:,.2f} {status}"):
            st.write(f"Current: ₹{cur} | SL: ₹{pos['sl']:.2f} | TP: ₹{pos['tp']:.2f}")
            if st.button("Close Position", key=f"close_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.portfolio.pop(i)
                st.rerun()
