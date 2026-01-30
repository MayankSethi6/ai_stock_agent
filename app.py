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

# 2. UI
ticker = st.sidebar.text_input("Stock Ticker", value="NVDA")
if st.sidebar.button("Run AI Analysis"):
    try:
        # DATA FETCHING
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        
        if hist.empty:
            st.error(f"Could not find data for {ticker}. Check the symbol.")
            st.stop()

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
            
            with st.spinner("Analyzing..."):
                try:
                    # NEW 2026 METHOD CALL
                    response = client.models.generate_content(
                        model="gemini-2.0-flash",
                        contents=f"Analyze {ticker} based on this data:\n{data_summary}\nGive a BUY/SELL/HOLD signal."
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
