import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
from datetime import datetime
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Institutional Live Sync", layout="wide", page_icon="🏛️")

# March 2026 NSE F&O Master List
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
    st.session_state.fund_balance = 1000000.0  # 10 Lakhs Initial
if 'portfolio' not in st.session_state:
    st.session_state.portfolio = []
if 'pnl_ledger' not in st.session_state:
    st.session_state.pnl_ledger = []

# --- 2. UTILITIES ---

def get_market_status():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    m_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    m_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    is_open = now.weekday() < 5 and m_open <= now <= m_close
    return is_open, now.strftime("%H:%M:%S")

def get_live_price(ticker):
    """Fetches the latest single price point."""
    try:
        data = yf.Ticker(ticker).history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
        return None
    except:
        return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Fund Management")
    st.metric("Liquid Paper Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🔄 Reset Global Account"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.portfolio = []
        st.session_state.pnl_ledger = []
        st.rerun()
    
    st.divider()
    st.header("⚡ Order Entry")
    ticker_choice = st.selectbox("Asset (Lot Size)", options=list(NSE_FO_MASTER.keys()))
    lots = st.number_input("Lots", min_value=1, max_value=100, value=1)
    
    market_open, current_time = get_market_status()
    if market_open: st.success(f"🟢 NSE Open: {current_time}")
    else: st.error(f"🔴 NSE Closed: {current_time}")

    if st.button("Generate Alpha Strategy"):
        with st.spinner("Analyzing Market Microstructure..."):
            tk = yf.Ticker(ticker_choice)
            hist = tk.history(period="5d", interval="15m")
            if not hist.empty:
                cp = float(hist['Close'].iloc[-1])
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi_val = 100 - (100 / (1 + (gain/loss))).iloc[-1]
                
                # Hedge Fund Vet Persona
                prompt = f"""
                You are a Senior Hedge Fund Manager with 10+ years of profit. 
                Ticker: {ticker_choice} @ ₹{cp}. RSI: {rsi_val:.2f}. 
                Provide a ruthless 2-5% profit scalp strategy. 
                Include exact entry/target and a 'Time-Stop' (minutes). 
                If the RSI is extreme, advise 'NO TRADE'.
                """
                res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                st.session_state.curr_trade = {"ticker": ticker_choice, "price": cp, "lots": lots, "report": res.text}

# --- 4. MAIN TABS ---
tab_strat, tab_desk, tab_ledger = st.tabs(["🧠 AI Strategy", "🚀 Trading Desk", "📜 P&L Ledger"])

with tab_strat:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy: {st.session_state.curr_trade['ticker']}")
        st.info(st.session_state.curr_trade['report'])
    else:
        st.write("Select an asset and click 'Generate Alpha Strategy'.")
    st.caption(DISCLAIMER)

with tab_desk:
    # Order Execution Logic
    if "curr_trade" in st.session_state:
        qty = NSE_FO_MASTER[st.session_state.curr_trade['ticker']] * st.session_state.curr_trade['lots']
        margin = float(st.session_state.curr_trade['price'] * qty * 0.10) # 10% Margin Buying
        
        st.markdown(f"**Action:** Buy {qty} units of {st.session_state.curr_trade['ticker']}")
        if st.button("EXECUTE BUY ORDER"):
            if not market_open: st.error("Market is currently CLOSED.")
            elif st.session_state.fund_balance < margin: st.error("Insufficient Fund Balance!")
            else:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "ticker": st.session_state.curr_trade['ticker'], 
                    "entry": float(st.session_state.curr_trade['price']),
                    "qty": int(qty), "margin": margin, "time": current_time
                })
                st.toast("Order Filled at Market.")
                st.rerun()

    st.divider()
    
    # Live Position Monitor
    col_title, col_sync = st.columns([3, 1])
    col_title.subheader("📂 Active Positions")
    if st.session_state.portfolio and col_sync.button("🔄 Sync All Prices"):
        st.rerun() # Refreshing causes get_live_price to re-run for all rows

    if not st.session_state.portfolio:
        st.info("No active exposure in the book.")
    else:
        for i, pos in enumerate(st.session_state.portfolio):
            current_p = get_live_price(pos['ticker'])
            if current_p:
                unrealized_pnl = float((current_p - pos['entry']) * pos['qty'])
                pnl_color = "green" if unrealized_pnl >= 0 else "red"
                
                with st.expander(f"{pos['ticker']} | Live P&L: ₹{unrealized_pnl:,.2f}", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Entry Price", f"₹{pos['entry']:,.2f}")
                    c2.metric("LTP (Last Traded)", f"₹{current_p:,.2f}")
                    c3.markdown(f"**Current P&L:** <span style='color:{pnl_color}'>₹{unrealized_pnl:,.2f}</span>", unsafe_allow_html=True)
                    
                    if st.button("SELL & WRITE OFF", key=f"sell_{i}"):
                        # Final Write-off: Return margin + P&L to balance
                        st.session_state.fund_balance += (pos['margin'] + unrealized_pnl)
                        st.session_state.pnl_ledger.append({
                            "Asset": pos['ticker'], "Entry": pos['entry'], "Exit": current_p,
                            "Qty": pos['qty'], "Net P&L": unrealized_pnl, "Time": pos['time']
                        })
                        st.session_state.portfolio.pop(i)
                        st.rerun()

with tab_ledger:
    st.subheader("📊 Closed Trade Performance")
    if st.session_state.pnl_ledger:
        df = pd.DataFrame(st.session_state.pnl_ledger)
        total_realized = df['Net P&L'].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("Realized P&L (Total)", f"₹{total_realized:,.2f}", delta=f"{total_realized:,.2f}")
        m2.metric("Current Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
        
        st.table(df)
    else:
        st.write("No closed trades in the ledger yet.")
    st.caption(DISCLAIMER)
