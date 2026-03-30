import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - F&O Executive Desk", layout="wide", page_icon="📈")

USD_INR_2026 = 87.50
# 2026 Revised Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 1500, "TCS": 175}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {
    'fund_balance': 1000000.0, 
    'balance_history': [1000000.0], 
    'portfolio': [], 
    'pnl_ledger': []
}.items():
    if key not in st.session_state: st.session_state[key] = val

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
                "symbol": q['symbol'], "name": q.get('shortname', q['symbol']),
                "sector": tk.info.get('sector', 'Uncategorized'),
                "currency": tk.info.get('currency', 'INR')
            }
    except: return None

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Fund: ₹{:,.2f}".format(st.session_state.fund_balance))
    if st.button("🔄 Reset Terminal"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.balance_history = [1000000.0]
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        if "curr_trade" in st.session_state: del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Search Asset (e.g. Nifty, Google, SBI)", value="Nifty 50")
    asset = universal_search(user_query)
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        is_nse = ".NS" in asset['symbol']
        lot_size = NSE_LOTS.get(asset['symbol'].split(".")[0].replace("^",""), 1) if is_nse else 1
        lots = st.number_input(f"Lots (Size: {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run Manager Intel"):
            with st.spinner("AI Analysis..."):
                tk = yf.Ticker(asset['symbol'])
                hist = tk.history(period="1d")
                if not hist.empty:
                    cp = float(hist['Close'].iloc[-1])
                    prompt = f"Role: Hedge Fund Manager. Asset: {asset['name']} @ {cp}. Provide 1-sentence sentiment: Bullish, Bearish, or Neutral and specify one target Strike Price for Options."
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    
                    st.session_state.curr_trade = {
                        "ticker": asset['symbol'], "name": asset['name'], "sector": asset['sector'],
                        "market_price": cp, "qty": lots * lot_size, "report": res.text, "currency": asset['currency']
                    }
                    st.rerun()

# --- 4. TABS ---
t_ai, t_opt, t_desk, t_perf = st.tabs(["🧠 AI Strategy", "🎯 Option Recs", "🚀 Trade Desk", "📊 Performance"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Run 'Manager Intel' in sidebar.")

with t_opt:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("🎯 Suggested Option Strategies")
        # Logic to extract strike/type from AI text or suggest ATM
        atm_strike = round(tr['market_price'] / 50) * 50
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🟢 Bullish View")
            st.write(f"**Strategy:** Buy Call (CE)")
            st.code(f"Strike: {atm_strike} CE")
        with c2:
            st.markdown("### 🔴 Bearish View")
            st.write(f"**Strategy:** Buy Put (PE)")
            st.code(f"Strike: {atm_strike} PE")
        st.caption("ATM Strikes are auto-calculated based on current spot price.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Order Configuration")
        
        mode = st.radio("Instrument", ["Equity/Spot", "Options (CE/PE)"], horizontal=True)
        
        col_p, col_sl, col_tp = st.columns(3)
        # Dynamic Price Entry
        entry_price = col_p.number_input("Entry Price (Limit)", value=float(tr['market_price']) if mode=="Equity/Spot" else 100.0)
        sl = col_sl.number_input("Stop Loss", value=entry_price * 0.90)
        tp = col_tp.number_input("Take Profit", value=entry_price * 1.20)
        
        fx = USD_INR_2026 if tr['currency'] == 'USD' else 1
        # Margin: 10% for Equity, 100% for Options (Premium Buying)
        margin_mult = 0.10 if mode == "Equity/Spot" else 1.0
        req_margin = (entry_price * fx) * tr['qty'] * margin_mult
        
        st.metric("Total Margin Required", f"₹{req_margin:,.2f}")

        if st.button("EXECUTE ORDER"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": f"{tr['name']} ({'Opt' if mode=='Options (CE/PE)' else 'Spot'})",
                    "ticker": tr['ticker'], "entry": entry_price, "qty": tr['qty'],
                    "margin": req_margin, "sl": sl, "tp": tp, "currency": tr['currency']
                })
                st.rerun()
            else: st.error("Insufficient Funds.")

    st.divider()
    for i, pos in enumerate(st.session_state.portfolio):
        # Tracking logic
        with st.expander(f"{pos['name']} | Entry: {pos['entry']}"):
            st.write(f"Qty: {pos['qty']} | Margin: ₹{pos['margin']:,.2f}")
            if st.button("EXIT POSITION", key=f"ex_{i}"):
                st.session_state.fund_balance += pos['margin'] # Exit at cost for simulation
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": 0.0})
                st.session_state.portfolio.pop(i)
                st.rerun()

with t_perf:
    if st.session_state.pnl_ledger:
        st.plotly_chart(px.line(st.session_state.balance_history, title="Equity Curve"), use_container_width=True)
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
