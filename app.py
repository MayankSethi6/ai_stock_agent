import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Pro F&O", layout="wide", page_icon="🏛️")

# Official March 2026 NSE Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. STRICT NSE SEARCH & UTILITIES ---
def strict_nse_search(query):
    """
    Restricts search results strictly to NSE Indian markets.
    """
    q = query.upper().strip()
    
    # Direct Index Mapping (NSE only)
    if q in ["NIFTY", "NIFTY 50", "NIFTY50"]:
        return {"symbol": "^NSEI", "name": "Nifty 50 Index"}
    if q in ["BANKNIFTY", "BANK NIFTY", "NIFTY BANK"]:
        return {"symbol": "^NSEBANK", "name": "Nifty Bank Index"}
    if q in ["FINNIFTY", "FIN NIFTY", "NIFTY FIN SERVICE"]:
        return {"symbol": "^CNXFIN", "name": "Nifty Financial Services"}

    try:
        # Pull global results but filter aggressively for the '.NS' exchange extension
        search = yf.Search(q + " NSE", max_results=5)
        for res in search.quotes:
            sym = res.get('symbol', '')
            if sym.endswith(".NS") or res.get('exchDisp') == "NSE":
                return {"symbol": sym, "name": res.get('shortname', sym)}
                
        # Strict Fallback: If no results found, force the .NS ticker protocol
        if len(q) <= 10 and "." not in q:
            return {"symbol": q + ".NS", "name": q}
            
    except Exception:
        pass
        
    return None

def get_option_ticker(symbol, strike, opt_type, expiry_date):
    """
    Formats standard NSE Ticker for Yahoo Finance options:
    [SYMBOL][YY][MM][DD][C/P][STRIKE].NS
    """
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    expiry_str = expiry_date.strftime("%y%m%d") # E.g., 260430 for April 30, 2026
    suffix = "C" if "CE" in opt_type else "P"
    return f"{prefix}{expiry_str}{suffix}{int(strike)}.NS"

def fetch_live_price(ticker):
    try:
        data = yf.Ticker(ticker).history(period="1d")
        return float(data['Close'].iloc[-1]) if not data.empty else 0.0
    except: 
        return 0.0

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Pro Desk")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    user_query = st.text_input("Search Company (e.g. Reliance, SBI, Nifty)", value="Nifty")
    
    # Calling the strict NSE restricted search
    asset = strict_nse_search(user_query)
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        st.caption(f"Asset Ticker: `{asset['symbol']}`")
        
        lot_key = asset['symbol'].replace(".NS","").replace("^","").replace("NSEI","NIFTY").replace("NSEBANK","BANKNIFTY")
        lot_size = NSE_LOTS.get(lot_key, 1)
        lots = st.number_input("Lots", min_value=1, value=1)
        total_qty = lots * lot_size
        
        if st.button("🔥 Run AI Quant Intel"):
            tk = yf.Ticker(asset['symbol'])
            hist = tk.history(period="5d")
            if not hist.empty:
                cp = float(hist['Close'].iloc[-1])
                prompt = f"Hedge Fund Manager. Analyze {asset['name']} (NSE) at price {cp}. Bullish/Bearish? Suggest strike."
                res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                
                st.session_state.curr_trade = {
                    "ticker": asset['symbol'], 
                    "name": asset['name'], 
                    "market_price": cp, 
                    "report": res.text,
                    "qty": total_qty,
                    "lot_key": lot_key
                }
                st.rerun()
    else:
        st.warning("No asset found. Ensure you type valid Indian company names.")

# --- 4. TABS ---
t_ai, t_desk, t_port = st.tabs(["🧠 Alpha Strategy", "🚀 Execution Desk", "📊 Live Portfolio"])

with t_ai:
    if "curr_trade" in st.session_state:
        st.info(st.session_state.curr_trade['report'])
        st.metric("Current Spot Price", f"₹{st.session_state.curr_trade['market_price']:,.2f}")
    else: 
        st.warning("Run Intel in the sidebar to generate a strategy.")

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader("Order Configuration")
        
        mode = st.radio("Instrument", ["Cash", "Options"], horizontal=True)
        side = st.radio("Action", ["BUY", "SELL"], horizontal=True)
        
        if mode == "Options":
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Type", ["CE", "PE"])
            # Auto round to nearest 50 point strike
            strike = c2.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            
            # --- EXPIRY DATE SUPPORT ---
            # Default to last Thursday of April 2026
            expiry_date = st.date_input("Expiry Date", value=date(2026, 4, 30))
            
            opt_ticker = get_option_ticker(tr['ticker'], strike, opt_type, expiry_date)
            
            if 'last_strike_price' not in st.session_state or st.button("🔄 Refresh Strike Price"):
                st.session_state.last_strike_price = fetch_live_price(opt_ticker)
            
            # Use fetched premium or hard default if the contract didn't trade yet
            default_premium = st.session_state.last_strike_price if st.session_state.last_strike_price > 0 else 100.0
            entry_price = c3.number_input("Premium", value=default_premium)
            
            st.caption(f"Options Ticker Targeted: `{opt_ticker}` | Live Premium: ₹{st.session_state.last_strike_price}")
            
            # Selling an option requires capital margin equivalent to standard NSE regulations
            margin_mult = 1.0 if side == "BUY" else 5.0 
            display_name = f"{tr['name']} {strike} {opt_type} ({expiry_date.strftime('%d%b')})"
            track_ticker = opt_ticker
        else:
            entry_price = st.number_input("Price", value=tr['market_price'])
            margin_mult = 0.10 if side == "BUY" else 1.0
            display_name = f"{tr['name']} (Cash)"
            track_ticker = tr['ticker']

        req_margin = entry_price * tr['qty'] * margin_mult
        st.metric("Total Margin Blocked", f"₹{req_margin:,.2f}")

        if st.button(f"CONFIRM {side} EXECUTION"):
            if st.session_state.fund_balance >= req_margin:
                st.session_state.fund_balance -= req_margin
                st.session_state.portfolio.append({
                    "name": display_name,
                    "ticker": track_ticker,
                    "entry": entry_price, 
                    "qty": tr['qty'], 
                    "side": side, 
                    "margin": req_margin, 
                    "mode": mode
                })
                st.toast(f"Position opened for {display_name}")
                st.rerun()
            else: 
                st.error("Insufficient Funds to clear this margin!")

with t_port:
    st.subheader("Current Open Positions")
    if st.button("🔄 Sync Live P&L"): 
        st.rerun()
    
    total_unrealized = 0
    
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            current_price = fetch_live_price(pos['ticker'])
            
            # Protect against empty data returning 0 and ruining P&L visually
            if current_price == 0: 
                current_price = pos['entry']
                
            # Calculating P&L depending on execution direction
            if pos['side'] == "BUY":
                pnl = (current_price - pos['entry']) * pos['qty']
            else:
                pnl = (pos['entry'] - current_price) * pos['qty']
            
            total_unrealized += pnl
            pnl_color = "green" if pnl >= 0 else "red"
            
            with st.expander(f"{pos['name']} | {pos['side']} | P&L: :{pnl_color}[₹{pnl:,.2f}]"):
                st.write(f"Entry: ₹{pos['entry']} | Current: ₹{current_price} | Margin Tied Up: ₹{pos['margin']:,.2f}")
                if st.button("SQUARE OFF", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.pnl_ledger.append({"Asset": pos['name'], "Final P&L": pnl})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        
        st.divider()
        st.metric("Total Unrealized P&L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else:
        st.info("No active positions are being tracked right now.")
