import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. CONFIG & SESSION STATE ---
st.set_page_config(page_title="NSE Alpha Terminal", layout="wide", page_icon="🏛️")

# Initialize API Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    # Target the new 2026 Gemini 3 series
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# Initialize Global State
for key, val in {
    'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
    'active_asset': None, 'ai_report': None, 'conn_status': "⚪ Ready"
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. ROBUST NSE DATA ENGINE ---
def fetch_nse_price(symbol, is_opt=False, strike=None, otype=None, expiry=None):
    """Fetches numeric prices with strict type-safety."""
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
                    side_data = row.get(otype)
                    if isinstance(side_data, dict):
                        price = side_data.get('lastPrice', 0.0)
                    break
        
        return float(price) if price is not None else 0.0, "🟢 Online"
    except Exception as e:
        return 0.0, f"🔴 Sync Error: {str(e)[:10]}"

# --- 3. MULTI-AI STRATEGY ENGINE (Gemini 3 -> Groq -> OpenAI) ---
def run_multi_ai(prompt):
    with st.status("🧠 Consulting Quant Engines...", expanded=True) as status:
        # Tier 1: Gemini 3 Flash Preview (Most Intelligent)
        st.write("📡 Pinging Google (Gemini 3 Flash Preview)...")
        try:
            res = st.session_state.gemini_client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=[prompt]
            )
            status.update(label="✅ Strategy via Gemini 3", state="complete")
            return f"♊ **Gemini 3 Intel:**\n\n{res.text}"
        except Exception as e:
            st.warning(f"Gemini 3 Limit Reached: {str(e)[:30]}")

        # Tier 2: Groq (Highest Limits / Free Workhorse)
        st.write("⚡ Pinging Groq (Llama 4 Scout)...")
        try:
            res = st.session_state.groq_client.chat.completions.create(
                model="llama-4-scout-17b",
                messages=[{"role": "user", "content": prompt}]
            )
            status.update(label="✅ Strategy via Groq (Unlimited Tier)", state="complete")
            return f"🦙 **Groq/Llama Intel:**\n\n{res.choices[0].message.content}"
        except Exception as e:
            st.warning(f"Groq failed: {str(e)[:30]}")

        # Tier 3: OpenAI Fallback
        st.write("🔄 Pinging OpenAI (GPT-4o)...")
        try:
            res = st.session_state.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            status.update(label="✅ Strategy via OpenAI", state="complete")
            return f"🤖 **OpenAI Intel:**\n\n{res.choices[0].message.content}"
        except Exception:
            status.update(label="❌ All Engines Offline", state="error")
            return "Critical: All AI quotas exhausted."

# --- 4. SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.header("⚙️ Terminal Control")
    st.write(f"**Data Health:** {st.session_state.conn_status}")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    st.divider()
    search = st.text_input("Ticker Focus", value="NIFTY").upper()
    if st.button("🔍 Fixate & Sync"):
        p, status = fetch_nse_price(search)
        st.session_state.conn_status = status
        if p > 0:
            st.session_state.active_asset = {"symbol": search, "price": p}
            st.success(f"Locked: {search} @ ₹{p}")

# --- 5. MAIN INTERFACE ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Quant", "🚀 Execution", "📊 Live P/L", "📜 History"])

with t_ai:
    if st.session_state.active_asset:
        asset = st.session_state.active_asset
        if st.button("🔥 GENERATE AI STRATEGY", type="primary", use_container_width=True):
            prompt = f"Target: {asset['symbol']} @ ₹{asset['price']}. Suggest a low-risk option strategy with entry/exit."
            st.session_state.ai_report = run_multi_ai(prompt)
    
    if st.session_state.ai_report:
        st.markdown(st.session_state.ai_report)
    else: st.info("Fixate an asset in the sidebar to start analysis.")

with t_desk:
    if st.session_state.active_asset:
        asset = st.session_state.active_asset
        st.subheader(f"Execution Desk: {asset['symbol']}")
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Mode", ["Naked Buy", "Naked Sell", "Spread"])
        strike = c2.number_input("Strike", value=int(asset['price']), step=50)
        otype = c3.selectbox("Type", ["CE", "PE"])
        
        expiry = st.date_input("Expiry", value=date(2026, 4, 30))
        lots = st.number_input("Lots", min_value=1, step=1)
        
        premium, _ = fetch_nse_price(asset['symbol'], True, strike, otype, expiry)
        premium = premium if premium > 0 else 10.0 # Default if no data
        qty = lots * (50 if "NIFTY" in asset['symbol'] else 250)
        margin = (150000 * lots) if mode == "Naked Sell" else (premium * qty)
        
        st.write(f"**Estimated Margin:** ₹{margin:,.2f} | **LTP:** ₹{premium}")
        
        if st.button("🚀 TRANSMIT ORDER"):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "symbol": asset['symbol'], "strike": strike, "otype": otype, 
                    "expiry": expiry, "entry": premium, "qty": qty, "margin": margin, "mode": mode
                })
                st.success("Order filled.")
                st.rerun()

with t_port:
    if st.session_state.portfolio:
        total_pnl = 0
        for i, pos in enumerate(st.session_state.portfolio):
            cur_p, _ = fetch_nse_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry'])
            # Fixed line 138 logic
            display_p = cur_p if (cur_p is not None and cur_p > 0) else pos['entry']
            
            pnl = (display_p - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - display_p) * pos['qty']
            total_pnl += pnl
            
            with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | ₹{pnl:,.2f}"):
                st.write(f"Entry: ₹{pos['entry']} | Current: ₹{display_p}")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": f"{pos['symbol']} {pos['strike']}{pos['otype']}", "P&L": pnl, "Time": datetime.now()})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.metric("Portfolio Unrealized P/L", f"₹{total_pnl:,.2f}", delta=total_pnl)
    else: st.info("No active trades.")

with t_hist:
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
