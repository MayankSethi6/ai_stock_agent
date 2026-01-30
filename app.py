import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd

# 1. SETUP & CLIENT INITIALIZATION
st.set_page_config(page_title="AI Stock Agent 2026", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("Credential Error: Please set GOOGLE_API_KEY in Streamlit Secrets.")
    st.stop()

# 2. UI HEADER
st.title("🤖 Autonomous AI Stock Intelligence")
ticker = st.sidebar.text_input("Enter Ticker", value="NVDA").upper()
period_map = {"1 Month": "1mo", "3 Month": "3mo", "1 Year": "1y"}
selected_period = st.sidebar.selectbox("Analysis Window", list(period_map.keys()))

if st.sidebar.button("Execute Full Analysis"):
    try:
        # DATA ACQUISITION
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period_map[selected_period])
        news = stock.news[:5] # Fetch top 5 recent headlines
        
        if hist.empty:
            st.error("Invalid Ticker or No Data Found.")
            st.stop()

        # 3. SENTIMENT ANALYSIS (NLP LAYER)
        headlines = [n['title'] for n in news]
        sentiment_prompt = f"Analyze the sentiment of these headlines for {ticker}: {headlines}. Return a score from -1 (Bearish) to 1 (Bullish) and a 1-sentence summary."
        
        with st.spinner("Analyzing Market Sentiment..."):
            sent_resp = client.models.generate_content(model="gemini-2.0-flash", contents=sentiment_prompt)
            # Simple logic to extract a score if the AI provides one, else default to 0
            sentiment_text = sent_resp.text

        # 4. VISUALIZATION (Decision Support)
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Candlestick Chart
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            fig.update_layout(title=f"{ticker} Technical Chart", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)
            
            # Display Recent News
            st.subheader("Latest Market News")
            for n in news:
                st.write(f"🔹 {n['title']} ([Link]({n['link']}))")

        with col2:
            st.subheader("AI Agent Reasoning")
            
            # Combine Technical + Sentiment for Final Reasoning
            tech_summary = hist.tail(3).to_string()
            final_prompt = f"""
            System: Senior Investment Strategist
            Ticker: {ticker}
            Recent Prices: {tech_summary}
            News Sentiment Analysis: {sentiment_text}
            
            Task: Provide a final BUY/SELL/HOLD signal with a 'Confidence Score' (0-100%).
            """
            
            with st.spinner("Generating Strategic Recommendation..."):
                final_resp = client.models.generate_content(model="gemini-2.0-flash", contents=final_prompt)
                st.info(final_resp.text)

    except Exception as e:
        st.error(f"Operational Error: {e}")
