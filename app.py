import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from nsepython import nse_get_top_gainers, nse_get_top_losers

# --- 1. PERSISTENT SESSION STATE ---
for key, val in {
    'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
    'token_log': {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0},
    'auto_trade_enabled': False
}.items():
    if key not in st.session_state: st.session_state[key] = val

# Initialize API Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- 2. THE AUTO-EXECUTION LOGIC ---
def process_auto_trade(symbol, ltp, advice):
    """Parses AI advice and executes if a strong signal is found."""
    advice_upper = advice.upper()
    mode = None
    
    if "STRONG BUY" in advice_upper or "BUY" in advice_upper:
        mode = "Naked Buy"
    elif "STRONG SELL" in advice_upper or "SELL" in advice_upper:
        mode = "Naked Sell"
        
    if mode and st.session_state.auto_trade_enabled:
        # Standard 1-lot calculation for Intraday
        qty = 50 if "NIFTY" in symbol else 15
        margin = 165000 if mode == "Naked Sell" else (float(ltp) * qty)
        
        if st.session_state.fund_balance >= margin:
            st.session_state.fund_balance -= margin
            st.session_state.portfolio.append({
                "symbol": symbol, "strike": int(ltp), "otype": "CE" if "Buy" in mode else "PE", 
                "expiry": date(2026, 4, 30), "entry": float(ltp), "qty": qty, 
                "margin": margin, "mode": f"Auto-{mode}"
            })
            return f"✅ Auto-Executed: {mode} @ ₹{ltp}"
    return None

# --- 3. AI STRATEGY ENGINE ---
def get_ai_recommendation(symbol, ltp, trend):
    prompt = f"Stock: {symbol}, Price: {ltp}, Trend: {trend}. Provide a 1-sentence recommendation starting with 'STRONG BUY', 'STRONG SELL', or 'HOLD'."
    try:
        # Primary: Gemini 3 Flash Preview
        res = st.session_state.gemini_client.models.generate_content(
            model="gemini-3-flash-preview", contents=[prompt])
        st.session_state.token_log["Gemini 3"] += 1
        return res.text
    except:
        # Fallback: Groq (High Limits)
        res = st.session_state.groq_client.chat.completions.create(
            model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}])
        st.session_state.token_log["Groq/Llama"] += 1
        return res.choices[0].message.content

# --- 4. MAIN INTERFACE ---
st.title("🏛️ NSE Alpha Terminal: Auto-Quant")

with st.sidebar:
    st.header("📊 System Health")
    st.session_state.auto_trade_enabled = st.checkbox("⚡ Enable Auto-Trade", value=False, help="Automatically executes orders based on AI 'Strong' signals.")
    
    st.divider()
    for eng, count in st.session_state.token_log.items():
        st.write(f"● {eng}: **{count}** calls")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🚨 HARD RESET SYSTEM"):
        st.session_state.clear()
        st.rerun()

# --- 5. TABS ---
t_movers, t_desk, t_port, t_hist = st.tabs(["📈 Market Movers", "🚀 Execution", "📊 Live P/L", "📜 History"])

with t_movers:
    st.subheader("High Movement Stocks (Today)")
    try:
        gainers = nse_get_top_gainers().head(5)
        losers = nse_get_top_losers().head(5)
        movers_df = pd.concat([gainers, losers])
        
        for _, row in movers_df.iterrows():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            c1.write(f"**{row['symbol']}**")
            c2.write(f"₹{row['ltp']}")
            c3.write("🚀" if row['netPrice'] > 0 else "📉")
            
            if c4.button(f"🧠 Advice", key=f"btn_{row['symbol']}"):
                advice = get_ai_recommendation(row['symbol'], row['ltp'], "Gainer" if row['netPrice'] > 0 else "Loser")
                st.info(f"**Advice:** {advice}")
                
                # Check for Auto-Trade
                auto_msg = process_auto_trade(row['symbol'], row['ltp'], advice)
                if auto_msg: st.success(auto_msg)
    except:
        st.error("Market data unavailable. Re-syncing...")

with t_desk:
    st.subheader("Manual Execution")
    # ... (Manual Order code remains here) ...

with t_port:
    st.subheader("Current Portfolio")
    total_pnl = 0
    for i, pos in enumerate(st.session_state.portfolio):
        # Fresh Sync (0 Tokens)
        cur = float(pos['entry']) # Placeholder for demo, replace with fetch_nse_price_only in production
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        total_pnl += pnl
        
        with st.expander(f"{pos['symbol']} | {pos['mode']} | P/L: ₹{pnl:,.2f}"):
            if st.button("Close Position", key=f"close_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.history.append({"Symbol": pos['symbol'], "P&L": pnl, "Date": datetime.now()})
                st.session_state.portfolio.pop(i)
                st.rerun()
    st.metric("Total Unrealized", f"₹{total_pnl:,.2f}", delta=total_pnl)

with t_hist:
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history))
