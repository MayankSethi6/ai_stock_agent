import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from openai import OpenAI
from google import genai
from jugaad_data.nse import NSELive

# --- 1. CONFIG & SESSION INITIALIZATION ---
st.set_page_config(page_title="NSE Alpha Terminal", layout="wide", page_icon="🏛️")

# Initialize API Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize Global State
for key, val in {
    'fund_balance': 1000000.0, 
    'portfolio': [], 
    'history': [], 
    'active_asset': None, 
    'ai_report': None, 
    'quota_count': 0,
    'conn_status': "⚪ Ready"
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. CRASH-PROOF DATA ENGINE ---
def fetch_nse_price(symbol, is_opt=False, strike=None, otype=None, expiry=None):
    """Fetches numeric prices with strict type-safety to prevent 'None' errors."""
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
        
        final_p = float(price) if price is not None else 0.0
        return final_p, "🟢 Online"
    except Exception as e:
        return 0.0, f"🔴 Sync Error: {str(e)[:15]}"

# --- 3. MULTI-AI STRATEGY ENGINE ---
def run_multi_ai(prompt):
    st.session_state.quota_count += 1
    with st.status("🧠 Consulting AI Quant Engines...", expanded=True) as status:
        # Attempt 1: OpenAI
        st.write("📡 Pinging OpenAI (GPT-4o)...")
        try:
            res = st.session_state.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": "NSE F&O Expert"}, {"role": "user", "content": prompt}],
                timeout=15
            )
            status.update(label="✅ Strategy Generated via OpenAI", state="complete", expanded=False)
            return f"🤖 **OpenAI Intel:**\n\n{res.choices[0].message.content}"
        except Exception:
            # Attempt 2: Gemini Fallback
            st.write("🔄 Falling back to Gemini 2.0...")
            try:
                res = st.session_state.gemini_client.models.generate_content(
                    model="gemini-2.0-flash", contents=[prompt]
                )
                status.update(label="✅ Strategy Generated via Gemini", state="complete", expanded=False)
                return f"♊ **Gemini Fallback:**\n\n{res.text}"
            except Exception:
                status.update(label="❌ All AI Engines Failed", state="error")
                return "❌ Quota Exhausted or Connection Failed."

# --- 4. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Terminal Control")
    st.write(f"**Data Health:** {st.session_state.conn_status}")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    st.divider()
    search = st.text_input("Trade Focus (NIFTY/RELIANCE)", value="NIFTY").upper()
    if st.button("🔍 Fixate & Sync Market"):
        p, status = fetch_nse_price(search)
        st.session_state.conn_status = status
        if p > 0:
            st.session_state.active_asset = {"symbol": search, "price": p}
            st.success(f"Locked: {search} @ ₹{p}")

    if st.button("🚨 HARD RESET SYNC"):
        st.cache_data.clear()
        st.session_state.quota_count = 0
        st.rerun()

# --- 5. MAIN INTERFACE (4 TABS) ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Quant", "🚀 Execution", "📊 Live P/L", "📜 History"])

with t_ai:
    if st.session_state.active_asset:
        asset = st.session_state.active_asset
        if st.button("🔥 GENERATE AI STRATEGY", type="primary", use_container_width=True):
            prompt = f"Analyze {asset['symbol']} at ₹{asset['price']}. Suggest a high-probability NSE Option play."
            st.session_state.ai_report = run_multi_ai(prompt)
    
    if st.session_state.ai_report:
        st.markdown(st.session_state.ai_report)
    else: st.info("Fixate an asset in the sidebar to start.")

with t_desk:
    if st.session_state.active_asset:
        asset = st.session_state.active_asset
        st.subheader(f"Order Entry: {asset['symbol']}")
        c1, c2, c3 = st.columns(3)
        mode = c1.selectbox("Order Type", ["Naked Buy", "Naked Sell", "Spread Leg"])
        strike = c2.number_input("Strike", value=int(asset['price']), step=50)
        otype = c3.selectbox("Option", ["CE", "PE"])
        
        c4, c5 = st.columns(2)
        expiry = c4.date_input("Expiry", value=date(2026, 4, 30))
        lots = c5.number_input("Lots", min_value=1, step=1)
        
        premium, _ = fetch_nse_price(asset['symbol'], True, strike, otype, expiry)
        premium = premium if premium > 0 else 100.0
        qty = lots * (65 if "NIFTY" in asset['symbol'] else 250)
        margin = (185000 * lots) if mode == "Naked Sell" else (premium * qty)
        
        st.info(f"Premium: ₹{premium} | Margin Required: ₹{margin:,.2f}")
        
        if st.button("🚀 EXECUTE TRADE", use_container_width=True):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "symbol": asset['symbol'], "strike": strike, "otype": otype, 
                    "expiry": expiry, "entry": premium, "qty": qty, "margin": margin, "mode": mode
                })
                st.rerun()

with t_port:
    col_a, col_b = st.columns([4, 1])
    if col_b.button("🔄 REFRESH SYNC"): st.rerun()
        
    total_unrealized = 0
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            cur_p, status = fetch_nse_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry'])
            st.session_state.conn_status = status
            display_p = cur_p if (cur_p is not None and cur_p > 0) else pos['entry']
            
            pnl = (display_p - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - display_p) * pos['qty']
            total_unrealized += pnl
            
            with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | P/L: ₹{pnl:,.2f}"):
                st.write(f"Entry: ₹{pos['entry']} | **Current: ₹{display_p}**")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": f"{pos['symbol']} {pos['strike']}{pos['otype']}", "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.metric("Total Unrealized P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else: st.info("No active trades.")

with t_hist:
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
