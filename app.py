import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
from datetime import datetime, date

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Full Suite", layout="wide", page_icon="🏛️")

# Official 2026 NSE Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 'ai_report': None, 'active_ticker': None}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. FAIL-BACK SYNC ENGINE ---
def get_safe_price(ticker):
    try:
        tk = yf.Ticker(ticker)
        # Attempt 1: 1m History (Most accurate for 2026 live sessions)
        hist = tk.history(period="1d", interval="1m")
        if not hist.empty: return float(hist['Close'].iloc[-1])
        # Attempt 2: Fast Info
        if hasattr(tk, 'fast_info'): return float(tk.fast_info.get('last_price', 0))
    except: pass
    return 0.0

def get_option_ticker(symbol, strike, opt_type, expiry_date):
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    return f"{prefix}{expiry_date.strftime('%y%m%d')}{'C' if 'CE' in opt_type else 'P'}{int(strike)}.NS"

# --- 3. SIDEBAR: PERSISTENT SEARCH & MARGIN ---
with st.sidebar:
    st.header("🇮🇳 NSE Control Center")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    # Live Margin Calculation
    total_margin = sum([p.get('margin', 0) for p in st.session_state.portfolio])
    st.write(f"**Blocked Margin:** ₹{total_margin:,.2f}")
    
    st.divider()
    user_query = st.text_input("Asset Search (e.g. Nifty, Reliance)", value="Nifty")
    
    # Search Logic: Keeps the AI button persistent
    if st.button("🔍 Find & Focus", use_container_width=True):
        q = user_query.upper().strip()
        search = yf.Search(q + " NSE", max_results=1)
        if search.quotes:
            st.session_state.active_ticker = {"symbol": search.quotes[0]['symbol'], "name": search.quotes[0].get('shortname', q)}
            st.success(f"Focused on {st.session_state.active_ticker['name']}")

    if st.session_state.active_ticker:
        if st.button("🔥 RUN AI QUANT INTEL", type="primary", use_container_width=True):
            price = get_safe_price(st.session_state.active_ticker['symbol'])
            res = st.session_state.client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=[f"NSE Intel: {st.session_state.active_ticker['name']} at ₹{price}. Recommend Option Strike."]
            )
            st.session_state.ai_report = {"text": res.text, "price": price}

# --- 4. MAIN TABS ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Strategy", "🚀 Execution Desk", "📊 Live Portfolio", "📜 Trade History"])

with t_ai:
    if st.session_state.ai_report:
        st.info(st.session_state.ai_report['text'])
    else: st.warning("Focus an asset and run AI Intel in the sidebar.")

with t_desk:
    if st.session_state.active_ticker:
        at = st.session_state.active_ticker
        st.subheader(f"Strategy: {at['name']}")
        
        mode = st.radio("Order Type", ["Options (Spreads)", "Naked Buy", "Naked Sell"], horizontal=True)
        
        c1, c2, c3 = st.columns(3)
        strike = c1.number_input("Strike", value=22000, step=50)
        otype = c2.selectbox("Type", ["CE", "PE"])
        expiry = c3.date_input("Expiry", value=date(2026, 4, 30))
        
        lots = st.number_input("Lots", min_value=1, value=1)
        lot_size = NSE_LOTS.get(at['symbol'].replace("^","").replace("NSEI","NIFTY").replace(".NS",""), 1)
        total_qty = lots * lot_size

        opt_tk = get_option_ticker(at['symbol'], strike, otype, expiry)
        live_p = get_safe_price(opt_tk) or 150.0
        
        # Margin Logic
        is_sell = "Sell" in mode
        margin_req = (185000 * lots) if is_sell else (live_p * total_qty)
        
        st.write(f"**Premium:** ₹{live_p} | **Required Margin:** ₹{margin_req:,.2f}")
        
        if st.button(f"CONFIRM {mode.upper()} @ ₹{live_p}", use_container_width=True):
            if st.session_state.fund_balance >= margin_req:
                st.session_state.fund_balance -= margin_req
                st.session_state.portfolio.append({
                    "name": f"{mode} {strike}{otype}", "ticker": opt_tk, "entry": live_p, 
                    "qty": total_qty, "side": "SELL" if is_sell else "BUY", "margin": margin_req
                })
                st.rerun()

with t_port:
    col_a, col_b = st.columns([4, 1])
    col_a.subheader("Active Positions")
    if col_b.button("🔄 SYNC ALL PRICES"): st.rerun()

    if st.session_state.portfolio:
        total_unrealized = 0
        for i, pos in enumerate(st.session_state.portfolio):
            cur = get_safe_price(pos['ticker']) or pos['entry']
            pnl = (cur - pos['entry']) * pos['qty'] if pos['side'] == "BUY" else (pos['entry'] - cur) * pos['qty']
            total_unrealized += pnl
            
            with st.expander(f"{pos['name']} | P/L: ₹{pnl:,.2f}"):
                st.write(f"Entry: {pos['entry']} | Current: {cur}")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": pos['name'], "Exit": cur, "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.metric("Total Unrealized P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else: st.info("No open positions.")

with t_hist:
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
        st.metric("Realized P/L", f"₹{sum(d['P&L'] for d in st.session_state.history):,.2f}")
