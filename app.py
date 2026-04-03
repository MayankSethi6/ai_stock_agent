import streamlit as st
import pandas as pd
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. SESSION PERSISTENCE (Crucial for History/Cash) ---
if 'fund_balance' not in st.session_state: st.session_state.fund_balance = 1000000.0
if 'portfolio' not in st.session_state: st.session_state.portfolio = []
if 'history' not in st.session_state: st.session_state.history = []
if 'token_log' not in st.session_state: 
    st.session_state.token_log = {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0}
if 'active_asset' not in st.session_state: st.session_state.active_asset = {"symbol": "NIFTY", "price": 0.0}

# Initialize Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- 2. ZERO-TOKEN PRICE ENGINE ---
def fetch_nse_price_only(symbol, is_opt=False, **kwargs):
    """Fetches market data with 0 AI Tokens."""
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

# --- 3. TOKEN-MONITORED AI ENGINE ---
def run_monitored_ai(prompt):
    with st.status("🧠 AI Analysis (Consuming Tokens)...") as status:
        try: # Try Gemini 3 Flash Preview
            res = st.session_state.gemini_client.models.generate_content(
                model="gemini-3-flash-preview", contents=[prompt]
            )
            st.session_state.token_log["Gemini 3"] += 1
            return f"♊ **Gemini 3:**\n\n{res.text}"
        except:
            try: # Fallback to Groq (High Limits)
                res = st.session_state.groq_client.chat.completions.create(
                    model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}]
                )
                st.session_state.token_log["Groq/Llama"] += 1
                return f"🦙 **Groq:**\n\n{res.choices[0].message.content}"
            except:
                return "❌ AI Quotas Exhausted."

# --- 4. SIDEBAR DASHBOARD ---
with st.sidebar:
    st.header("📊 Usage & Health")
    st.subheader("AI Token Counter")
    for engine, count in st.session_state.token_log.items():
        st.write(f"● {engine}: **{count}** calls")
    
    st.divider()
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    # Persistent Reset
    if st.button("🚨 RESET ALL (History & Cash)", use_container_width=True):
        st.session_state.history = []
        st.session_state.portfolio = []
        st.session_state.fund_balance = 1000000.0
        st.session_state.token_log = {k: 0 for k in st.session_state.token_log}
        st.rerun()

# --- 5. MAIN INTERFACE ---
t_desk, t_port, t_hist, t_ai = st.tabs(["🚀 Execution Desk", "📊 Live P/L", "📜 Order History", "🧠 AI Quant"])

with t_desk:
    st.subheader("Trade Execution")
    c1, c2 = st.columns([3, 1])
    sym = c1.text_input("Ticker Symbol", value=st.session_state.active_asset['symbol']).upper()
    if c2.button("Sync LTP (0 Tokens)", use_container_width=True):
        p = fetch_nse_price_only(sym)
        st.session_state.active_asset = {"symbol": sym, "price": p}
    
    ltp = st.session_state.active_asset['price']
    st.write(f"**Current Market Price:** ₹{ltp:,.2f}")

    st.divider()
    col1, col2, col3 = st.columns(3)
    mode = col1.selectbox("Order Mode", ["Naked Buy", "Naked Sell", "Spread Leg"])
    strike = col2.number_input("Strike Price", value=int(ltp) if ltp > 0 else 22000, step=50)
    otype = col3.selectbox("Option Type", ["CE", "PE"])
    
    col4, col5 = st.columns(2)
    expiry = col4.date_input("Expiry Date", value=date(2026, 4, 30))
    lots = col5.number_input("Number of Lots", min_value=1, step=1)

    # Fetch Option Premium (0 Tokens)
    premium = fetch_nse_price_only(sym, True, strike=strike, otype=otype, expiry=expiry) or 50.0
    qty = lots * (50 if "NIFTY" in sym else 15)
    margin = (165000 * lots) if mode == "Naked Sell" else (premium * qty)
    
    st.info(f"Premium: ₹{premium} | Est. Margin: ₹{margin:,.2f}")
    
    if st.button("🚀 EXECUTE TRADE", type="primary", use_container_width=True):
        if st.session_state.fund_balance >= margin:
            st.session_state.fund_balance -= margin
            st.session_state.portfolio.append({
                "symbol": sym, "strike": strike, "otype": otype, 
                "expiry": expiry, "entry": premium, "qty": qty, "margin": margin, "mode": mode
            })
            st.toast("Trade Executed Successfully!")
            st.rerun()
        else:
            st.error("Insufficient Funds!")

with t_port:
    st.subheader("Active Portfolio")
    if st.button("🔄 Sync Prices (0 Tokens)"): st.rerun()
    
    total_unrealized = 0
    for i, pos in enumerate(st.session_state.portfolio):
        # Fresh Price Sync (0 Tokens)
        cur = fetch_nse_price_only(pos['symbol'], True, strike=pos['strike'], otype=pos['otype'], expiry=pos['expiry'])
        cur = cur if cur > 0 else pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        total_unrealized += pnl
        
        with st.expander(f"{pos['symbol']} {pos['strike']}{pos['otype']} | P/L: ₹{pnl:,.2f}"):
            st.write(f"Entry: ₹{pos['entry']} | LTP: ₹{cur}")
            if st.button("Close Position", key=f"close_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.history.append({
                    "Symbol": pos['symbol'], "Strike": pos['strike'], "Type": pos['otype'],
                    "P&L": pnl, "Exit_Time": datetime.now().strftime("%H:%M:%S")
                })
                st.session_state.portfolio.pop(i)
                st.rerun()
    st.metric("Total Unrealized P/L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)

with t_hist:
    st.subheader("Closed Trade History")
    if st.session_state.history:
        st.dataframe(pd.DataFrame(st.session_state.history), use_container_width=True)
    else:
        st.info("No closed trades yet.")

with t_ai:
    st.subheader("AI Strategy Analysis")
    if st.button("🧠 GENERATE STRATEGY (Consumes Tokens)"):
        prompt = f"Provide a high-probability strategy for {st.session_state.active_asset['symbol']} at ₹{st.session_state.active_asset['price']}."
        st.markdown(run_monitored_ai(prompt))
