# --- UPDATE: Added Naked Order Support & Margin Simulation ---

with t_desk:
    if "curr_trade" in st.session_state:
        tr = st.session_state.curr_trade
        st.subheader(f"Execution: {tr['name']}")
        
        # New "Naked Sell" option added to the mode selector
        mode = st.radio("Instrument", ["Cash", "Options", "Spreads", "Naked Sell"], horizontal=True)
        
        c_q, c_sl, c_tp = st.columns(3)
        lot_key = tr['ticker'].replace(".NS","").replace("^","").replace("NSEI","NIFTY")
        lot_size = NSE_LOTS.get(lot_key, 1)
        lots = c_q.number_input("Lots", min_value=1, value=1)
        total_qty = lots * lot_size
        
        # Risk thresholds
        sl_pct = c_sl.number_input("Stop Loss %", value=10.0 if "Naked" in mode else 5.0)
        tp_pct = c_tp.number_input("Take Profit %", value=20.0)

        if mode == "Naked Sell":
            st.warning("⚠️ NAKED SELLING: Potential for unlimited loss. Requires high margin.")
            col1, col2 = st.columns(2)
            strike = col1.number_input("Strike to SELL", value=int(round(tr['market_price']/50)*50), step=50)
            otype = col2.selectbox("Type", ["CE (Naked Call)", "PE (Naked Put)"])
            opt_tk = get_option_ticker(tr['ticker'], strike, otype[:2], expiry)
            
            # Simulation of NSE SPAN + Exposure Margin (approx 1.5L for Nifty)
            simulated_margin = 150000.0 * lots 
            premium_received = fetch_live_price(opt_tk) * total_qty
            
            st.info(f"Estimated NSE Margin Required: ₹{simulated_margin:,.2f} | Premium Credit: ₹{premium_received:,.2f}")
            
            if st.button(f"EXECUTE NAKED SELL @ ₹{fetch_live_price(opt_tk)}"):
                if st.session_state.fund_balance >= simulated_margin:
                    # In naked selling, you get the premium but margin is blocked
                    st.session_state.fund_balance -= (simulated_margin - premium_received)
                    st.session_state.portfolio.append({
                        "name": f"NAKED {otype} {strike}", "ticker": opt_tk, "entry": fetch_live_price(opt_tk), 
                        "qty": total_qty, "side": "SELL", "margin": simulated_margin,
                        "sl": fetch_live_price(opt_tk) * (1 + sl_pct/100), # SL is above entry for sellers
                        "tp": fetch_live_price(opt_tk) * (1 - tp_pct/100)
                    })
                    st.rerun()
