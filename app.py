import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime

# --- 1. CONFIG & STYLE ---
st.set_page_config(page_title="AI Alpha - NSE Hedge Fund Agent", layout="wide", page_icon="🏛️")

# Restrict to NSE only
NSE_TICKERS = ["NIFTY.NS", "^NSEI", "BANKNIFTY.NS", "^NSEBANK", "RELIANCE.NS", "HDFCBANK.NS", "SBIN.NS", "TCS.NS", "INFY.NS"]

DISCLAIMER = "⚠️ **Institutional Disclosure:** Professional Trading involves capital risk. 2026 NSE Lot Sizes applied. Not a SEBI advisory."

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize Paper Trading Session
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [] # List of dicts: {ticker, lots, entry, current, status}

# --- 2. THE 2026 NSE QUANT ENGINE ---
def get_nse_lot(ticker):
    """Accurate 2026 NSE Revised Lot Sizes."""
    lot_map = {
        "NIFTY.NS": 65, "^NSEI": 65,
        "BANKNIFTY.NS": 30, "^NSEBANK": 30,
        "FINNIFTY.NS": 60, "RELIANCE.NS": 500,
        "HDFCBANK.NS": 550, "SBIN.NS": 1500
    }
    return lot_map.get(ticker.upper(), 100)

def fund_manager_strategy(ticker, price, rsi, volume_surge):
    """Gemini-3-Flash reasoning as a 10-year Hedge Fund Vet."""
    prompt = f"""
    Act as a Hedge Fund Manager with 10+ years of consistent profit. 
    Context: NSE Market, March 2026. Ticker: {ticker} at ₹{price}.
    Technicals: RSI is {rsi:.1f}. Volume Surge: {volume_surge}.
    
    Instruction: Provide a high-conviction scalp strategy (2-5% target). 
    Focus on risk-mitigation. If the setup is weak, tell the user to 'STAY IN CASH'.
    Include:
    1. Exact Buy/Sell points for an ATM Call/Put.
    2. The 'Stop-Out' time (minutes) before Theta decay ruins the trade.
    """
    res = st.session_state.client.models.generate_content(
        model="gemini-3-flash-preview", 
        contents=[prompt]
    )
    return res.text

# --- 3. UI LAYOUT ---
st.title("🏛️ AI Alpha: NSE Institutional Dashboard")

with st.sidebar:
    st.header("🏢 Fund Execution Desk")
    selected_ticker = st.selectbox("Select NSE Asset", NSE_TICKERS)
    lot_count = st.number_input("Number of Lots", min_value=1, max_value=50, value=1)
    
    if st.button("Generate Alpha"):
        with st.spinner("Analyzing Market Microstructure..."):
            tk = yf.Ticker(selected_ticker)
            hist = tk.history(period="5d", interval="15m")
            if not hist.empty:
                curr_price = hist['Close'].iloc[-1]
                # Simple RSI
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi = 100 - (100 / (1 + (gain/loss))).iloc[-1]
                vol_surge = hist['Volume'].iloc[-1] > (hist['Volume'].rolling(20).mean().iloc[-1] * 1.5)
                
                analysis = fund_manager_strategy(selected_ticker, curr_price, rsi, vol_surge)
                
                st.session_state.update({
                    "curr_data": {"ticker": selected_ticker, "price": curr_price, "lots": lot_count, "analysis": analysis}
                })

# --- 4. TABS & PAPER TRADING ---
tab_stock, tab_ai, tab_paper = st.tabs(["📊 Market Watch", "🧠 Manager Recommendation", "💰 Live Paper Trade"])

if "curr_data" in st.session_state:
    with tab_stock:
        st.subheader(f"Institutional View: {st.session_state.curr_data['ticker']}")
        # Placeholder for price chart
        st.write(f"Current Spot Price: ₹{st.session_state.curr_data['price']:.2f}")
        st.caption(DISCLAIMER)

    with tab_ai:
        st.subheader("💡 Manager's High-Conviction Report")
        st.write(st.session_state.curr_data['analysis'])
        st.caption(DISCLAIMER)

    with tab_paper:
        st.subheader("🚀 Live Execution (Paper Trading)")
        lot_size = get_nse_lot(st.session_state.curr_data['ticker'])
        total_qty = lot_size * st.session_state.curr_data['lots']
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Asset:** {st.session_state.curr_data['ticker']}")
            st.write(f"**Total Quantity:** {total_qty} units")
            if st.button("BUY NOW (Paper Order)"):
                st.session_state.portfolio.append({
                    "ticker": st.session_state.curr_data['ticker'],
                    "entry": st.session_state.curr_data['price'],
                    "qty": total_qty,
                    "time": datetime.now().strftime("%H:%M:%S")
                })
        
        with col2:
            st.write("📂 **Active Positions**")
            if not st.session_state.portfolio:
                st.info("No active trades.")
            for trade in st.session_state.portfolio:
                st.success(f"{trade['ticker']} | Entry: {trade['entry']} | Qty: {trade['qty']} | Time: {trade['time']}")
        st.caption(DISCLAIMER)
