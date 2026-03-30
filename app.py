import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Elite Searchable Desk", layout="wide", page_icon="🏛️")

# 2026 NSE F&O Master Mapping (Friendly Name : Ticker)
ASSET_LOOKUP = {
    "Nifty 50": "NIFTY.NS",
    "Bank Nifty": "BANKNIFTY.NS",
    "Finnifty": "FINNIFTY.NS",
    "Reliance": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "HDFC Bank": "HDFCBANK.NS",
    "ICICI Bank": "ICICIBANK.NS",
    "Infosys": "INFY.NS",
    "SBI": "SBIN.NS",
    "Airtel": "BHARTIARTL.NS",
    "ITC": "ITC.NS",
    "Tata Motors": "TATAMOTORS.NS",
    "Kotak Bank": "KOTAKBANK.NS",
    "L&T": "LT.NS",
    "Axis Bank": "AXISBANK.NS"
}

# Ticker to Lot Size (March 2026)
LOT_SIZES = {
    "NIFTY.NS": 65, "BANKNIFTY.NS": 30, "FINNIFTY.NS": 60, "RELIANCE.NS": 250,
    "TCS.NS": 175, "HDFCBANK.NS": 550, "ICICIBANK.NS": 700, "INFY.NS": 400,
    "SBIN.NS": 1500, "BHARTIARTL.NS": 950, "ITC.NS": 1600, "TATAMOTORS.NS": 1425,
    "KOTAKBANK.NS": 400, "LT.NS": 300, "AXISBANK.NS": 625
}

DISCLAIMER = "⚠️ **Institutional Disclosure:** 2026 NSE Lot Sizes. Market Hours: 9:15 AM - 3:30 PM IST."

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
if 'fund_balance' not in st.session_state:
    st.session_state.fund_balance = 1000000.0
if 'balance_history' not in st.session_state:
    st.session_state.balance_history = [1000000.0]
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []
if 'pnl_ledger' not in st.session_state:
    st.session_state.pnl_ledger = []

# --- 2. UTILITIES ---
def get_market_status():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    is_open = now.weekday() < 5 and time(9,15) <= now.time() <= time(15,30)
    return is_open, now.strftime("%H:%M:%S")

def get_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else None
    except: return None

# --- 3. SIDEBAR: THE TRADING CONSOLE ---
with st.sidebar:
    st.header("💳 Fund Management")
    st.metric("Liquid Paper Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🔄 Reset Account"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        st.rerun()
    
    st.divider()
    st.header("🔍 Asset Search")
    # SEARCHABLE BOX
    search_input = st.selectbox("Search Company or Index", options=list(ASSET_LOOKUP.keys()))
    target_ticker = ASSET_LOOKUP[search_input]
    target_lot = LOT_SIZES[target_ticker]
    
    st.write(f"**Ticker:** `{target_ticker}` | **Lot Size:** `{target_lot}`")
    lots = st.number_input("Lots", min_value=1, max_value=100, value=1)
    
    market_open, cur_time = get_market_status()
    if market_open: st.success(f"🟢 Market Open: {cur_time}")
    else: st.error(f"🔴 Market Closed: {cur_time}")

    if st.button("Generate Alpha Strategy"):
        with st.spinner("AI Analysis..."):
            hist = yf.Ticker(target_ticker).history(period="5d", interval="15m")
            cp = float(hist['Close'].iloc[-1])
            prompt = f"Role: Hedge Fund Manager. Asset: {search_input} @ {cp}. Provide 2-5% profit scalp strategy."
            res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
            st.session_state.curr_trade = {"ticker": target_ticker, "name": search_input, "price": cp, "lots": lots, "report": res.text}

# --- 4. MAIN TABS ---
tab_strat, tab_desk, tab_ledger = st.tabs(["🧠 AI Strategy", "🚀 Trading Desk", "📜 P&L Ledger"])

with tab_strat:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy: {st.session_state.curr_trade['name']}")
        st.info(st.session_state.curr_trade['report'])
    st.caption(DISCLAIMER)

with tab_desk:
    if "curr_trade" in st.session_state:
        qty = LOT_SIZES[st.session_state.curr_trade['ticker']] * st.session_state.curr_trade['lots']
        margin = float(st.session_state.curr_trade['price'] * qty * 0.10)
        
        # RISK METER
        risk_pct = (margin / st.session_state.fund_balance) * 100
        st.write(f"**Exposure:** {qty} units | **Margin:** ₹{margin:,.2f}")
        
        if risk_pct > 50:
            st.warning(f"⚠️ HIGH RISK: This trade uses {risk_pct:.1f}% of your liquid cash.")
        else:
            st.info(f"Risk Profile: {risk_pct:.1f}% of capital.")

        if st.button("EXECUTE BUY"):
            if not market_open: st.error("Market Closed.")
            elif st.session_state.fund_balance < margin: st.error("Insufficient Funds.")
            else:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "name": st.session_state.curr_trade['name'], "ticker": st.session_state.curr_trade['ticker'], 
                    "entry": float(st.session_state.curr_trade['price']), "qty": int(qty), "margin": margin
                })
                st.rerun()

    st.divider()
    if st.session_state.portfolio and st.button("🔄 Sync Live Prices"): st.rerun()

    for i, pos in enumerate(st.session_state.portfolio):
        cp = get_live_price(pos['ticker'])
        if cp:
            pnl = float((cp - pos['entry']) * pos['qty'])
            pnl_color = "green" if pnl >= 0 else "red"
            with st.expander(f"{pos['name']} | Live P&L: ₹{pnl:,.2f}", expanded=True):
                st.markdown(f"Entry: ₹{pos['entry']} | LTP: ₹{cp} | **P&L:** <span style='color:{pnl_color}'>₹{pnl:,.2f}</span>", unsafe_allow_html=True)
                if st.button("SELL & WRITE OFF", key=f"s_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.balance_history.append(st.session_state.fund_balance)
                    st.session_state.pnl_ledger.append({"Asset": pos['name'], "Net P&L": pnl, "Exit Price": cp})
                    st.session_state.portfolio.pop(i)
                    st.rerun()

with tab_ledger:
    st.subheader("📈 Institutional Equity Curve")
    if len(st.session_state.balance_history) > 1:
        fig = px.line(st.session_state.balance_history, title="Total Fund Value", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
    st.caption(DISCLAIMER)
