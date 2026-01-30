import streamlit as st
import yfinance as yf
from google import genai  # Updated import
import plotly.graph_objects as go
import pandas as pd

# 1. CONFIGURATION
st.set_page_config(page_title="AI Stock Analyst", layout="wide")
GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
client = genai.Client(api_key=API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Use the latest stable model (Gemini 2.5 Flash is now the standard)
MODEL_ID = "gemini-2.5-flash"

# 2. APP UI HEADER
st.title("📈 Autonomous AI Stock Agent")
st.markdown("Enter a stock ticker to get real-time analysis and AI-powered recommendations.")

# 3. SIDEBAR INPUTS
ticker = st.sidebar.text_input("Stock Ticker (e.g., TSLA, NVDA, AAPL)", value="AAPL")
period = st.sidebar.selectbox("Data Period", ["1mo", "3mo", "6mo", "1y"])

if st.sidebar.button("Run Analysis"):
    try:
        # 4. DATA ACQUISITION
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        # 5. FEATURE ENGINEERING (Technical Indicators)
        hist['SMA_20'] = hist['Close'].rolling(window=20).mean()
        hist['RSI'] = 100 - (100 / (1 + hist['Close'].diff().where(hist['Close'].diff() > 0, 0).rolling(14).mean() / 
                                     -hist['Close'].diff().where(hist['Close'].diff() < 0, 0).rolling(14).mean()))

        # 6. VISUALIZATION
        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA_20'], name='SMA 20', line=dict(color='orange')))
            st.plotly_chart(fig, use_container_width=True)

        # 7. AI REASONING LAYER
        with col2:
            st.subheader("AI Analyst Insight")
            recent_data = hist.tail(10).to_string()
        # Updated Prompt for 2026 Agents
            prompt = f"""Analyze {ticker} with this data: {recent_data}. 
            Provide a BUY/SELL/HOLD recommendation with technical reasoning."""
    
        with st.spinner("Agent is reasoning..."):
            # Updated method call for the new SDK
            response = client.models.generate_content(
            model=MODEL_ID,
            contents=prompt
            )
            st.write(response.text)

        # 8. DATA TABLE
        st.subheader("Raw Technical Data")
        st.dataframe(hist.tail(5))

    except Exception as e:
        st.error(f"Error: {e}. Please ensure the ticker is valid.")
