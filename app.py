import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime

# --- 1. CONFIG ---
st.set_page_config(page_title="NSE Alpha - Payoff Analytics", layout="wide", page_icon="🇮🇳")

NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 1500, "TCS": 175}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'balance_history': [1000000.0], 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. SEARCH & PAYOFF LOGIC ---
def nse_friendly_search(query):
    q = query.upper().strip()
    if q in ["NIFTY", "NIFTY 50"]: return {"symbol": "^NSEI", "name": "Nifty 50 Index"}
    if q in ["BANKNIFTY", "BANK NIFTY"]: return {"symbol": "^NSEBANK", "name": "Nifty Bank Index"}
    try:
        search = yf.Search(q + " NSE", max_results=2)
        for res in search.quotes:
            if ".NS" in res['symbol']:
                return {"symbol": res['symbol'], "name": res.get('shortname', res['symbol'])}
    except: return None

def plot_payoff(mode, opt_type, strike, premium, qty):
    """Generates an Options Payoff Chart."""
    x = np.linspace(strike * 0.85, strike * 1.15, 100)
    if mode == "Cash/Spot":
        y = (x - strike) * qty
    else:
        if "CE" in opt_type:
            y = (np.maximum(x - strike, 0) - premium) * qty
        else:
            y = (np.maximum(strike - x, 0) - premium) * qty
            
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=y, name="Payoff", line=dict(color='#00FFCC', width=3)))
    fig.add_hline(y=0, line_dash="dash", line_color="white")
    fig.update_layout(title="Strategy Payoff Projection", template="plotly_dark", 
                      xaxis_title="Underlying Price", yaxis_title="Profit / Loss (₹)")
    return fig

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Fund Management")
    st.metric("Capital Available", f"₹{st.session_state.fund_balance:,.2f}")
    
    user_query = st.text_input("Friendly Search", value="Nifty")
    asset = nse_friendly_search(user_query)
    
    if asset:
        st.success(f"Found: {asset['name']}")
        clean_t = asset['symbol'].replace(".NS","").replace("^","").replace("NSEI","NIFTY").replace("NSEBANK","BANKNIFTY")
        lot_size = NSE_LOTS.get(clean_t, 1)
        lots = st.number_input(f"Quantity (Lots of {lot_size})", min_value=1, value=1)
        
        if st.button("🔥 Run AI Manager Intel"):
            with st.spinner("AI Quant Analysis..."):
                tk = yf.Ticker(asset['symbol'])
                cp = tk.history(period="1d")['Close'].iloc[-1]
                prompt = f"Hedge Fund Manager. Asset: {asset['name']} @ {cp}. Give Bullish/Bearish sentiment and suggest a Strike."
                res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                st.session_state.curr_trade = {"ticker": asset['symbol'], "name": asset['name'], "market_price": cp, "qty": lots * lot_size, "report": res.text}
                st.rerun()

# --- 4. DASHBOARD TABS ---
t_ai, t_desk, t_perf = st.tabs(["🧠 AI Strategy", "🚀 Execution Desk", "📊 Performance"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
        st.metric("Current Spot Price", f"₹{st.session_state.curr_trade['market_price']:,.2f}")
    else: st.warning("Search and run Intel to start.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Institutional Order Entry")
        
        mode = st.radio("Instrument", ["Cash/Spot", "Options (CE/PE)"], horizontal=True)
        
        if mode == "Options (CE/PE)":
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Type", ["CE (Call)", "PE (Put)"])
            suggested_strike = round(tr['market_price'] / 50) * 50
            strike_price = c2.number_input("Strike", value=int(suggested_strike), step=50)
            entry_price = c3.number_input("Premium (Price)", value=150.0)
            
            # --- PAYOFF VISUALIZER ---
            st.plotly_chart(plot_payoff(mode, opt_type, strike_price, entry_price, tr['qty']), use_container_width=True)
            
            display_name = f"{tr['name']} {strike_price} {opt_type[:2]}"
            margin_mult = 1.0
        else:
            c1, c2, c3 = st.columns(3)
            entry_price = c1.number_input("Limit Price", value=float(tr['market_price']))
            st.plotly_chart(plot_payoff(mode, None, entry_price, 0, tr['qty']), use_container_width=True)
            display_name = f"{tr['name']} (Spot)"
            margin_mult = 0.10

        req_margin = entry_price * tr['qty'] * margin_mult
        st.metric(f"Capital Required", f"₹{req_margin:,.2f}")

        if st.button("CONFIRM & EXECUTE ORDER"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": display_name, "entry": entry_price, "qty": tr['qty'], "margin": req_margin, "mode": mode
                })
                st.rerun()
            else: st.error("Insufficient Funds!")

    st.divider()
    for i, pos in enumerate(st.session_state.portfolio):
        with st.expander(f"{pos['name']} | Entry: ₹{pos['entry']}"):
            if st.button("SQUARE OFF", key=f"cl_{i}"):
                st.session_state.fund_balance += pos['margin']
                st.session_state.pnl_ledger.append({"Asset": pos['name'], "P&L": 0.0})
                st.session_state.portfolio.pop(i)
                st.rerun()

with t_perf:
    if st.session_state.pnl_ledger:
        st.table(pd.DataFrame(st.session_state.pnl_ledger))
