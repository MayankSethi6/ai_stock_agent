import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. PERSISTENT SESSION STATE ---
# Stores terminal data so it survives tab switching and interactions
for key, val in {
    'fund_balance': 1000000.0, 
    'portfolio': [], 
    'history': [], 
    'token_log': {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0},
    'auto_trade_enabled': False,
    'active_asset': {"symbol": "NIFTY", "price": 0.0},
    'movers_data': pd.DataFrame(),
    'last_sync': "Never"
}.items():
    if key not in st.session_state: st.session_state[key] = val

# Initialize API Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- 2. ZERO-TOKEN DATA ENGINES (Optimized for Top 10) ---

def get_market_movers():
    """Directly pings NSE API and restricts to Top 5 Gainers & Top 5 Losers."""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        url = "https://www.nseindia.com/api/live-analysis-top-gainers-losers?index=NIFTY"
        response = session.get(url, headers=headers, timeout=5)
        data = response.json()
        
        # Slice to Top 5 each to get a total of Top 10
        gainers = pd.DataFrame(data['gainers']['data']).head(5)[['symbol', 'ltp', 'pChange']]
        losers = pd.DataFrame(data['losers']['data']).head(5)[['symbol', 'ltp', 'pChange']]
        
        gainers['Trend'], losers['Trend'] = "🚀 Gainer", "📉 Loser"
        return pd.concat([gainers, losers]).rename(columns={'pChange': 'netPrice'})
    except:
        return pd.DataFrame()

def fetch_nse_price_only(symbol, is_opt=False, **kwargs):
    """Fetches real-time market data with 0 AI Tokens."""
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

# --- 3. CORE LOGIC (AI & TRADING) ---

def run_monitored_ai(prompt):
    """Execution with monitored token consumption."""
    with st.status("🧠 AI Analysis...") as status:
        try: # Tier 1: Gemini 3
            res = st.session_state.gemini_client.models.generate_content(
                model="gemini-3-flash-preview", contents=[prompt])
            st.session_state.token_log["Gemini 3"] += 1
            return res.text
        except:
            try: # Tier 2: Groq
                res = st.session_state.groq_client.chat.completions.create(
                    model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}])
                st.session_state.token_log["Groq/Llama"] += 1
                return res.choices[0].message.content
            except: return "❌ AI Quota Exhausted."

def process_trade(symbol, ltp, advice=None, is_auto=False):
    """Naked Option Execution Logic."""
    mode = None
    if advice:
        adv = advice.upper()
        if "STRONG BUY" in adv: mode = "Naked Buy"
        elif "STRONG SELL" in adv: mode = "Naked Sell"
    
    # Logic for manual Buy button (default to Buy) or Auto-signal
    exec_mode = mode if is_auto else "Naked Buy"
    if exec_mode:
        qty = 50 if "NIFTY" in symbol else 15
        margin = 165000 if "Sell" in exec_mode else (float(ltp) * qty)
        if st.session_state.fund_balance >= margin:
            st.session_state.fund_balance -= margin
            st.session_state.portfolio.append({
                "symbol": symbol, "strike": int(ltp), "otype": "CE", "expiry": date(2026, 4, 30),
                "entry": float(ltp), "qty": qty, "margin": margin, "mode": f"{'Auto-' if is_auto else ''}{exec_mode}"
            })
            return True
    return False

# --- 4. MAIN INTERFACE ---

st.title("🏛️ NSE Alpha Terminal")

with st.sidebar:
    st.header("📊 Master Control")
    
    # UNIFIED SYNC (0 TOKENS)
    if st.button("🔄 SYNC ALL DATA", type="primary", use_container_width=True):
        with st.spinner("Accessing Exchange..."):
            st.session_state.movers_data = get_market_movers()
            st.session_state.last_sync = datetime.now().strftime("%H:%M:%S")
            st.session_state.active_asset['price'] = fetch_nse_price_only(st.session_state.active_asset['symbol'])
            st.rerun()

    st.write(f"Last Sync: **{st.session_state.last_sync}**")
    st.divider()
    st.session_state.auto_trade_enabled = st.checkbox("⚡ Enable Auto-Trade", value=False)
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    with st.expander("AI Token Meter"):
        for eng, count in st.session_state.token_log.items():
            st.write(f"{eng}: **{count}**")

    if st.button("🚨 HARD RESET SYSTEM"):
        st.session_state.clear()
        st.rerun()

t_movers, t_desk, t_port, t_hist = st.tabs(["📈 Top 10 Movers", "🚀 Execution", "📊 P/L", "📜 History"])

with t_movers:
    if st.session_state.movers_data.empty:
        st.info("Click 'SYNC ALL DATA' in the sidebar to fetch today's Top 10.")
    else:
        st.subheader(f"Top 10 High-Activity Stocks ({st.session_state.last_sync})")
        for _, row in st.session_state.movers_data.iterrows():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            c1.write(f"**{row['symbol']}**")
            c2.write(f"₹{row['ltp']}")
            # Color coding trend
            tc = "green" if "Gainer" in row['Trend'] else "red"
            c3.markdown(f":{tc}[{row['Trend']}]")
            
            if c4.button(f"🧠 AI Advice", key=f"mv_{row['symbol']}"):
                advice = run_monitored_ai(f"Stock {row['symbol']} @ ₹{row['ltp']}. Trend: {row['Trend']}. Provide 1-sentence action: STRONG BUY, STRONG SELL, or HOLD.")
                st.info(f"**{row['symbol']} Analysis:** {advice}")
                if st.session_state.auto_trade_enabled:
                    if process_trade(row['symbol'], row['ltp'], advice, is_auto=True):
                        st.success(f"⚡ Auto-Trade Executed for {row['symbol']}!")

with t_desk:
    st.subheader("Manual Order Management")
    c1, c2 = st.columns([3, 1])
    sym = c1.text_input("Ticker Symbol", value=st.session_state.active_asset['symbol']).upper()
    ltp = st.session_state.active_asset['price']
    st.write(f"**Live Market Price:** ₹{ltp:,.2f}")
    if st.button("🚀 Execute Market Buy (1 Lot)", use_container_width=True):
        if process_trade(sym, ltp): st.success("Trade Placed Successfully")

with t_port:
    st.subheader("Open Positions")
    total_pnl = 0
    if not st.session_state.portfolio:
        st.info("No active trades.")
    else:
        for i, pos in enumerate(st.session_state.portfolio):
            cur = fetch_nse_price_only(pos['symbol'], True, strike=pos['strike'], otype=pos['otype'], expiry=pos['expiry'])
            cur = cur if cur > 0 else pos['entry']
            pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
            total_pnl += pnl
            
            with st.expander(f"{pos['symbol']} | {pos['mode']} | P/L: ₹{pnl:,.2f}"):
                if st.button("Square Off", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.history.append({"Asset": pos['symbol'], "P&L": pnl, "Type": pos['mode'], "Time": datetime.now()})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        st.metric("Total Unrealized P/L", f"₹{total_pnl:,.2f}", delta=total_pnl)

with t_hist:
    st.subheader("Trade Logs")
    if st.session_state.history: 
        st.table(pd.DataFrame(st.session_state.history))
    else:
        st.info("No closed trades in this session.")
