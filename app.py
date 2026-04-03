import streamlit as st
import pandas as pd
import requests
from datetime import datetime, date
from openai import OpenAI
from google import genai
from groq import Groq
from jugaad_data.nse import NSELive

# --- 1. PERSISTENT SESSION STATE ---
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

# --- 2. DATA ENGINES (0 TOKENS) ---

def get_market_movers():
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers, timeout=5)
        url = "https://www.nseindia.com/api/live-analysis-top-gainers-losers?index=NIFTY"
        response = session.get(url, headers=headers, timeout=5)
        data = response.json()
        gainers = pd.DataFrame(data['gainers']['data']).head(5)[['symbol', 'ltp', 'pChange']]
        losers = pd.DataFrame(data['losers']['data']).head(5)[['symbol', 'ltp', 'pChange']]
        gainers['Trend'], losers['Trend'] = "🚀 Gainer", "📉 Loser"
        return pd.concat([gainers, losers]).rename(columns={'pChange': 'netPrice'})
    except: return pd.DataFrame()

def fetch_nse_price_only(symbol, is_opt=False, **kwargs):
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

# --- 3. EXECUTION LOGIC ---

def run_monitored_ai(prompt):
    try:
        res = st.session_state.gemini_client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
        st.session_state.token_log["Gemini 3"] += 1
        return res.text
    except:
        try:
            res = st.session_state.groq_client.chat.completions.create(model="llama-4-scout-17b", messages=[{"role": "user", "content": prompt}])
            st.session_state.token_log["Groq/Llama"] += 1
            return res.choices[0].message.content
        except: return "❌ Quota Exhausted."

def execute_order(symbol, strike, otype, expiry, lots, mode, premium):
    qty = lots * (50 if "NIFTY" in symbol else 15)
    margin = (165000 * lots) if mode == "Naked Sell" else (premium * qty)
    
    if st.session_state.fund_balance >= margin:
        st.session_state.fund_balance -= margin
        st.session_state.portfolio.append({
            "symbol": symbol, "strike": strike, "otype": otype, "expiry": expiry,
            "entry": premium, "qty": qty, "margin": margin, "mode": mode
        })
        return True
    return False

# --- 4. UI BUILD ---

with st.sidebar:
    st.header("📊 Global Sync")
    if st.button("🔄 SYNC ALL (Price & Market)", type="primary", use_container_width=True):
        st.session_state.movers_data = get_market_movers()
        st.session_state.last_sync = datetime.now().strftime("%H:%M:%S")
        st.session_state.active_asset['price'] = fetch_nse_price_only(st.session_state.active_asset['symbol'])
        st.rerun()
    st.write(f"Last Sync: **{st.session_state.last_sync}**")
    st.divider()
    st.session_state.auto_trade_enabled = st.checkbox("⚡ Enable Auto-Trade")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    if st.button("🚨 HARD RESET"):
        st.session_state.clear()
        st.rerun()

t_movers, t_desk, t_port, t_hist = st.tabs(["📈 Top 10 Movers", "🚀 Execution Desk", "📊 P/L", "📜 History"])

with t_movers:
    if st.session_state.movers_data.empty: st.info("Sync in sidebar to load Top 10.")
    else:
        for _, row in st.session_state.movers_data.iterrows():
            c1, c2, c3, c4 = st.columns([1, 1, 1, 3])
            c1.write(f"**{row['symbol']}**"); c2.write(f"₹{row['ltp']}"); c3.write(row['Trend'])
            if c4.button(f"🧠 Advice", key=f"mv_{row['symbol']}"):
                adv = run_monitored_ai(f"Stock {row['symbol']} @ {row['ltp']}. Action: STRONG BUY/SELL/HOLD?")
                st.info(adv)
                if st.session_state.auto_trade_enabled and ("STRONG" in adv.upper()):
                    mode = "Naked Buy" if "BUY" in adv.upper() else "Naked Sell"
                    execute_order(row['symbol'], int(row['ltp']), "CE", date(2026, 4, 30), 1, f"Auto-{mode}", row['ltp'])

with t_desk:
    st.subheader("Manual Option Order")
    c1, c2 = st.columns([3, 1])
    sym = c1.text_input("Ticker Symbol", value=st.session_state.active_asset['symbol']).upper()
    if c2.button("Sync Price"): 
        st.session_state.active_asset = {"symbol": sym, "price": fetch_nse_price_only(sym)}
        st.rerun()
    
    ltp = st.session_state.active_asset['price']
    st.write(f"Current Market Price: **₹{ltp:,.2f}**")
    
    st.divider()
    col1, col2, col3 = st.columns(3)
    mode = col1.selectbox("Trade Mode", ["Naked Buy", "Naked Sell"])
    strike = col2.number_input("Strike", value=int(ltp) if ltp > 0 else 22000, step=50)
    otype = col3.selectbox("Option Type", ["CE", "PE"])
    
    col4, col5 = st.columns(2)
    expiry = col4.date_input("Expiry Date", value=date(2026, 4, 30))
    lots = col5.number_input("Lots", min_value=1, step=1)

    premium = fetch_nse_price_only(sym, True, strike=strike, otype=otype, expiry=expiry) or 50.0
    st.info(f"LTP Premium: ₹{premium} | Est. Margin Req: ₹{(165000*lots) if mode == 'Naked Sell' else (premium*lots*50):,.2f}")
    
    if st.button("🚀 TRANSMIT ORDER", type="primary", use_container_width=True):
        if execute_order(sym, strike, otype, expiry, lots, mode, premium):
            st.success("Order Executed.")
            st.rerun()
        else: st.error("Insufficient Cash.")

with t_port:
    total_pnl = 0
    for i, pos in enumerate(st.session_state.portfolio):
        cur = fetch_nse_price_only(pos['symbol'], True, strike=pos['strike'], otype=pos['otype'], expiry=pos['expiry'])
        cur = cur if cur > 0 else pos['entry']
        pnl = (cur - pos['entry']) * pos['qty'] if "Buy" in pos['mode'] else (pos['entry'] - cur) * pos['qty']
        total_pnl += pnl
        with st.expander(f"{pos['symbol']} | {pos['mode']} | P/L: ₹{pnl:,.2f}"):
            if st.button("Square Off", key=f"sq_{i}"):
                st.session_state.fund_balance += (pos['margin'] + pnl)
                st.session_state.history.append({"Symbol": pos['symbol'], "P&L": pnl, "Date": datetime.now()})
                st.session_state.portfolio.pop(i); st.rerun()
    st.metric("Total Unrealized P/L", f"₹{total_pnl:,.2f}", delta=total_pnl)

with t_hist:
    if st.session_state.history: st.table(pd.DataFrame(st.session_state.history))
