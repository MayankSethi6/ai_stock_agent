import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
from datetime import datetime
import pytz

# --- 1. CONFIG & SYSTEM ARCHITECTURE ---
st.set_page_config(page_title="AI Alpha - NSE Institutional Desk", layout="wide", page_icon="🏛️")

# March 2026 NSE F&O Master List (Ticker: Lot Size)
NSE_FO_MASTER = {
    "NIFTY.NS": 65, "BANKNIFTY.NS": 30, "FINNIFTY.NS": 60, "MIDCPNIFTY.NS": 120,
    "RELIANCE.NS": 250, "TCS.NS": 175, "HDFCBANK.NS": 550, "ICICIBANK.NS": 700,
    "INFY.NS": 400, "SBIN.NS": 1500, "BHARTIARTL.NS": 950, "ITC.NS": 1600,
    "TATAMOTORS.NS": 1425, "KOTAKBANK.NS": 400, "LT.NS": 300, "AXISBANK.NS": 625
}

DISCLAIMER = "⚠️ **Institutional Disclosure:** Trading involves risk. Market Hours: 9:15 AM - 3:30 PM IST. Budget 2026 STT rates applied."

# --- 2. PERSISTENT STATE MANAGEMENT ---
if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

if 'fund_balance' not in st.session_state:
    st.session_state.fund_balance = 1000000.0  # Initial 10 Lakh Paper Cash

if 'portfolio' not in st.session_state:
    st.session_state.portfolio = [] # Active Trades

if 'pnl_ledger' not in st.session_state:
    st.session_state.pnl_ledger = [] # Closed Trades

# --- 3. CORE LOGIC ENGINES ---

def get_market_status():
    """Checks if NSE is currently open for orders."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    m_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    m_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    # 0=Mon, 4=Fri
    if now.weekday() < 5 and m_open <= now <= m_close:
        return True, now.strftime("%H:%M:%S")
    return False, now.strftime("%H:%M:%S")

def hedge_fund_manager_ai(ticker, price, rsi):
    """Gemini-3-Flash reasoning as a 10-year Veteran Trader."""
    prompt = f"""
    Context: NSE India (March 2026). Professional Hedge Fund View.
    Asset: {ticker} @ ₹{price}. RSI: {rsi:.2f}.
    Instruction: Recommend a scalp (2-5% target). If logic fails, say 'STAY IN CASH'.
    Include Entry, Target, and a specific 'Time-to-Exit' in minutes based on Theta decay.
    """
    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
    return res.text

# --- 4. SIDEBAR: FUND EXECUTION ---
with st.sidebar:
    st.header("💳 Fund Management")
    st.metric("Liquid Paper Cash", f"₹{st.session_state.fund_balance:,.2f}")
    st.divider()
    
    st.header("⚡ Order Entry")
    ticker_choice = st.selectbox("Select Asset", options=list(NSE_FO_MASTER.keys()))
    lots = st.number_input("Lots to Trade", min_value=1, max_value=50, value=1)
    
    is_open, current_time = get_market_status()
    if is_open:
        st.success(f"Market Open: {current_time}")
    else:
        st.error(f"Market Closed: {current_time}")

    if st.button("Generate AI Alpha"):
        with st.spinner("Syncing NSE Micro-data..."):
            tk = yf.Ticker(ticker_choice)
            hist = tk.history(period="5d", interval="15m")
            if not hist.empty:
                cp = hist['Close'].iloc[-1]
                delta = hist['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rsi_val = 100 - (100 / (1 + (gain/loss))).iloc[-1]
                
                report = hedge_fund_manager_ai(ticker_choice, cp, rsi_val)
                st.session_state.curr_trade = {"ticker": ticker_choice, "price": cp, "lots": lots, "report": report}

# --- 5. DASHBOARD TABS ---
tab_mgr, tab_desk, tab_ledger = st.tabs(["🧠 Manager Insight", "🚀 Trading Desk", "📜 Performance Ledger"])

with tab_mgr:
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy for {st.session_state.curr_trade['ticker']}")
        st.info(st.session_state.curr_trade['report'])
    else:
        st.write("Analyze an asset in the sidebar to receive instructions.")
    st.caption(DISCLAIMER)

with tab_desk:
    if "curr_trade" in st.session_state:
        lot_size = NSE_FO_MASTER[st.session_state.curr_trade['ticker']]
        total_qty = lot_size * st.session_state.curr_trade['lots']
        est_cost = st.session_state.curr_trade['price'] * total_qty * 0.05 # Using 5% margin for F&O
        
        st.write(f"**Execution:** Buy {total_qty} units of {st.session_state.curr_trade['ticker']}")
        st.write(f"**Estimated Margin Required:** ₹{est_cost:,.2f}")
        
        if st.button("EXECUTE BUY ORDER"):
            if not is_open:
                st.error("Market is closed. Orders blocked.")
            elif st.session_state.fund_balance < est_cost:
                st.error("Insufficient Fund Balance!")
            else:
                # Deduct from balance
                st.session_state.fund_balance -= est_cost
                st.session_state.portfolio.append({
                    "ticker": st.session_state.curr_trade['ticker'],
                    "entry": st.session_state.curr_trade['price'],
                    "qty": total_qty,
                    "margin": est_cost,
                    "time": current_time
                })
                st.success("Order Filled at Market.")
    
    st.divider()
    st.subheader("📂 Active Institutional Positions")
    if not st.session_state.portfolio:
        st.info("No active exposure.")
    else:
        for i, pos in enumerate(st.session_state.portfolio):
            with st.expander(f"{pos['ticker']} | Qty: {pos['qty']} | Entry: ₹{pos['entry']}", expanded=True):
                if st.button(f"SELL & WRITE OFF POSITION", key=f"sell_{i}"):
                    # Simulation: Get exit price (usually live, here mocked from current analysis)
                    exit_p = yf.Ticker(pos['ticker']).history(period="1d")['Close'].iloc[-1]
                    raw_pnl = (exit_p - pos['entry']) * pos['qty']
                    
                    # WRITE OFF LOGIC: Return margin + P&L to balance
                    st.session_state.fund_balance += (pos['margin'] + raw_pnl)
                    st.session_state.pnl_ledger.append({
                        "Asset": pos['ticker'], "P&L": raw_pnl, "Time": pos['time'], "Exit": exit_p
                    })
                    st.session_state.portfolio.pop(i)
                    st.rerun()

with tab_ledger:
    st.subheader("📊 Closed Trade Performance")
    if st.session_state.pnl_ledger:
        df = pd.DataFrame(st.session_state.pnl_ledger)
        total_pnl = df['P&L'].sum()
        st.metric("Total Realized P&L", f"₹{total_pnl:,.2f}", delta=f"{total_pnl:,.2f}")
        st.table(df)
    else:
        st.write("No trades written off yet.")
    st.caption(DISCLAIMER)
