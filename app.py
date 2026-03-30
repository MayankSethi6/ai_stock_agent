import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from fpdf import FPDF
import requests
from datetime import datetime, timedelta

# --- 1. INITIALIZATION ---
st.set_page_config(page_title="AI Alpha Quant", layout="wide", page_icon="💹")

if 'client' not in st.session_state:
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.session_state.client = genai.Client(api_key=api_key)
    except Exception:
        st.error("Missing GOOGLE_API_KEY in Secrets.")
        st.stop()

# --- 2. CORE UTILITY FUNCTIONS ---

def calculate_indicators(df):
    """Adds technical indicators for more robust analysis."""
    # RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Moving Averages
    df['SMA_20'] = df['Close'].rolling(window=20).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    # Volatility (ATR-like)
    df['Volatility'] = df['High'] - df['Low']
    return df

def get_options_data(ticker_symbol):
    """Fetches near-the-money option chain data."""
    try:
        stock = yf.Ticker(ticker_symbol)
        expirations = stock.options
        if not expirations:
            return None
        
        # Get the closest expiration
        opt = stock.option_chain(expirations[0])
        calls = opt.calls[['strike', 'lastPrice', 'openInterest', 'volume']].head(5)
        puts = opt.puts[['strike', 'lastPrice', 'openInterest', 'volume']].head(5)
        return {"calls": calls, "puts": puts, "expiry": expirations[0]}
    except:
        return None

def get_exchange_rate():
    try:
        data = yf.Ticker("USDINR=X").history(period="1d")
        return data['Close'].iloc[-1]
    except:
        return 83.5

def get_ticker_and_logo(query):
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers).json()
        ticker_symbol = response['quotes'][0]['symbol'] if response.get('quotes') else query.upper().strip()
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        website = info.get('website', '').replace('https://', '').split('/')[0]
        return ticker_symbol, info.get('longName', ticker_symbol), website
    except:
        return None, None, None

# --- 3. DASHBOARD UI ---
st.title("Autonomous Equity & Options Agent 🤖")

with st.sidebar:
    st.header("Analysis Parameters")
    user_query = st.text_input("Ticker (e.g., TATAMOTORS.NS, TSLA)", "RELIANCE.NS")
    view_type = st.radio("Prediction View", ["1 Week", "1 Month"])
    
    if st.button("Generate Deep Research"):
        with st.spinner("Analyzing Technicals & Option Chains..."):
            ticker, name, domain = get_ticker_and_logo(user_query)
            if ticker:
                # 1. Fetch Historicals
                period = "3mo" if view_type == "1 Month" else "1mo"
                hist = yf.Ticker(ticker).history(period=period)
                hist = calculate_indicators(hist)
                
                # 2. Fetch Options
                options = get_options_data(ticker)
                
                # 3. Construct AI Prompt with "Critical Sources" Logic
                recent_data = hist.tail(15).to_string()
                opt_str = f"Option Chain for {options['expiry']}: \nCalls: {options['calls'].to_string()}\nPuts: {options['puts'].to_string()}" if options else "No Options Data"
                
                prompt = f"""
                Act as a Senior Quant Analyst. Analyze {name} ({ticker}) for a {view_type} outlook.
                
                CRITICAL DATA:
                1. Technicals (Recent): {recent_data}
                2. Market Volatility: RSI and Moving Averages (SMA20/50).
                3. Options Sentiment: {opt_str}
                
                REQUIRED OUTPUT:
                - SIGNAL: Clear BUY, SELL, or HOLD.
                - RATIONALE: Support with RSI and Trend analysis.
                - OPTIONS STRATEGY: Suggest a specific Strike Price for a Call (CE) or Put (PE) based on Support/Resistance.
                - RISK LEVEL: High/Medium/Low.
                """
                
                try:
                    response = st.session_state.client.models.generate_content(
                        model="gemini-1.5-flash", 
                        contents=[prompt]
                    )
                    st.session_state.analysis_text = response.text
                    st.session_state.stock_data = hist
                    st.session_state.comp_info = {'ticker': ticker, 'name': name, 'domain': domain}
                except Exception as e:
                    st.error(f"AI Error: {e}")

# --- 4. DISPLAY ENGINE ---
if 'stock_data' in st.session_state and st.session_state.stock_data is not None:
    info = st.session_state.comp_info
    hist = st.session_state.stock_data
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"{info['name']} - {view_type} Outlook")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Price"))
        fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA_20'], line=dict(color='orange', width=1), name="SMA 20"))
        fig.update_layout(template="plotly_dark", height=500)
        st.plotly_chart(fig, use_container_width=True)
        
    with col2:
        st.write("### AI Recommendation")
        st.markdown(st.session_state.analysis_text)

    # Indicator Quick-View
    st.divider()
    m1, m2, m3 = st.columns(3)
    latest_rsi = hist['RSI'].iloc[-1]
    m1.metric("RSI (14)", f"{latest_rsi:.2f}", delta="Oversold" if latest_rsi < 30 else "Overbought" if latest_rsi > 70 else "Neutral")
    m2.metric("SMA 20", f"₹{hist['SMA_20'].iloc[-1]:,.2f}")
    m3.metric("Volatility (ATR)", f"{hist['Volatility'].iloc[-1]:,.2f}")
