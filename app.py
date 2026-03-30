import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - Executive Fund Desk", layout="wide", page_icon="🏛️")

USD_INR_2026 = 87.50
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "RELIANCE": 250, "SBIN": 1500, "TCS": 175, "INFY": 400}

# Initialize Gemini Client
if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
# This block ensures all variables exist before the UI runs
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

def universal_search(query):
    try:
        search = yf.Search(query, max_results=1)
        if search.quotes:
            q = search.quotes[0]
            tk = yf.Ticker(q['symbol'])
            return {
                "symbol": q['symbol'], 
                "name": q.get('shortname', q['symbol']),
                "sector": tk.info.get('sector', 'Uncategorized'),
                "currency": tk.info.get('currency', 'INR')
            }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🏢 Fund Assets")
    st.metric("Net Liquid Capital", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🗑️ Wipe & Reset Terminal"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        if "curr_trade" in st.session_state: del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Global Search (Company/Index)", value="Nifty 50")
    asset = universal_search(user_query)
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        is_nse = ".NS" in asset['symbol']
        lot_size = NSE_LOTS.get(asset['symbol'].split(".")[0], 1) if is_nse else 1
        lots = st.number_input(f"Execution Size (Lots of {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run Manager Intel"):
            with st.spinner("AI Quant Analysis in Progress..."):
                tk = yf.Ticker(asset['symbol'])
                # Get the absolute latest price
                hist = tk.history(period="1d")
                if not hist.empty:
                    cp = float(hist['Close'].iloc[-1])
                    news = [n['title'] for n in tk.news[:3]]
                    prompt = f"Hedge Fund Manager. Asset: {asset['name']} @ {cp}. News: {news}. Strategy?"
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    
                    # SAVE TO STATE (This prevents the error!)
                    st.session_state.curr_trade = {
                        "ticker": asset['symbol'], "name": asset['name'], "sector": asset['sector'],
                        "price": cp, "qty": lots * lot_size, "report": res.text, "currency": asset['currency']
                    }
                    st.rerun()

# --- 4. DASHBOARD TABS ---
tab_ai, tab_trade, tab_report = st.tabs(["🧠 Alpha Strategy", "🚀 Execution Desk", "📜 Fund Performance"])

with tab_ai:
    # FIXED: Added the check to prevent the KeyError
    if "curr_trade" in st.session_state:
        st.subheader(f"Strategy Briefing: {st.session_state.curr_trade['name']}")
        st.info(st.session_state.curr_trade['report'])
    else:
        st.warning("Please search for an asset in the sidebar and click 'Run Manager Intel' to generate a report.")

with tab_trade:
    # Check if a trade is ready to be placed
    if "curr_trade" in st.session_state:
        t = st.session_state.curr_trade
        fx = USD_INR_2026 if t['currency'] == 'USD' else 1
        price_inr = t['price'] * fx
        margin = price_inr * t['qty'] * 0.10
        
        st.subheader("Dynamic Order Entry")
        c1, c2, c3 = st.columns(3)
        sl = c1.number_input("Stop Loss (Price)", value=t['price']*0.97)
        tp = c2.number_input("Take Profit (Price)", value=t['price']*1.06)
        c3.metric("Margin Required", f"₹{margin:,.2f}")

        if st.button("CONFIRM INSTITUTIONAL BUY"):
            is_open, _ = get_market_status()
            if not is_open:
                st.error("Market is currently CLOSED. Orders blocked.")
            elif st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "name": t['name'], "ticker": t['ticker'], "entry": t['price'],
                    "qty": t['qty'], "margin": margin, "sl": sl, "tp": tp,
                    "currency": t['currency'], "sector": t['sector'], 
                    "time": datetime.now().strftime("%H:%M")
                })
                st.toast("Trade Executed!")
                st.rerun()
            else: st.error("Margin Call: Insufficient Funds.")

    st.divider()
    st.subheader("📂 Active Portfolio Risk")
    if st.session_state.portfolio and st.button("🔄 Sync P&L & Check Exit Levels"): st.rerun()

    for i, pos in enumerate(st.session_state.portfolio):
        # Fetching fresh LTP for active positions
        live_data = yf.Ticker(pos['ticker']).history(period="1d")
        if not live_data.empty:
            live_p = float(live_data['Close'].iloc[-1])
            fx = USD_INR_2026 if pos['currency'] == 'USD' else 1
            pnl = (live_p - pos['entry']) * pos['qty'] * fx
            
            status = "🟢 ACTIVE"
            if live_p <= pos['sl']: status = "🛑 STOP LOSS TRIGGERED"
            elif live_p >= pos['tp']: status = "🎯 TAKE PROFIT TRIGGERED"

            with st.expander(f"{pos['name']} | {status} | P&L: ₹{pnl:,.2f}", expanded=(status != "🟢 ACTIVE")):
                st.write(f"Entry: {pos['entry']} | Current: {live_p} | Sector: {pos['sector']}")
                if st.button("EXIT TRADE", key=f"exit_{i}") or status != "🟢 ACTIVE":
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.balance_history.append(st.session_state.fund_balance)
                    st.session_state.pnl_ledger.append({
                        "Date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "Asset": pos['name'], "Sector": pos['sector'], "P&L": round(pnl, 2)
                    })
                    st.session_state.portfolio.pop(i)
                    st.rerun()

with tab_report:
    if st.session_state.pnl_ledger:
        df = pd.DataFrame(st.session_state.pnl_ledger)
        st.plotly_chart(px.line(y=st.session_state.balance_history, title="Equity Curve", template="plotly_dark"), use_container_width=True)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Download Report", df.to_csv().encode('utf-8'), "performance.csv", "text/csv")
    else:
        st.info("No realized trades in the ledger.")
