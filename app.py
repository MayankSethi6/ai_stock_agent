import streamlit as st
from jugaad_data.nse import NSELive
from google import genai
import pandas as pd
from datetime import datetime, date
import time

# --- 1. INITIALIZATION ---
st.set_page_config(page_title="NSE Alpha - Jugaad Edition", layout="wide")

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize State
for key, val in {
    'fund_balance': 1000000.0, 
    'portfolio': [], 
    'history': [], 
    'active_asset': None, 
    'ai_intel': None
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. JUGAAD-DATA ENGINE ---
n = NSELive()

def fetch_live_price(symbol, is_option=False, strike=None, otype=None, expiry=None):
    """Fetches live LTP using Jugaad-Data's direct NSE bridge."""
    try:
        if not is_option:
            # For Equity/Indices
            if symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY"]:
                return n.live_index(symbol.replace("NIFTY", "NIFTY 50").replace("BANKNIFTY", "NIFTY BANK"))['data'][0]['lastPrice']
            return n.stock_quote(symbol)['priceInfo']['lastPrice']
        else:
            # For Options: Fetch the full chain and filter
            chain = n.index_option_chain(symbol) if symbol in ["NIFTY", "BANKNIFTY"] else n.stock_option_chain(symbol)
            for item in chain['records']['data']:
                if item['strikePrice'] == strike and item['expiryDate'] == expiry.strftime('%d-%b-%Y'):
                    return item[otype]['lastPrice']
    except Exception as e:
        st.error(f"Sync Error: {e}")
    return 0.0

# --- 3. SIDEBAR: MARGIN & SEARCH ---
with st.sidebar:
    st.header("🇮🇳 NSE Alpha Terminal")
    st.metric("Available Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    # Real-time Margin Monitor
    blocked_margin = sum([p['margin'] for p in st.session_state.portfolio])
    st.write(f"**Blocked Margin:** ₹{blocked_margin:,.2f}")
    st.progress(min(blocked_margin / 1000000.0, 1.0))
    
    st.divider()
    search_query = st.text_input("Enter Symbol (e.g. NIFTY, RELIANCE)", value="NIFTY").upper()
    if st.button("🔍 Fixate Asset", use_container_width=True):
        price = fetch_live_price(search_query)
        st.session_state.active_asset = {"symbol": search_query, "price": price}
        st.success(f"Locked on {search_query} @ {price}")

    if st.session_state.active_asset:
        if st.button("🔥 RUN AI QUANT INTEL", type="primary", use_container_width=True):
            asset = st.session_state.active_asset
            prompt = f"NSE AI: {asset['symbol']} is at {asset['price']}. Recommend a high-probability option strategy."
            res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
            st.session_state.ai_intel = res.text

# --- 4. MAIN INTERFACE ---
tabs = st.tabs(["🧠 AI Strategy", "🚀 Execution Desk", "📊 Active Portfolio", "📜 Trade History"])

with tabs[0]:
    if st.session_state.ai_intel:
        st.markdown(st.session_state.ai_intel)
    else: st.info("Use the sidebar to search and run AI analysis.")

with tabs[1]:
    if st.session_state.active_asset:
        st.subheader(f"Trading: {st.session_state.active_asset['symbol']}")
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Strategy", ["Naked Buy", "Naked Sell", "Spread Leg"])
        strike = c2.number_input("Strike", value=int(st.session_state.active_asset['price']), step=50)
        otype = c3.selectbox("Type", ["CE", "PE"])
        
        c4, c5 = st.columns(2)
        expiry = c4.date_input("Expiry", value=date(2026, 4, 30))
        lots = c5.number_input("Lots", min_value=1, value=1)
        
        # Calculate Costs
        l_price = fetch_live_price(st.session_state.active_asset['symbol'], True, strike, otype, expiry) or 100.0
        qty = lots * (65 if "NIFTY" in st.session_state.active_asset['symbol'] else 250)
        margin = (185000 * lots) if mode == "Naked Sell" else (l_price * qty)
        
        st.info(f"Current Premium: ₹{l_price} | Est. Margin Required: ₹{margin:,.2f}")
        
        if st.button("CONFIRM EXECUTION", use_container_width=True):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "symbol": st.session_state.active_asset['symbol'], "type": f"{strike} {otype}",
                    "entry": l_price, "qty": qty, "margin": margin, "mode": mode,
                    "strike": strike, "otype": otype, "expiry": expiry
                })
                st.toast("Order Placed Successfully!")
                st.rerun()

with tabs[2]:
    col_head, col_sync = st.columns([4, 1])
    col_head.subheader("Live Positions")
    if col_sync.button("🔄 SYNC P/L & PRICES"): st.rerun()
    
    total_unrealized = 0
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            # Live Fetch for each position
            current_p = fetch_live_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry']) or pos['entry']
            pnl = (current_p - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - current_p) * pos['qty']
            total_unrealized += pnl
            
            with st.expander(f"{pos['symbol']} {pos['type']} | P/L: ₹{pnl:,.2f}"):
                st.write(f"Mode: {pos['mode']} | Entry: {pos['entry']} | LTP: {current_p}")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Trade": f"{pos['symbol']} {pos['type']}", "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.divider()
        st.metric("Total Unrealized", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else: st.info("No open positions.")

with tabs[3]:
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
        st.metric("Total Realized Profit", f"₹{sum(x['P&L'] for x in st.session_state.history):,.2f}")
