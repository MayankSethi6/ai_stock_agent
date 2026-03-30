import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha Terminal", layout="wide", page_icon="🇮🇳")

# Official March 2026 NSE Lot Sizes
NSE_LOTS = {
    "NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "MIDCPNIFTY": 120,
    "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400
}

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

# --- 2. SEARCH & PAYOFF LOGIC ---
def nse_friendly_search(query):
    q = query.upper().strip()
    if q in ["NIFTY", "NIFTY 50", "NIFTY50"]:
        return {"symbol": "^NSEI", "name": "Nifty 50 Index"}
    if q in ["BANKNIFTY", "BANK NIFTY"]:
        return {"symbol": "^NSEBANK", "name": "Nifty Bank Index"}
    
    try:
        search = yf.Search(q + ".NS", max_results=3)
        for res in search.quotes:
            if res['symbol'].endswith(".NS") or res.get('exchDisp') == "NSE":
                return {"symbol": res['symbol'], "name": res.get('shortname', res['symbol'])}
        if "." not in q and len(q) <= 10:
            return {"symbol": q + ".NS", "name": q}
    except:
        return None
    return None

def plot_payoff(mode, opt_type, strike, premium, qty):
    # Dynamic price range for x-axis
    x = np.linspace(strike * 0.85, strike * 1.15, 100)
    if mode == "Cash/Spot":
        y = (x - strike) * qty
    else:
        if "CE" in opt_type:
            y = (np.maximum(x - strike, 0) - premium) * qty
        else:
            y = (np.maximum(strike - x, 0) - premium) * qty
            
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, name="Payoff", line=dict(color='#00FFCC', width=3),
                             fill='tozeroy', fillcolor='rgba(0, 255, 204, 0.1)'))
    fig.add_hline(y=0, line_dash="dash", line_color="white", opacity=0.5)
    
    fig.update_layout(
        title="Strategy Payoff Projection",
        template="plotly_dark",
        xaxis_title="Price (₹)",
        yaxis_title="P&L (₹)",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20)
    )
    return fig

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Fund Management")
    st.metric("Capital", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🗑️ Reset All Sessions"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.portfolio, st.session_state.pnl_ledger = [], []
        if "curr_trade" in st.session_state: del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Friendly Search", value="Nifty")
    asset = nse_friendly_search(user_query)
    
    if asset:
        st.success(f"Locked: {asset['name']}")
        clean_key = asset['symbol'].replace(".NS","").replace("^","").replace("NSEI","NIFTY").replace("NSEBANK","BANKNIFTY")
        lot_size = NSE_LOTS.get(clean_key, 1)
        lots = st.number_input(f"Lots (Size: {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run AI Manager Intel"):
            with st.spinner("Analyzing Market Data..."):
                tk = yf.Ticker(asset['symbol'])
                hist = tk.history(period="5d")
                if not hist.empty:
                    # FORCE FLOAT CONVERSION HERE
                    cp = float(hist['Close'].iloc[-1])
                    prompt = f"Hedge Fund Manager. Asset: {asset['name']} @ {cp}. Give sentiment and strike recommendation."
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    
                    st.session_state.curr_trade = {
                        "ticker": asset['symbol'], "name": asset['name'], 
                        "market_price": cp, "qty": lots * lot_size, "report": res.text
                    }
                    st.rerun()

# --- 4. TABS ---
t_ai, t_desk, t_perf = st.tabs(["🧠 AI Strategy", "🚀 Execution Desk", "📊 Performance"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
    else: st.warning("Run 'Manager Intel' in the sidebar.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        # SAFETY CHECK FOR PRICE TYPE
        mkt_price = float(tr.get('market_price', 0))
        
        st.subheader("Order Configuration")
        mode = st.radio("Instrument", ["Cash/Spot", "Options (CE/PE)"], horizontal=True)
        
        if mode == "Options (CE/PE)":
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Type", ["CE (Call)", "PE (Put)"])
            # ERROR FIXED: Explicit type casting and rounding
            suggested_strike = int(round(mkt_price / 50) * 50) if mkt_price > 0 else 0
            strike_price = c2.number_input("Strike Price", value=suggested_strike, step=50)
            entry_price = c3.number_input("Premium (Limit)", value=100.0)
            
            st.plotly_chart(plot_payoff(mode, opt_type, strike_price, entry_price, tr['qty']), use_container_width=True)
            display_name = f"{tr['name']} {strike_price} {opt_type[:2]}"
            margin_mult = 1.0
        else:
            c1, c2 = st.columns(2)
            entry_price = c1.number_input("Entry Price (Limit)", value=mkt_price)
            st.plotly_chart(plot_payoff(mode, None, entry_price, 0, tr['qty']), use_container_width=True)
            display_name = f"{tr['name']} (Cash)"
            margin_mult = 0.10

        req_margin = entry_price * tr['qty'] * margin_mult
        st.metric(f"Margin Required", f"₹{req_margin:,.2f}")

        if st.button("CONFIRM EXECUTION"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": display_name, "entry": entry_price, "qty": tr['qty'], "margin": req_margin
                })
                st.rerun()
            else: st.error("Insufficient Funds!")

    st.divider()
    for i, pos in enumerate(st.session_state.portfolio):
        with st.expander(f"{pos['name']} | Qty: {pos['qty']}"):
            if st.button("SQUARE OFF", key=f"ex_{i}"):
                st.session_state.fund_balance += pos['margin']
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": 0.0})
                st.session_state.portfolio.pop(i)
                st.rerun()

with t_perf:
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
