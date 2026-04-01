import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from jugaad_data.nse import NSELive

# --- 1. CONFIG & CLIENTS ---
st.set_page_config(page_title="NSE Alpha Pro", layout="wide", page_icon="🏛️")

# Initialize API Clients (Stored in session to prevent re-init)
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# Initialize Global State
for key, val in {
    'fund_balance': 1000000.0, 'portfolio': [], 'history': [], 
    'active_asset': None, 'ai_report': None, 'quota_count': 0
}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. DATA ENGINE (THE SYNC FIX) ---
def fetch_nse_price(symbol, is_opt=False, strike=None, otype=None, expiry=None):
    """
    STRICTLY NO CACHING. 
    Creates a fresh NSELive instance on every call to bypass stale data.
    """
    n = NSELive() 
    try:
        if not is_opt:
            if "NIFTY" in symbol:
                idx_name = "NIFTY 50" if symbol == "NIFTY" else "NIFTY BANK"
                return n.live_index(idx_name)['data'][0]['lastPrice']
            return n.stock_quote(symbol)['priceInfo']['lastPrice']
        else:
            # Option Chain Logic
            chain = n.index_option_chain(symbol) if "NIFTY" in symbol else n.stock_option_chain(symbol)
            exp_str = expiry.strftime('%d-%b-%Y') # e.g. 30-Apr-2026
            for row in chain['records']['data']:
                if row['strikePrice'] == strike and row['expiryDate'] == exp_str:
                    return row[otype]['lastPrice']
    except:
        return 0.0

def run_multi_ai(prompt):
    """GPT-5.4 Primary with Gemini Fallback."""
    st.session_state.quota_count += 1
    try:
        res = st.session_state.openai_client.chat.completions.create(
            model="gpt-5.4-thinking",
            messages=[{"role": "system", "content": "NSE Quant Expert"}, {"role": "user", "content": prompt}]
        )
        return f"🤖 **GPT-5.4 Intel:**\n\n{res.choices[0].message.content}"
    except:
        try:
            res = st.session_state.gemini_client.models.generate_content(model="gemini-3-flash", contents=[prompt])
            return f"♊ **Gemini Fallback:**\n\n{res.text}"
        except:
            return "❌ Quota Exhausted on all engines."

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Terminal Control")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    st.write(f"**AI Calls Today:** {st.session_state.quota_count}")
    
    st.divider()
    search = st.text_input("Active Trade Focus", value="NIFTY").upper()
    if st.button("🔍 Fixate & Get LTP"):
        p = fetch_nse_price(search)
        st.session_state.active_asset = {"symbol": search, "price": p}
        st.success(f"Locked: {search} @ ₹{p}")

    if st.button("🚨 CLEAR APP CACHE"):
        st.cache_data.clear()
        st.rerun()

# --- 4. MAIN INTERFACE (4 TABS) ---
t_ai, t_desk, t_port, t_hist = st.tabs(["🧠 AI Quant", "🚀 Execution", "📊 Live P/L", "📜 History"])

with t_ai:
    if st.session_state.active_asset:
        if st.button("🔥 GENERATE GPT-5 STRATEGY", type="primary"):
            asset = st.session_state.active_asset
            prompt = f"Analyze {asset['symbol']} at ₹{asset['price']}. Suggest a high-probability naked or spread play."
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
        
        # Fresh Premium Fetch
        premium = fetch_nse_price(asset['symbol'], True, strike, otype, expiry) or 100.0
        qty = lots * (65 if "NIFTY" in asset['symbol'] else 250)
        margin = (185000 * lots) if mode == "Naked Sell" else (premium * qty)
        
        st.info(f"Current Premium: ₹{premium} | Margin Required: ₹{margin:,.2f}")
        
        if st.button("🚀 EXECUTE TRADE", use_container_width=True):
            if st.session_state.fund_balance >= margin:
                st.session_state.fund_balance -= margin
                st.session_state.portfolio.append({
                    "symbol": asset['symbol'], "strike": strike, "otype": otype, 
                    "expiry": expiry, "entry": premium, "qty": qty, "margin": margin, "mode": mode
                })
                st.toast(f"Executed {mode} on {asset['symbol']}")
                st.rerun()

with t_port:
    col_a, col_b = st.columns([4, 1])
    col_a.subheader("Current Positions")
    if col_b.button("🔄 REFRESH SYNC"):
        st.toast("Fetching latest NSE prices...")
        # st.rerun() is automatic
        
    total_unrealized = 0
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            # THE SYNC: Direct call to fetch_nse_price inside the loop
            cur_p = fetch_nse_price(pos['symbol'], True, pos['strike'], pos['otype'], pos['expiry'])
            
            # Fallback if NSE API throttles or market is closed
            display_p = cur_p if cur_p > 0 else pos['entry']
            
            pnl = (display_p - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - display_p) * pos['qty']
            total_unrealized += pnl
            
            with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | P/L: ₹{pnl:,.2f}"):
                st.write(f"Entry: ₹{pos['entry']} | **Current: ₹{display_p}**")
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": f"{pos['symbol']} {pos['strike']}{pos['otype']}", "P&L": pnl, "Time": datetime.now().strftime("%H:%M")})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.divider()
        st.metric("Total Unrealized P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else: st.info("No active trades.")

with t_hist:
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
    else: st.write("No trade history yet.")
