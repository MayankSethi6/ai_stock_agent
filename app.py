import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, date
import numpy as np
from scipy.stats import norm

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="AI Alpha - F&O Desk", layout="wide", page_icon="📈")

USD_INR_2026 = 87.50
# 2026 Revised Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 1500}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'balance_history': [1000000.0], 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. OPTION UTILITIES (Greeks Lite) ---
def get_option_recommendation(ticker_symbol, market_price, ai_view):
    """Simple Logic to recommend an option strategy based on AI sentiment"""
    sentiment = ai_view.lower()
    if "bullish" in sentiment or "buy" in sentiment:
        strike = round(market_price / 50) * 50 # ATM Strike
        return {"type": "CE", "strike": strike, "strategy": "Long Call (Aggressive Bullish)"}
    elif "bearish" in sentiment or "sell" in sentiment:
        strike = round(market_price / 50) * 50
        return {"type": "PE", "strike": strike, "strategy": "Long Put (Aggressive Bearish)"}
    return {"type": "CE", "strike": market_price, "strategy": "Neutral - Wait for Signal"}

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Institutional Capital")
    st.metric("Net Liquidity", f"₹{st.session_state.fund_balance:,.2f}")
    
    user_query = st.text_input("Asset Search", value="NIFTY 50")
    # Universal Search Logic
    search = yf.Search(user_query, max_results=1)
    asset = None
    if search.quotes:
        q = search.quotes[0]
        asset = {"symbol": q['symbol'], "name": q.get('shortname', q['symbol']), "currency": "INR" if ".NS" in q['symbol'] else "USD"}
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        if st.button("🔥 Run Manager Intel"):
            with st.spinner("Analyzing Global Macros..."):
                tk = yf.Ticker(asset['symbol'])
                cp = tk.history(period="1d")['Close'].iloc[-1]
                prompt = f"Hedge Fund Manager view on {asset['name']} at {cp}. Give a 1-sentence sentiment (Bullish/Bearish) and why."
                res = st.session_state.client.models.generate_content(model="gemini-2.0-flash", contents=[prompt])
                
                st.session_state.curr_trade = {
                    "ticker": asset['symbol'], "name": asset['name'], 
                    "market_price": cp, "report": res.text, "currency": asset['currency']
                }
                st.rerun()

# --- 4. TABS ---
tab_ai, tab_opt_rec, tab_trade, tab_perf = st.tabs(["🧠 AI Strategy", "🎯 Option Recommendations", "🚀 Execution Desk", "📊 Fund Performance"])

with tab_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Search an asset and run Intel first.")

with tab_opt_rec:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        rec = get_option_recommendation(tr['ticker'], tr['market_price'], tr['report'])
        
        st.subheader(f"Strategy: {rec['strategy']}")
        c1, c2 = st.columns(2)
        c1.metric("Recommended Strike", f"{rec['strike']} {rec['type']}")
        c2.metric("Underlying Price", f"₹{tr['market_price']:,.2f}")
        st.write("💡 *Note: Recommendations are based on AI sentiment analysis and ATM (At-the-money) strike selection.*")
    else: st.info("Run AI Strategy to see Option Recommendations.")

with tab_trade:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Order Configuration")
        
        trade_mode = st.radio("Instrument Type", ["Equity (Spot)", "Options (F&O)"], horizontal=True)
        
        # Shared Configuration
        lot_size = NSE_LOTS.get(tr['ticker'].replace(".NS", ""), 1)
        lots = st.number_input(f"Quantity (Lots of {lot_size})", min_value=1, value=1)
        total_qty = lots * lot_size
        
        if trade_mode == "Equity (Spot)":
            entry_price = st.number_input("Limit Price", value=float(tr['market_price']))
            margin_pct = 0.20 # 20% for stocks
        else:
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Option Type", ["CE", "PE"])
            strike = c2.number_input("Strike Price", value=round(tr['market_price']/50)*50)
            entry_price = c3.number_input("Option Premium (Price)", value=100.0) # Default premium
            margin_pct = 1.0 # Options buying requires 100% premium upfront
            
        sl = st.number_input("Stop Loss", value=entry_price * 0.8)
        tp = st.number_input("Take Profit", value=entry_price * 1.5)
        
        fx = USD_INR_2026 if tr['currency'] == "USD" else 1
        req_capital = (entry_price * fx) * total_qty * margin_pct
        st.metric("Total Capital Required", f"₹{req_capital:,.2f}")
        
        if st.button("EXECUTE TRADE"):
            if st.session_state.fund_balance >= req_capital:
                st.session_state.fund_balance -= req_capital
                st.session_state.portfolio.append({
                    "name": f"{tr['name']} {strike if trade_mode=='Options' else ''} {opt_type if trade_mode=='Options' else ''}",
                    "ticker": tr['ticker'], "entry": entry_price, "qty": total_qty, 
                    "sl": sl, "tp": tp, "type": trade_mode, "margin": req_capital
                })
                st.toast("Position Opened!")
                st.rerun()
            else: st.error("Insufficient Funds.")

    st.divider()
    st.subheader("📂 Active Positions")
    for i, pos in enumerate(st.session_state.portfolio):
        # Simplification: Options P&L is tracked against their premium entry
        # In a real app, you'd fetch the specific option contract symbol LTP
        with st.expander(f"{pos['name']} ({pos['type']})"):
            st.write(f"Entry: {pos['entry']} | Qty: {pos['qty']} | Capital: ₹{pos['margin']:,.2f}")
            if st.button("EXIT", key=f"exit_{i}"):
                st.session_state.fund_balance += pos['margin'] # Simplified exit at cost for this demo
                st.session_state.portfolio.pop(i)
                st.rerun()
