import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time # FIXED: Added 'time' import
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Elite Equity Desk", layout="wide", page_icon="🏛️")

# 2026 NSE F&O Master List
NSE_FO_MASTER = {
    "NIFTY.NS": 65, "BANKNIFTY.NS": 30, "FINNIFTY.NS": 60, "RELIANCE.NS": 250,
    "TCS.NS": 175, "HDFCBANK.NS": 550, "ICICIBANK.NS": 700, "INFY.NS": 400,
    "SBIN.NS": 1500, "BHARTIARTL.NS": 950, "ITC.NS": 1600, "TATAMOTORS.NS": 1425
}

DISCLAIMER = "⚠️ **Institutional Disclosure:** Trading involves risk. 2026 NSE Lot Sizes. Market Hours: 9:15 AM - 3:30 PM IST."

if 'client' not in st.session_state:
    try:
        st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
    except:
        st.error("Missing GOOGLE_API_KEY in Secrets.")
        st.stop()

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
    """Checks NSE Market Hours strictly (9:15 - 15:30 IST)."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    # Check if weekday (0-4) and within time range
    is_open = now.weekday() < 5 and time(9,15) <= now.time() <= time(15,30)
    return is_open, now.strftime("%H:%M:%S")

def get_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else None
    except:
        return None

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
    
    market_open, cur_time = get_market_status()
    if market_open:
        st.success(f"🟢 NSE Open: {cur_time}")
    else:
        st.error(f"🔴 NSE Closed: {cur_time}")

    if st.button("Generate Alpha Strategy"):
        with st.spinner("AI Analysis..."):
            tk = yf.Ticker(ticker_choice)
            hist = tk.history(period="5d", interval="15m")
            if not hist.empty:
                cp = float(hist['Close'].iloc[-1])
                prompt = f"Role: Hedge Fund Manager. Asset: {ticker_choice} @ {cp}. Provide 2-5% profit scalp logic."
                res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                st.session_state.curr_trade = {"ticker": ticker_choice, "price": cp, "lots": lots, "report": res.text}

# --- 4. TABS ---
tab_strat, tab_desk, tab_ledger = st.tabs(["🧠 AI Strategy", "🚀 Trading Desk", "📜 P&L Ledger"])

with tab_strat:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy for {st.session_state.curr_trade['ticker']}")
        st.info(st.session_state.curr_trade['report'])
    st.caption(DISCLAIMER)

with tab_desk:
    if "curr_trade" in st.session_state:
        qty = NSE_FO_MASTER[st.session_state.curr_trade['ticker']] * st.session_state.curr_trade['lots']
        margin = float(st.session_state.curr_trade['price'] * qty * 0.10) # 10% Margin
        
        st.markdown(f"**Executing:** {qty} units of {st.session_state.curr_trade['ticker']}")
        if st.button("EXECUTE BUY ORDER"):
            if not market_open:
                st.error("Market is closed. Orders blocked.")
            elif st.session_state.fund_balance < margin:
                st.error("Insufficient Fund Balance!")
            else:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "ticker": st.session_state.curr_trade['ticker'], 
                    "entry": float(st.session_state.curr_trade['price']),
                    "qty": int(qty), "margin": margin, "time": cur_time
                })
                st.rerun()

    st.divider()
    st.subheader("📂 Active Positions")
    if st.session_state.portfolio and st.button("🔄 Sync Live Prices"): st.rerun()

    if not st.session_state.portfolio:
        st.info("No active trades.")
    else:
        for i, pos in enumerate(st.session_state.portfolio):
            current_p = get_live_price(pos['ticker'])
            if current_p:
                pnl = float((current_p - pos['entry']) * pos['qty'])
                pnl_color = "green" if pnl >= 0 else "red"
                
                with st.expander(f"{pos['ticker']} | Live P&L: ₹{pnl:,.2f}", expanded=True):
                    st.markdown(f"**Entry:** ₹{pos['entry']} | **LTP:** ₹{current_p} | **P&L:** <span style='color:{pnl_color}'>₹{pnl:,.2f}</span>", unsafe_allow_html=True)
                    if st.button("SELL & WRITE OFF", key=f"sell_{i}"):
                        st.session_state.fund_balance += (pos['margin'] + pnl)
                        st.session_state.balance_history.append(st.session_state.fund_balance)
                        st.session_state.pnl_ledger.append({
                            "Asset": pos['ticker'], "Entry": pos['entry'], "Exit": current_p,
                            "Qty": pos['qty'], "Net P&L": pnl, "Time": pos['time']
                        })
                        st.session_state.portfolio.pop(i)
                        st.rerun()

with tab_ledger:
    st.subheader("📈 Institutional Equity Curve")
    if len(st.session_state.balance_history) > 1:
        fig = px.line(st.session_state.balance_history, 
                      title="Total Fund Value (Cumulative)", 
                      labels={'value': 'Cash (₹)', 'index': 'Trade #'},
                      template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
    else:
        st.write("No closed trades recorded yet.")
    st.caption(DISCLAIMER)
