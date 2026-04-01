import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from openai import OpenAI
from google import genai
from jugaad_data.nse import NSELive

# --- 1. CONFIG & CLIENTS ---
st.set_page_config(page_title="NSE Alpha GPT-5.4", layout="wide")

if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

if 'active_asset' not in st.session_state:
    st.session_state.update({
        'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
        'active_asset': None, 'ai_report': None
    })

n = NSELive()

# --- 2. THE GPT-5.4 REASONING ENGINE ---
def fetch_gpt5_intel(prompt, mode="Thinking"):
    """
    Targets the 2026 GPT-5.4 Flagship model.
    Modes: 'Instant' (Fast) or 'Thinking' (Deep Reasoning)
    """
    model_alias = "gpt-5.3-instant" if mode == "Instant" else "gpt-5.4-thinking"
    try:
        res = st.session_state.openai_client.chat.completions.create(
            model=model_alias,
            messages=[
                {"role": "system", "content": "You are a PhD-level Quant for the Indian NSE Market."},
                {"role": "user", "content": prompt}
            ],
            # 2026 Feature: Requesting Chain-of-Thought transparency
            extra_body={"include_thinking": True} if mode == "Thinking" else {}
        )
        return res.choices[0].message.content
    except Exception as e:
        st.error(f"GPT-5 API Error: {e}")
        return "⚠️ Engine stall. Check API credits."

# --- 3. UPDATED SIDEBAR ---
with st.sidebar:
    st.header("🏛️ GPT-5.4 NSE Terminal")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    st.divider()
    search = st.text_input("NSE Symbol", value="NIFTY").upper()
    if st.button("🔍 Sync Market Data"):
        # Direct NSE fetch using jugaad-data
        if "NIFTY" in search:
            p = n.live_index("NIFTY 50" if search == "NIFTY" else "NIFTY BANK")['data'][0]['lastPrice']
        else:
            p = n.stock_quote(search)['priceInfo']['lastPrice']
        st.session_state.active_asset = {"symbol": search, "price": p}
    
    if st.session_state.active_asset:
        # 2026 Model Selection
        think_mode = st.radio("Intelligence Level", ["Instant", "Thinking"], index=1)
        if st.button(f"🔥 RUN {think_mode.upper()} ANALYSIS", type="primary"):
            asset = st.session_state.active_asset
            prompt = f"Analyze {asset['symbol']} at ₹{asset['price']}. Build a low-delta neutral strategy."
            with st.spinner(f"GPT-5.4 is {think_mode.lower()}..."):
                st.session_state.ai_report = fetch_gpt5_intel(prompt, think_mode)

# --- 4. MAIN INTERFACE ---
tab_ai, tab_trade = st.tabs(["🧠 GPT-5 Analysis", "🚀 Execution Desk"])

with tab_ai:
    if st.session_state.ai_report:
        st.markdown(f"### Strategy Report ({date.today()})")
        st.write(st.session_state.ai_report)
    else:
        st.info("Select an asset and run the GPT-5 engine.")

# (Rest of execution logic remains same as previous version)
