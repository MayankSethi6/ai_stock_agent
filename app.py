import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from openai import OpenAI
from google import genai
from google.api_core import exceptions
from jugaad_data.nse import NSELive

# --- 1. CONFIG & CLIENTS ---
st.set_page_config(page_title="NSE Alpha - Multi-AI", layout="wide")

# Initialize OpenAI
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Initialize Gemini (as Fallback)
if 'gemini_client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Global State
for key, val in {
    'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
    'active_asset': None, 'ai_report': None, 'ai_engine': 'ChatGPT (GPT-4o)'
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. DATA & AI ENGINES ---
n = NSELive()

def get_nse_price(symbol, is_opt=False, strike=None, otype=None, expiry=None):
    try:
        if not is_opt:
            if "NIFTY" in symbol:
                name = "NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"
                return n.live_index(name)['data'][0]['lastPrice']
            return n.stock_quote(symbol)['priceInfo']['lastPrice']
        else:
            # Option Chain Logic
            chain = n.index_option_chain(symbol) if "NIFTY" in symbol else n.stock_option_chain(symbol)
            exp_str = expiry.strftime('%d-%b-%Y')
            for row in chain['records']['data']:
                if row['strikePrice'] == strike and row['expiryDate'] == exp_str:
                    return row[otype]['lastPrice']
    except: return 0.0

def fetch_ai_intel(prompt):
    """Attempt ChatGPT first, fallback to Gemini on failure."""
    # Attempt 1: OpenAI
    try:
        res = st.session_state.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are an NSE F&O Quant."}, {"role": "user", "content": prompt}]
        )
        return f"🤖 **ChatGPT Intel:**\n\n{res.choices[0].message.content}"
    except Exception as e:
        st.warning("ChatGPT Limit reached. Switching to Gemini Fallback...")
        # Attempt 2: Gemini
        try:
            res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
            return f"♊ **Gemini Fallback Intel:**\n\n{res.text}"
        except:
            return "❌ All AI Engines exhausted. Please check API quotas."

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 Pro Terminal")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    # Margin Monitor
    blocked = sum([p['margin'] for p in st.session_state.portfolio])
    st.write(f"**Blocked Margin:** ₹{blocked:,.2f}")
    
    st.divider()
    search = st.text_input("NSE Symbol", value="NIFTY").upper()
    if st.button("🔍 Fixate & Sync"):
        price = get_nse_price(search)
        st.session_state.active_asset = {"symbol": search, "price": price}
    
    if st.session_state.active_asset:
        if st.button("🔥 RUN DUAL-AI INTEL", type="primary"):
            asset = st.session_state.active_asset
            st.session_state.ai_report = fetch_ai_intel(f"Analyze {asset['symbol']} at {asset['price']}. Suggest Naked vs Spread.")

# --- 4. MAIN TABS ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Strategy", "🚀 Execution", "📊 Portfolio", "📜 History"])

with t_ai:
    if st.session_state.ai_report: st.markdown(st.session_state.ai_report)
    else: st.info("Fixate an asset and run AI.")

with t_desk:
    if st.session_state.active_asset:
        asset = st.session_state.active_asset
        st.subheader(f"Trading: {asset['symbol']} @ ₹{asset['price']}")
        
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Mode", ["Naked Buy", "Naked Sell", "Spread Leg"])
        strike = c2.number_input("Strike", value=int(asset['price']), step=50)
        otype = c3.selectbox("Type", ["CE", "PE"])
        
        c4, c5 = st.columns(2)
        expiry = c4.date_input("Expiry", value=date(2026, 4, 30))
        lots = c5.number_input("Lots", min_value=1)
        
        # Live Sync for Premium
        premium = get_nse_price(asset['symbol'], True, strike, otype, expiry) or 100.0
        qty = lots * (65 if "NIFTY" in asset['symbol'] else 250)
        margin = (185000 * lots) if mode == "Naked Sell" else (premium * qty)
        
        st.write(f"**LTP:** ₹{premium} | **Required:** ₹{margin:,.2f}")
        
        if st.button("EXECUTE ORDER", use_container_width=True):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "symbol": asset['symbol'], "strike": strike, "otype": otype, 
                    "expiry": expiry, "entry": premium, "qty": qty, "margin": margin, "mode": mode
                })
                st.rerun()

with t_port:
    if st.button("🔄 FORCE SYNC ALL PRICES"): st.rerun()
    
    total_unrealized = 0
    for i, pos in enumerate(st.session_state.portfolio):
        cur = get_nse_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry']) or pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        total_unrealized += pnl
        
        with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | ₹{pnl:,.2f}"):
            if st.button("Square Off", key=f"sq_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.history.append({"Asset": pos['symbol'], "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                st.session_state.portfolio.pop(i)
                st.rerun()
    st.metric("Portfolio P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)

with t_hist:
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))
