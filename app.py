import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from jugaad_data.nse import NSELive

# --- 1. CONFIG & CLIENTS ---
st.set_page_config(page_title="NSE Alpha Pro", layout="wide", page_icon="🏛️")

# Initialize State
for key, val in {
    'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
    'active_asset': None, 'ai_report': None, 'conn_status': "⚪ Ready"
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. ROBUST DATA ENGINE (CRASH-PROOF) ---
def fetch_nse_price(symbol, is_opt=False, strike=None, otype=None, expiry=None):
    """
    Returns (Price, Status_Message). 
    Guarantees a numeric return to prevent 'None' comparison errors.
    """
    n = NSELive() 
    try:
        if not is_opt:
            if "NIFTY" in symbol:
                name = "NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"
                price = n.live_index(name)['data'][0]['lastPrice']
            else:
                price = n.stock_quote(symbol)['priceInfo']['lastPrice']
        else:
            chain = n.index_option_chain(symbol) if "NIFTY" in symbol else n.stock_option_chain(symbol)
            exp_str = expiry.strftime('%d-%b-%Y')
            price = 0.0
            for row in chain['records']['data']:
                if row['strikePrice'] == strike and row['expiryDate'] == exp_str:
                    # Check if the specific side (CE/PE) exists and has a price
                    side_data = row.get(otype)
                    if side_data and isinstance(side_data, dict):
                        price = side_data.get('lastPrice', 0.0)
                    break
        
        # Ensure we return a float, never None
        final_p = float(price) if price is not None else 0.0
        return final_p, "🟢 Online"
        
    except Exception as e:
        return 0.0, f"🔴 Error: {str(e)[:20]}..."

# --- 3. SIDEBAR WITH HEALTH MONITOR ---
with st.sidebar:
    st.header("⚙️ Terminal Control")
    
    # Connection Health Indicator
    st.write(f"**NSE Data Health:** {st.session_state.conn_status}")
    
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    st.divider()
    search = st.text_input("Trade Focus", value="NIFTY").upper()
    if st.button("🔍 Fixate & Sync"):
        p, status = fetch_nse_price(search)
        st.session_state.conn_status = status
        if p > 0:
            st.session_state.active_asset = {"symbol": search, "price": p}
            st.success(f"Locked: {search} @ ₹{p}")

# --- 4. MAIN INTERFACE (4 TABS) ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Quant", "🚀 Execution", "📊 Live P/L", "📜 History"])

# ... (Tabs 1 & 2 logic remains consistent) ...

with t_port:
    col_a, col_b = st.columns([4, 1])
    col_a.subheader("Active Positions")
    if col_b.button("🔄 REFRESH SYNC"):
        st.toast("Re-handshaking with NSE...")
        
    total_unrealized = 0
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            # THE FIX: This call now returns a float 0.0 even if it fails
            cur_p, status = fetch_nse_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry'])
            st.session_state.conn_status = status
            
            # Type-safe comparison (Line 138 Fix)
            display_p = cur_p if (cur_p is not None and cur_p > 0) else pos['entry']
            
            pnl = (display_p - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - display_p) * pos['qty']
            total_unrealized += pnl
            
            with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | P/L: ₹{pnl:,.2f}"):
                st.write(f"Entry: ₹{pos['entry']} | **LTP: ₹{display_p}**")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": f"{pos['symbol']} {pos['strike']}{pos['otype']}", "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.divider()
        st.metric("Total Unrealized P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else: st.info("No active trades.")
