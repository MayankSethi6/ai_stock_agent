import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import plotly.express as px
from datetime import datetime, time
import pytz

# --- 1. CONFIG ---
st.set_page_config(page_title="AI Alpha - Global Search Desk", layout="wide", page_icon="🏛️")

# March 2026 NSE Lot Sizes (Fallback for Indian Stocks)
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "RELIANCE": 250, "SBIN": 1500, "TCS": 175, "INFY": 400}

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

# --- 2. THE SEARCH ENGINE ---
def universal_search(query):
    """Searches Yahoo Finance for the best matching ticker."""
    try:
        search = yf.Search(query, max_results=1)
        if search.quotes:
            res = search.quotes[0]
            return {
                "symbol": res['symbol'],
                "shortname": res.get('shortname', res['symbol']),
                "exchange": res.get('exchDisp', 'Unknown')
            }
    except: return None
    return None

def get_sentiment_analysis(ticker, name):
    """Uses Gemini to analyze recent news headlines for the stock."""
    try:
        tk = yf.Ticker(ticker)
        news = tk.news[:5] # Get 5 latest headlines
        headlines = [n['title'] for n in news]
        
        prompt = f"""
        Analyze these headlines for {name} ({ticker}): {headlines}
        1. Summarize the sentiment (Bullish/Bearish/Neutral).
        2. Give a 'Vibe Score' from 1-10 (10 is extremely positive).
        3. Be brief (2 sentences).
        """
        res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
        return res.text
    except: return "Sentiment data unavailable."

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("💳 Fund: ₹{:,.2f}".format(st.session_state.fund_balance))
    
    st.subheader("🔍 Universal Search")
    user_query = st.text_input("Type Company Name (e.g. Zomato, Nvidia, Apple)", value="Reliance")
    
    with st.spinner("Searching..."):
        asset_info = universal_search(user_query)
    
    if asset_info:
        st.success(f"Found: {asset_info['shortname']} ({asset_info['symbol']})")
        st.caption(f"Exchange: {asset_info['exchange']}")
        
        # Determine Lot Size (Default to 1 for US/Global stocks)
        base_ticker = asset_info['symbol'].split(".")[0]
        lot_size = NSE_LOTS.get(base_ticker, 1) if ".NS" in asset_info['symbol'] else 1
        
        lots = st.number_input(f"Quantity (Lot Size: {lot_size})", min_value=1, value=1)
        
        if st.button("Analyze & Fetch News"):
            with st.spinner("Reading Headlines..."):
                tk = yf.Ticker(asset_info['symbol'])
                cp = tk.history(period="1d")['Close'].iloc[-1]
                sentiment = get_sentiment_analysis(asset_info['symbol'], asset_info['shortname'])
                
                st.session_state.curr_trade = {
                    "ticker": asset_info['symbol'], "name": asset_info['shortname'],
                    "price": float(cp), "qty": lots * lot_size, "sentiment": sentiment
                }
    else:
        st.error("No asset found. Try a clearer name.")

# --- 4. MAIN TABS ---
tab_strat, tab_desk, tab_ledger = st.tabs(["📊 AI Sentiment", "🚀 Trading Desk", "📈 Performance"])

with tab_strat:
    if "curr_trade" in st.session_state:
        st.subheader(f"Institutional Intel: {st.session_state.curr_trade['name']}")
        st.markdown(st.session_state.curr_trade['sentiment'])
        st.metric("Live Market Price", f"₹{st.session_state.curr_trade['price']:,.2f}")
    else:
        st.info("Search for a company in the sidebar to begin.")

with tab_desk:
    if "curr_trade" in st.session_state:
        trade = st.session_state.curr_trade
        margin_req = trade['price'] * trade['qty'] * 0.10
        
        st.write(f"Executing **{trade['qty']} units** of {trade['name']}")
        st.write(f"Margin Required: ₹{margin_req:,.2f}")
        
        if st.button("CONFIRM BUY ORDER"):
            if st.session_state.fund_balance >= margin_req:
                st.session_state.fund_balance -= margin_req
                st.session_state.portfolio.append({
                    "name": trade['name'], "ticker": trade['ticker'],
                    "entry": trade['price'], "qty": trade['qty'], "margin": margin_req
                })
                st.toast("Order Filled!")
                st.rerun()
            else: st.error("Insufficient Capital.")

    st.divider()
    st.subheader("📂 Open Positions")
    for i, pos in enumerate(st.session_state.portfolio):
        # Quick price sync
        live_p = yf.Ticker(pos['ticker']).history(period="1d")['Close'].iloc[-1]
        pnl = (live_p - pos['entry']) * pos['qty']
        
        with st.expander(f"{pos['name']} | P&L: ₹{pnl:,.2f}"):
            st.write(f"Entry: {pos['entry']} | Current: {live_p}")
            if st.button("Close Position", key=f"close_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.balance_history.append(st.session_state.fund_balance)
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": pnl})
                st.session_state.portfolio.pop(i)
                st.rerun()

with tab_ledger:
    if len(st.session_state.balance_history) > 1:
        fig = px.line(y=st.session_state.balance_history, title="Equity Curve", template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
