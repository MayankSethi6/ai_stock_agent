import streamlit as st
import yfinance as yf
from google import genai
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, date

# --- 1. CONFIG & SYSTEM ---
st.set_page_config(page_title="NSE Alpha - Pro F&O", layout="wide", page_icon="🏛️")

# Official 2026 NSE Lot Sizes
NSE_LOTS = {"NIFTY": 65, "BANKNIFTY": 30, "FINNIFTY": 60, "RELIANCE": 250, "SBIN": 750, "TCS": 175, "INFY": 400}

if 'client' not in st.session_state:
    st.session_state.client = genai.Client(api_key=st.secrets["GOOGLE_API_KEY"])

# --- PERSISTENT STATE ---
for key, val in {'fund_balance': 1000000.0, 'portfolio': [], 'pnl_ledger': []}.items():
    if key not in st.session_state: st.session_state[key] = val

# --- 2. STRICT NSE SEARCH & UTILITIES ---
def strict_nse_search(query):
    q = query.upper().strip()
    
    if q in ["NIFTY", "NIFTY 50", "NIFTY50"]:
        return {"symbol": "^NSEI", "name": "Nifty 50 Index"}
    if q in ["BANKNIFTY", "BANK NIFTY", "NIFTY BANK"]:
        return {"symbol": "^NSEBANK", "name": "Nifty Bank Index"}
    if q in ["FINNIFTY", "FIN NIFTY", "NIFTY FIN SERVICE"]:
        return {"symbol": "^CNXFIN", "name": "Nifty Financial Services"}

    try:
        search = yf.Search(q + " NSE", max_results=5)
        for res in search.quotes:
            sym = res.get('symbol', '')
            if sym.endswith(".NS") or res.get('exchDisp') == "NSE":
                return {"symbol": sym, "name": res.get('shortname', sym)}
                
        if len(q) <= 10 and "." not in q:
            return {"symbol": q + ".NS", "name": q}
            
    except Exception:
        pass
        
    return None

def get_option_ticker(symbol, strike, opt_type, expiry_date):
    prefix = symbol.replace("^", "").replace("NSEI", "NIFTY").replace("NSEBANK", "BANKNIFTY").replace(".NS", "")
    expiry_str = expiry_date.strftime("%y%m%d") 
    suffix = "C" if "CE" in opt_type else "P"
    return f"{prefix}{expiry_str}{suffix}{int(strike)}.NS"

def fetch_live_price(ticker):
    """
    Bulletproofed price fetcher to prevent Yahoo 1d data errors.
    """
    try:
        tk = yf.Ticker(ticker)
        data = tk.history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
        
        # Fallback to fast_info if history fails (Crucial for illiquid F&O)
        info = tk.fast_info
        if 'last_price' in info and info['last_price'] is not None:
            return float(info['last_price'])
    except Exception:
        pass
    return 0.0

# --- 3. SIDEBAR ---
with st.sidebar:
    st.header("🇮🇳 NSE Pro Desk")
    st.metric("Liquid Cash", f"₹{st.session_state.fund_balance:,.2f}")
    
    if st.button("🔄 Clear App Cache & Reset"):
        st.session_state.fund_balance = 1000000.0
        st.session_state.portfolio = []
        st.session_state.pnl_ledger = []
        if "curr_trade" in st.session_state: 
            del st.session_state.curr_trade
        st.rerun()

    st.divider()
    user_query = st.text_input("Search Company", value="Nifty")
    asset = strict_nse_search(user_query)
    
    if asset:
        st.success(f"Focused: {asset['name']}")
        st.caption(f"Asset Ticker: `{asset['symbol']}`")
        
        if st.button("🔥 Run AI Quant Intel"):
            tk = yf.Ticker(asset['symbol'])
            hist = tk.history(period="5d")
            if not hist.empty:
                cp = float(hist['Close'].iloc[-1])
                prompt = f"Hedge Fund Manager. Analyze {asset['name']} (NSE) at price {cp}. Bullish/Bearish? Suggest strike."
                
                # FIX 1: 503 Server Error Handling
                try:
                    res = st.session_state.client.models.generate_content(model="gemini-3-flash-preview", contents=[prompt])
                    report_text = res.text
                except Exception:
                    report_text = "⚠️ The AI engine is experiencing heavy demand right now. Please try again in a few moments."
                
                st.session_state.curr_trade = {
                    "ticker": asset['symbol'], 
                    "name": asset['name'], 
                    "market_price": cp, 
                    "report": report_text,
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
        
        mode = st.radio("Instrument", ["Cash", "Options", "Spreads"], horizontal=True)
        
        lot_key = tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY").replace("NSEBANK","BANKNIFTY")
        lot_size = NSE_LOTS.get(lot_key, 1)
        lots = st.number_input(f"Quantity (Lots of {lot_size})", min_value=1, value=1)
        total_qty = lots * lot_size
        
        expiry_date = st.date_input("Expiry Date", value=date(2026, 4, 30))
        
        # --- MODE 1: CASH ---
        if mode == "Cash":
            side = st.radio("Action", ["BUY", "SELL"], horizontal=True)
            entry_price = st.number_input("Price", value=tr['market_price'])
            margin_mult = 0.10 if side == "BUY" else 1.0
            req_margin = entry_price * total_qty * margin_mult
            
            st.metric("Total Margin Blocked", f"₹{req_margin:,.2f}")
            
            if st.button(f"CONFIRM {side} EXECUTION"):
                if st.session_state.fund_balance >= req_margin:
                    st.session_state.fund_balance -= req_margin
                    st.session_state.portfolio.append({
                        "name": f"{tr['name']} (Cash)", "ticker": tr['ticker'], "entry": entry_price, 
                        "qty": total_qty, "side": side, "margin": req_margin, "mode": mode
                    })
                    st.toast(f"Position opened!")
                    st.rerun()
                else: st.error("Insufficient Funds!")
                
        # --- MODE 2: OPTIONS (SINGLE LEG) ---
        elif mode == "Options":
            side = st.radio("Action", ["BUY", "SELL"], horizontal=True)
            c1, c2, c3 = st.columns(3)
            opt_type = c1.selectbox("Type", ["CE", "PE"])
            strike = c2.number_input("Strike", value=int(round(tr['market_price']/50)*50), step=50)
            
            opt_ticker = get_option_ticker(tr['ticker'], strike, opt_type, expiry_date)
            
            if st.button("🔄 Refresh Strike Price"):
                st.session_state.last_strike_price = fetch_live_price(opt_ticker)
                
            live_prem = st.session_state.get('last_strike_price', 0.0)
            # FIX 2: If price is 0 (delisted error), default to a mock 100 premium instead of breaking
            entry_price = c3.number_input("Premium", value=live_prem if live_prem > 0 else 100.0)
            
            st.caption(f"Target: `{opt_ticker}` | Live Premium: ₹{live_prem}")
            
            margin_mult = 1.0 if side == "BUY" else 5.0 
            req_margin = entry_price * total_qty * margin_mult
            st.metric("Total Margin Blocked", f"₹{req_margin:,.2f}")
            
            if st.button(f"CONFIRM {side} EXECUTION"):
                if st.session_state.fund_balance >= req_margin:
                    st.session_state.fund_balance -= req_margin
                    st.session_state.portfolio.append({
                        "name": f"{tr['name']} {strike} {opt_type}", "ticker": opt_ticker, "entry": entry_price, 
                        "qty": total_qty, "side": side, "margin": req_margin, "mode": mode
                    })
                    st.toast(f"Position opened!")
                    st.rerun()
                else: st.error("Insufficient Funds!")

        # --- MODE 3: SPREADS (MULTI-LEG) ---
        elif mode == "Spreads":
            strategy = st.selectbox("Select Spread", ["Bull Call Spread", "Bear Put Spread", "Iron Condor"])
            atm_strike = int(round(tr['market_price']/50)*50)
            
            # Setup Plotly Visual arrays
            spot_range = np.linspace(atm_strike - 500, atm_strike + 500, 100)
            payoff = np.zeros_like(spot_range)
            
            # --- BULL CALL SPREAD ---
            if strategy == "Bull Call Spread":
                c1, c2 = st.columns(2)
                strike_buy = c1.number_input("Buy Strike (ITM/ATM)", value=atm_strike, step=50)
                strike_sell = c2.number_input("Sell Strike (OTM)", value=atm_strike + 100, step=50)
                
                ticker_buy = get_option_ticker(tr['ticker'], strike_buy, "CE", expiry_date)
                ticker_sell = get_option_ticker(tr['ticker'], strike_sell, "CE", expiry_date)
                
                if st.button("🔄 Fetch Spread Prices"):
                    st.session_state.spread_buy_price = fetch_live_price(ticker_buy)
                    st.session_state.spread_sell_price = fetch_live_price(ticker_sell)
                    
                p_buy = st.session_state.get('spread_buy_price', 150.0) if st.session_state.get('spread_buy_price', 0) > 0 else 150.0
                p_sell = st.session_state.get('spread_sell_price', 50.0) if st.session_state.get('spread_sell_price', 0) > 0 else 50.0
                
                net_premium = p_buy - p_sell
                req_margin = net_premium * total_qty
                
                # Payoff calculation
                payoff = (np.maximum(spot_range - strike_buy, 0) - p_buy) - (np.maximum(spot_range - strike_sell, 0) - p_sell)
                payoff *= total_qty
                
                st.write(f"📈 Buy Leg: ₹{p_buy} | 📉 Sell Leg: ₹{p_sell}")
                st.metric("Net Premium Paid (Total Margin)", f"₹{req_margin:,.2f}")
                
                if st.button("CONFIRM SPREAD EXECUTION"):
                    if st.session_state.fund_balance >= req_margin:
                        st.session_state.fund_balance -= req_margin
                        st.session_state.portfolio.append({"name": f"{tr['name']} {strike_buy} CE (Spread Buy)", "ticker": ticker_buy, "entry": p_buy, "qty": total_qty, "side": "BUY", "margin": req_margin*0.7, "mode": "Options"})
                        st.session_state.portfolio.append({"name": f"{tr['name']} {strike_sell} CE (Spread Sell)", "ticker": ticker_sell, "entry": p_sell, "qty": total_qty, "side": "SELL", "margin": req_margin*0.3, "mode": "Options"})
                        st.toast(f"Bull Call Spread Executed!")
                        st.rerun()
                    else: st.error("Insufficient Funds!")

            # --- BEAR PUT SPREAD ---
            elif strategy == "Bear Put Spread":
                c1, c2 = st.columns(2)
                strike_buy = c1.number_input("Buy Strike (ATM/ITM)", value=atm_strike, step=50)
                strike_sell = c2.number_input("Sell Strike (OTM)", value=atm_strike - 100, step=50)
                
                ticker_buy = get_option_ticker(tr['ticker'], strike_buy, "PE", expiry_date)
                ticker_sell = get_option_ticker(tr['ticker'], strike_sell, "PE", expiry_date)
                
                if st.button("🔄 Fetch Spread Prices"):
                    st.session_state.spread_buy_price = fetch_live_price(ticker_buy)
                    st.session_state.spread_sell_price = fetch_live_price(ticker_sell)
                    
                p_buy = st.session_state.get('spread_buy_price', 150.0) if st.session_state.get('spread_buy_price', 0) > 0 else 150.0
                p_sell = st.session_state.get('spread_sell_price', 50.0) if st.session_state.get('spread_sell_price', 0) > 0 else 50.0
                
                net_premium = p_buy - p_sell
                req_margin = net_premium * total_qty
                
                # Payoff calculation
                payoff = (np.maximum(strike_buy - spot_range, 0) - p_buy) - (np.maximum(strike_sell - spot_range, 0) - p_sell)
                payoff *= total_qty
                
                st.write(f"📉 Buy Leg: ₹{p_buy} | 📈 Sell Leg: ₹{p_sell}")
                st.metric("Net Premium Paid (Total Margin)", f"₹{req_margin:,.2f}")
                
                if st.button("CONFIRM SPREAD EXECUTION"):
                    if st.session_state.fund_balance >= req_margin:
                        st.session_state.fund_balance -= req_margin
                        st.session_state.portfolio.append({"name": f"{tr['name']} {strike_buy} PE (Spread Buy)", "ticker": ticker_buy, "entry": p_buy, "qty": total_qty, "side": "BUY", "margin": req_margin*0.7, "mode": "Options"})
                        st.session_state.portfolio.append({"name": f"{tr['name']} {strike_sell} PE (Spread Sell)", "ticker": ticker_sell, "entry": p_sell, "qty": total_qty, "side": "SELL", "margin": req_margin*0.3, "mode": "Options"})
                        st.toast(f"Bear Put Spread Executed!")
                        st.rerun()
                    else: st.error("Insufficient Funds!")

            # --- IRON CONDOR ---
            elif strategy == "Iron Condor":
                c1, c2, c3, c4 = st.columns(4)
                p_buy_strike = c1.number_input("Put Buy Strike", value=atm_strike - 200, step=50)
                p_sell_strike = c2.number_input("Put Sell Strike", value=atm_strike - 100, step=50)
                c_sell_strike = c3.number_input("Call Sell Strike", value=atm_strike + 100, step=50)
                c_buy_strike = c4.number_input("Call Buy Strike", value=atm_strike + 200, step=50)
                
                tk_p_buy = get_option_ticker(tr['ticker'], p_buy_strike, "PE", expiry_date)
                tk_p_sell = get_option_ticker(tr['ticker'], p_sell_strike, "PE", expiry_date)
                tk_c_sell = get_option_ticker(tr['ticker'], c_sell_strike, "CE", expiry_date)
                tk_c_buy = get_option_ticker(tr['ticker'], c_buy_strike, "CE", expiry_date)
                
                if st.button("🔄 Fetch Condor Prices"):
                    st.session_state.ic_pb = fetch_live_price(tk_p_buy)
                    st.session_state.ic_ps = fetch_live_price(tk_p_sell)
                    st.session_state.ic_cs = fetch_live_price(tk_c_sell)
                    st.session_state.ic_cb = fetch_live_price(tk_c_buy)
                    
                pb = st.session_state.get('ic_pb', 30.0) if st.session_state.get('ic_pb', 0) > 0 else 30.0
                ps = st.session_state.get('ic_ps', 80.0) if st.session_state.get('ic_ps', 0) > 0 else 80.0
                cs = st.session_state.get('ic_cs', 80.0) if st.session_state.get('ic_cs', 0) > 0 else 80.0
                cb = st.session_state.get('ic_cb', 30.0) if st.session_state.get('ic_cb', 0) > 0 else 30.0
                
                st.write(f"🛡️ P-Buy: ₹{pb} | 💰 P-Sell: ₹{ps} | 💰 C-Sell: ₹{cs} | 🛡️ C-Buy: ₹{cb}")
                
                net_credit = (ps + cs) - (pb + cb)
                spread_width = 100 
                req_margin = (spread_width - net_credit) * total_qty
                
                # Payoff calculation
                payoff_pb = np.maximum(p_buy_strike - spot_range, 0) - pb
                payoff_ps = ps - np.maximum(p_sell_strike - spot_range, 0)
                payoff_cs = cs - np.maximum(spot_range - c_sell_strike, 0)
                payoff_cb = np.maximum(spot_range - c_buy_strike, 0) - cb
                payoff = (payoff_pb + payoff_ps + payoff_cs + payoff_cb) * total_qty
                
                st.metric("Margin Required (Calculated)", f"₹{req_margin:,.2f}")
                
                if st.button("CONFIRM IRON CONDOR EXECUTION"):
                    if st.session_state.fund_balance >= req_margin:
                        st.session_state.fund_balance -= req_margin
                        legs = [
                            (f"IC Put Buy {p_buy_strike}", tk_p_buy, pb, "BUY"),
                            (f"IC Put Sell {p_sell_strike}", tk_p_sell, ps, "SELL"),
                            (f"IC Call Sell {c_sell_strike}", tk_c_sell, cs, "SELL"),
                            (f"IC Call Buy {c_buy_strike}", tk_c_buy, cb, "BUY")
                        ]
                        for name, tkr, prem, side in legs:
                            st.session_state.portfolio.append({
                                "name": f"{tr['name']} {name}", "ticker": tkr, "entry": prem, 
                                "qty": total_qty, "side": side, "margin": req_margin / 4, "mode": "Options"
                            })
                        st.toast(f"Iron Condor Executed!")
                        st.rerun()
                    else: st.error("Insufficient Funds!")

            # --- RENDER PAYOFF GRAPH ---
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=spot_range, y=payoff, mode='lines', name='Strategy Payoff', line=dict(color='orange', width=2)))
            fig.add_hline(y=0, line_dash="dash", line_color="white")
            fig.update_layout(
                title=f"{strategy} - Projected Payoff at Expiry",
                xaxis_title="Underlying Asset Spot Price (₹)",
                yaxis_title="Net Profit / Loss (₹)",
                template="plotly_dark",
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)

with t_port:
    st.subheader("Current Open Positions")
    if st.button("🔄 Sync Live P&L"): st.rerun()
    
    total_unrealized = 0
    if st.session_state.portfolio:
        for i, pos in enumerate(st.session_state.portfolio):
            current_price = fetch_live_price(pos['ticker'])
            if current_price == 0: current_price = pos['entry']
                
            if pos['side'] == "BUY":
                pnl = (current_price - pos['entry']) * pos['qty']
            else:
                pnl = (pos['entry'] - current_price) * pos['qty']
            
            total_unrealized += pnl
            pnl_color = "green" if pnl >= 0 else "red"
            
            with st.expander(f"{pos['name']} | {pos['side']} | P&L: :{pnl_color}[₹{pnl:,.2f}]"):
                st.write(f"Entry: ₹{pos['entry']} | Current: ₹{current_price} | Margin: ₹{pos['margin']:,.2f}")
                if st.button("SQUARE OFF", key=f"sq_{i}"):
                    st.session_state.fund_balance += (pos['margin'] + pnl)
                    st.session_state.pnl_ledger.append({"Asset": pos['name'], "Final P&L": pnl})
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        
        st.divider()
        st.metric("Total Unrealized P&L", f"₹{total_unrealized:,.2f}", delta=total_unrealized)
    else:
        st.info("No active positions.")
