import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Elite Equity Desk", layout="wide", page_icon="🏛️")

NSE_FO_MASTER = {
    "NIFTY.NS": 65, "BANKNIFTY.NS": 30, "FINNIFTY.NS": 60, "RELIANCE.NS": 250,
    "TCS.NS": 175, "HDFCBANK.NS": 550, "ICICIBANK.NS": 700, "INFY.NS": 400,
    "SBIN.NS": 1500, "BHARTIARTL.NS": 950, "ITC.NS": 1600, "TATAMOTORS.NS": 1425
}

DISCLAIMER = "⚠️ **Institutional Disclosure:** Trading involves risk. 2026 NSE Lot Sizes. Market Hours: 9:15 AM - 3:30 PM IST."

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
if 'fund_balance' not in st.session_state:
    st.session_state.fund_balance = 1000000.0
if 'balance_history' not in st.session_state:
    st.session_state.balance_history = [1000000.0] # For Equity Curve
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

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Fund Management")
    st.metric("Liquid Paper Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🔄 Reset Global Account"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        st.rerun()
    
    st.divider()
    ticker_choice = st.selectbox("Asset (Lot Size)", options=list(NSE_FO_MASTER.keys()))
    lots = st.number_input("Lots", min_value=1, max_value=100, value=1)
    
    is_open, cur_time = get_market_status()
    st.info(f"IST Time: {cur_time}")

    if st.button("Generate Alpha Strategy"):
        with st.spinner("AI Analysis..."):
            hist = yf.Ticker(ticker_choice).history(period="5d", interval="15m")
            cp = float(hist['Close'].iloc[-1])
            prompt = f"Hedge Fund Strategy for {ticker_choice} @ {cp}. Provide 2-5% profit scalp logic."
            res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
            st.session_state.curr_trade = {"ticker": ticker_choice, "price": cp, "lots": lots, "report": res.text}

# --- 4. TABS ---
tab_strat, tab_desk, tab_ledger = st.tabs(["🧠 AI Strategy", "🚀 Trading Desk", "📜 P&L Ledger"])

with tab_strat:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    st.caption(DISCLAIMER)

with tab_desk:
    if "curr_trade" in st.session_state:
        qty = NSE_FO_MASTER[st.session_state.curr_trade['ticker']] * st.session_state.curr_trade['lots']
        margin = float(st.session_state.curr_trade['price'] * qty * 0.10)
        
        if st.button("EXECUTE BUY"):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "ticker": st.session_state.curr_trade['ticker'], "entry": float(st.session_state.curr_trade['price']),
                    "qty": int(qty), "margin": margin
                })
                st.rerun()

    st.divider()
    if st.session_state.portfolio and st.button("🔄 Sync Live Prices"): st.rerun()

    for i, pos in enumerate(st.session_state.portfolio):
        current_p = get_live_price(pos['ticker'])
        if current_p:
            pnl = float((current_p - pos['entry']) * pos['qty'])
            with st.expander(f"{pos['ticker']} | Live P&L: ₹{pnl:,.2f}", expanded=True):
                st.write(f"Entry: ₹{pos['entry']} | LTP: ₹{current_p}")
                if st.button("SELL & WRITE OFF", key=f"s_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.balance_history.append(st.session_state.fund_balance)
                    st.session_state.pnl_ledger.append({"Asset": pos['ticker'], "P&L": pnl})
                    st.session_state.portfolio.pop(i)
                    st.rerun()

with tab_ledger:
    st.subheader("📈 Institutional Equity Curve")
    # Plotting the growth of the fund
    fig = px.line(st.session_state.balance_history, title="Total Fund Value Over Time", labels={'value': 'Cash (₹)', 'index': 'Trade Count'})
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
    
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
    st.caption(DISCLAIMER)
