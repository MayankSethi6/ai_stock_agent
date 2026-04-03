import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. PERSISTENT SESSION STATE ---
# Ensures history, portfolio, and cash stay until a Hard Reset
for key, val in {
    'fund_balance': 1000000.0, 
    'portfolio': [], 
    'history': [], 
    'token_log': {"Gemini 3": 0, "Groq/Llama": 0, "OpenAI": 0},
    'auto_trade_enabled': False,
    'active_asset': {"symbol": "NIFTY", "price": 0.0},
    'ai_report': None
}.items():
    if key not in st.session_state: st.session_state[key] = val

# Initialize API Clients
if 'openai_client' not in st.session_state:
    st.session_state.openai_client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
if 'gemini_client' not in st.session_state:
    st.session_state.gemini_client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])
if 'groq_client' not in st.session_state:
    st.session_state.groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- 2. RESILIENT DATA ENGINES (0 TOKENS) ---

def get_market_movers():
    """Directly pings NSE API to avoid library import errors."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=10)
        url = "https://www.nseindia.com/api/live-analysis-top-gainers-losers?index=NIFTY"
        response = session.get(url, headers=headers, timeout=10)
        data = response.json()
        
        gainers = pd.DataFrame(data['gainers']['data']).head(5)
        gainers = gainers[['symbol', 'ltp', 'pChange']].rename(columns={'pChange': 'netPrice'})
        gainers['Trend'] = "🚀 Gainer"
        
        losers = pd.DataFrame(data['losers']['data']).head(5)
        losers = losers[['symbol', 'ltp', 'pChange']].rename(columns={'pChange': 'netPrice'})
        losers['Trend'] = "📉 Loser"
        
        return pd.concat([gainers, losers])
    except Exception:
        return pd.DataFrame()

def fetch_nse_price_only(symbol, is_opt=False, **kwargs):
    """Zero AI Tokens. Pure market data fetcher."""
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
                    side = kwargs.get('otype')
                    return row[side]['lastPrice'] if row[side] else 0.0
    except: return 0.0

# --- 3. MULTI-AI STRATEGY ENGINE ---

def run_monitored_ai(prompt):
    with st.status("🧠 AI Analysis (Consuming Tokens)...") as status:
        # TIER 1: Gemini 3 Flash Preview
        try:
            res = st.session_state.gemini_client.models.generate_content(
                model="gemini-3-flash-preview", contents=[prompt]
            )
            st.session_state.token_log["Gemini 3"] += 1
            return f"♊ **Gemini 3:**\n\n{res.text}"
        except:
            # TIER 2: Groq (Llama 4)
            try:
                res = st.session_state.groq_client.chat.completions.create(
                    model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}]
                )
                st.session_state.token_log["Groq/Llama"] += 1
                return f"🦙 **Groq:**\n\n{res.choices[0].message.content}"
            except:
                return "❌ All AI Quotas Exhausted."

def process_auto_trade(symbol, ltp, advice):
    """Executes trade if Auto-Trade is ON and signal is STRONG."""
    adv = advice.upper()
    mode = "Naked Buy" if "STRONG BUY" in adv else "Naked Sell" if "STRONG SELL" in adv else None
    
    if mode and st.session_state.auto_trade_enabled:
        qty = 50 if "NIFTY" in symbol else 15
        margin = 165000 if "Sell" in mode else (float(ltp) * qty)
        if st.session_state.fund_balance >= margin:
            st.session_state.fund_balance -= margin
            st.session_state.portfolio.append({
                "symbol": symbol, "strike": int(ltp), "otype": "CE" if "Buy" in mode else "PE", 
                "expiry": date(2026, 4, 30), "entry": float(ltp), "qty": qty, 
                "margin": margin, "mode": f"Auto-{mode}"
            })
            return True
    return False

# --- 4. MAIN UI ---

st.title("🏛️ NSE Alpha Terminal")

with st.sidebar:
    st.header("📊 Token Dashboard")
    for eng, count in st.session_state.token_log.items():
        st.write(f"● {eng}: **{count}** calls")
    st.divider()
    st.session_state.auto_trade_enabled = st.checkbox("⚡ Enable Auto-Trade", value=False)
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    if st.button("🚨 HARD RESET SYSTEM"):
        st.session_state.clear()
        st.rerun()

t_movers, t_desk, t_port, t_hist, t_ai = st.tabs(["📈 Movers", "🚀 Execution", "📊 P/L", "📜 History", "🧠 AI Quant"])

with t_movers:
    st.subheader("Market High-Activity Stocks")
    movers_df = get_market_movers()
    if not movers_df.empty:
        for _, row in movers_df.iterrows():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            c1.write(f"**{row['symbol']}**")
            c2.write(f"₹{row['ltp']}")
            c3.write(row['Trend'])
            if c4.button(f"🧠 Advice", key=f"mv_{row['symbol']}"):
                advice = run_monitored_ai(f"Stock {row['symbol']} @ {row['ltp']} is a {row['Trend']}. Give 1 sentence starting with STRONG BUY, STRONG SELL, or HOLD.")
                st.info(advice)
                if process_auto_trade(row['symbol'], row['ltp'], advice):
                    st.success(f"Executed Auto-Trade for {row['symbol']}!")
    else: st.info("Waiting for NSE API data...")

with t_desk:
    st.subheader("Execution Desk")
    c1, c2 = st.columns([3, 1])
    sym = c1.text_input("Symbol", value=st.session_state.active_asset['symbol']).upper()
    if c2.button("Sync LTP (0 Tokens)"):
        st.session_state.active_asset = {"symbol": sym, "price": fetch_nse_price_only(sym)}
    
    ltp = st.session_state.active_asset['price']
    st.write(f"**Current Market Price:** ₹{ltp:,.2f}")
    
    col1, col2, col3 = st.columns(3)
    mode = col1.selectbox("Mode", ["Naked Buy", "Naked Sell"])
    strike = col2.number_input("Strike", value=int(ltp) if ltp > 0 else 22000, step=50)
    otype = col3.selectbox("Type", ["CE", "PE"])
    expiry = st.date_input("Expiry", value=date(2026, 4, 30))
    lots = st.number_input("Lots", min_value=1)

    premium = fetch_nse_price_only(sym, True, strike=strike, otype=otype, expiry=expiry) or 50.0
    qty = lots * (50 if "NIFTY" in sym else 15)
    margin = (165000 * lots) if mode == "Naked Sell" else (premium * qty)
    
    if st.button("🚀 EXECUTE MANUAL TRADE", type="primary", use_container_width=True):
        if st.session_state.fund_balance >= margin:
            st.session_state.fund_balance -= margin
            st.session_state.portfolio.append({
                "symbol": sym, "strike": strike, "otype": otype, "expiry": expiry, 
                "entry": premium, "qty": qty, "margin": margin, "mode": mode
            })
            st.rerun()

with t_port:
    st.subheader("Live Portfolio")
    if st.button("🔄 Sync Prices"): st.rerun()
    total_pnl = 0
    for i, pos in enumerate(st.session_state.portfolio):
        cur = fetch_nse_price_only(pos['symbol'], True, strike=pos['strike'], otype=pos['otype'], expiry=pos['expiry'])
        cur = cur if cur > 0 else pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        total_pnl += pnl
        with st.expander(f"{pos['symbol']} | ₹{pnl:,.2f}"):
            if st.button("Square Off", key=f"sq_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.history.append({"Asset": pos['symbol'], "P&L": pnl, "Date": datetime.now()})
                st.session_state.portfolio.pop(i)
                st.rerun()
    st.metric("Portfolio P/L", f"₹{total_pnl:,.2f}", delta=total_pnl)

with t_hist:
    if st.session_state.history: st.dataframe(pd.DataFrame(st.session_state.history))

with t_ai:
    if st.button("🔥 GENERATE GENERAL STRATEGY"):
        st.markdown(run_monitored_ai("Provide a Nifty option spread strategy for today's market."))
