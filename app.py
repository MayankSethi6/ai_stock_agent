import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd

# 1. SETUP
st.set_page_config(page_title="AI Stock Agent", layout="wide")

try:
    # Use st.secrets locally or in Streamlit Cloud
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("API Key not found. Please set GOOGLE_API_KEY in your secrets.")
    st.stop()

# 2. APP UI HEADER
st.title("📈 Autonomous AI Stock Agent")
st.markdown("Enter a stock ticker to get real-time analysis and AI-powered recommendations.")

# 2. UI
ticker = st.sidebar.text_input("Stock Ticker (e.g., TSLA, NVDA, AAPL)", value="AAPL")
period = st.sidebar.selectbox("Data Period", ["1mo", "3mo", "6mo", "1y"])

if st.sidebar.button("Run AI Analysis"):
    try:
        # DATA FETCHING
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if hist.empty:
            st.error(f"Could not find data for {ticker}. Check the symbol.")
            st.stop()

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
        
        # DISPLAY DATA
        col1, col2 = st.columns([2, 1])
        with col1:
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            st.plotly_chart(fig, use_container_width=True)

        # AI ANALYSIS BLOCK
        with col2:
            st.subheader("AI Recommendation")
            data_summary = hist.tail(5).to_string()
            
            # Initializing response to None to prevent NameError
            response = None 
            
            # 4. GENERATING THE CONTENT
            st.markdown(f"### AI Recommendation\n{response.text}")
                # The new SDK uses: client.models.generate_content
            with st.spinner("AI Agent is analyzing market trends..."):
                try:
                    response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=f"Analyze this stock data for {ticker}: {recent_data}"
                    )

                except Exception as api_err:
                    st.error(f"AI API Error: {api_err}")

            # Check if response was successfully created before accessing .text
            if response:
                st.write(response.text)
            else:
                st.warning("The AI could not generate a response. Please try again.")

    except Exception as e:
        st.error(f"System Error: {e}")
