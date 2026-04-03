import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. PERSISTENT SESSION STATE ---
# We use st.session_state to ensure history and P/L remain until a Hard Reset
if 'fund_balance' not in st.session_state: st.session_state.fund_balance = 1000000.0
if 'portfolio' not in st.session_state: st.session_state.portfolio = []
if 'history' not in st.session_state: st.session_state.history = []
if 'token_log' not in st.session_state: 
    # Tracking usage per engine
    st.session_state.token_log = {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0}

# Initialize Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- 2. THE "NO-AI" PRICE ENGINE ---
def fetch_nse_price_only(symbol, is_opt=False, **kwargs):
    """Zero AI Tokens. Purely fetches market data."""
    n = NSELive()
    try:
        if not is_opt:
            if "NIFTY" in symbol:
                name = "NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"
                return n.live_index(name)['data'][0]['lastPrice']
            return n.stock_quote(symbol)['priceInfo']['lastPrice']
        else:
            chain = n.index_option_chain(symbol) if "NIFTY" in symbol else n.stock_option_chain(symbol)
            exp_str = kwargs.get('expiry').strftime('%d-%b-%Y')
            for row in chain['records']['data']:
                if row['strikePrice'] == kwargs.get('strike') and row['expiryDate'] == exp_str:
                    return row[kwargs.get('otype')]['lastPrice']
    except: return 0.0

# --- 3. MULTI-AI WITH TOKEN TRACKING ---
def run_monitored_ai(prompt):
    with st.status("🧠 AI Analysis in Progress...") as status:
        # TIER 1: GEMINI 3
        try:
            res = st.session_state.gemini_client.models.generate_content(
                model="gemini-3-flash-preview", contents=[prompt]
            )
            st.session_state.token_log["Gemini 3"] += 1 
            return f"♊ **Gemini 3:**\n\n{res.text}"
        except:
            # TIER 2: GROQ
            try:
                res = st.session_state.groq_client.chat.completions.create(
                    model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}]
                )
                st.session_state.token_log["Groq/Llama"] += 1
                return f"🦙 **Groq:**\n\n{res.choices[0].message.content}"
            except:
                # TIER 3: OPENAI
                try:
                    res = st.session_state.openai_client.chat.completions.create(
                        model="gpt-4o", messages=[{"role": "user", "content": prompt}]
                    )
                    st.session_state.token_log["OpenAI"] += 1
                    return f"🤖 **OpenAI:**\n\n{res.choices[0].message.content}"
                except:
                    return "❌ All AI Quotas Exhausted."

# --- 4. THE DASHBOARD ---
st.title("🏛️ NSE Alpha Terminal")

with st.sidebar:
    st.header("📊 Usage Dashboard")
    st.write("**AI Tokens Consumed (Today):**")
    for engine, count in st.session_state.token_log.items():
        st.write(f"- {engine}: {count} calls")
    
    st.divider()
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🚨 CLEAR ALL DATA (Hard Reset)"):
        st.session_state.history = []
        st.session_state.portfolio = []
        st.session_state.fund_balance = 1000000.0
        st.session_state.token_log = {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0}
        st.rerun()

# --- 5. TABBED INTERFACE ---
t_desk, t_port, t_hist, t_ai = st.tabs(["🚀 Execution", "📊 Live P/L", "📜 History", "🧠 AI Quant"])

with t_desk:
    symbol = st.text_input("Symbol", "NIFTY").upper()
    if st.button("Get Price (0 Tokens)"):
        p = fetch_nse_price_only(symbol)
        st.session_state.active_price = p
        st.success(f"LTP: ₹{p}")

with t_port:
    col_a, col_b = st.columns([4, 1])
    if col_b.button("🔄 Sync Prices (0 Tokens)"): st.rerun()
    
    unrealized = 0
    for i, pos in enumerate(st.session_state.portfolio):
        # Direct Price Fetch (No AI used)
        cur = fetch_nse_price_only(pos['symbol'], True, strike=pos['strike'], otype=pos['otype'], expiry=pos['expiry'])
        cur = cur if cur > 0 else pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        unrealized += pnl
        
        st.write(f"**{pos['symbol']}**: P/L ₹{pnl:,.2f} (LTP: {cur})")
        if st.button(f"Close #{i}"):
            st.session_state.fund_balance += (pos['margin'] + pnl)
            st.session_state.history.append({"Asset": pos['symbol'], "P&L": pnl, "Date": datetime.now()})
            st.session_state.portfolio.pop(i)
            st.rerun()
    st.metric("Total Unrealized", f"₹{unrealized:,.2f}", delta=unrealized)

with t_hist:
    if st.session_state.history:
        st.table(pd.DataFrame(st.session_state.history))

with t_ai:
    if st.button("🔥 GENERATE AI STRATEGY (Uses Tokens)"):
        prompt = f"Analyze NIFTY for a naked sell strategy."
        st.write(run_monitored_ai(prompt))
