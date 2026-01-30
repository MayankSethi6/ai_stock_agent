import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd

# 1. INITIALIZATION & SECRETS
st.set_page_config(page_title="AI Stock Agent 2026", layout="wide")

try:
    API_KEY = st.secrets["GOOGLE_API_KEY"]
    client = genai.Client(api_key=API_KEY)
except Exception:
    st.error("Credential Error: Please set GOOGLE_API_KEY in Streamlit Secrets.")
    st.stop()

# 2. UI HEADER
st.title("🤖 Autonomous AI Stock Intelligence")

# 3. SIDEBAR WITH PERSISTENCE
ticker = st.sidebar.text_input("Enter Ticker", value="NVDA", key="ticker_input").upper()
period_options = {"1 Month": "1mo", "3 Month": "3mo", "1 Year": "1y"}
# Use a key to ensure Streamlit tracks the selection state correctly
selected_label = st.sidebar.selectbox("Analysis Window", options=list(period_options.keys()), key="period_select")
yf_period = period_options[selected_label]

if st.sidebar.button("Execute Full Analysis"):
    try:
        # DATA ACQUISITION
        stock = yf.Ticker(ticker)
        hist = stock.history(period=yf_period)
        
        # FIX: Robust news fetching for 2026 yfinance structure
        raw_news = stock.news
        headlines = []
        if raw_news:
            for item in raw_news[:5]:
                # 2026 yfinance news items may use 'title' or 'content' depending on source
                # Using .get() prevents the 'title' KeyError
                title = item.get('title') or item.get('summary') or "Headline unavailable"
                link = item.get('link') or "#"
                headlines.append({"title": title, "link": link})
        
        if hist.empty:
            st.error(f"No data found for {ticker}. Please check the ticker symbol.")
            st.stop()

        # 4. DATA PREPROCESSING (Technical Indicators)
        hist['SMA_20'] = hist['Close'].rolling(window=20).mean()
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        hist['RSI'] = 100 - (100 / (1 + (gain / loss)))

        # 5. UI LAYOUT
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Interactive Chart
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'], name="Price")])
            fig.add_trace(go.Scatter(x=hist.index, y=hist['SMA_20'], name='SMA 20', line=dict(color='orange')))
            fig.update_layout(title=f"{ticker} Technicals ({selected_label})", template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
            
            # News Section
            st.subheader("📰 Market Headlines")
            if headlines:
                for h in headlines:
                    st.markdown(f"• [{h['title']}]({h['link']})")
            else:
                st.write("No recent news found.")

        with col2:
            st.subheader("🧠 AI Agent Reasoning")
            
            # NLP Layer: Sentiment Synthesis
            news_text = " ".join([h['title'] for h in headlines])
            tech_data = hist.tail(5).to_string()
            
            prompt = f"""
            Identify as a Wall Street Analyst. 
            Stock: {ticker}
            Recent News: {news_text}
            Recent Data: {tech_data}
            
            Instructions: Provide a clear 'Signal' (BUY/SELL/HOLD) and 3 bullet points on the 'Why' considering both technicals and sentiment.
            """
            
            with st.spinner("Agent is synthesizing data..."):
                try:
                    response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
                    st.info(response.text)
                except Exception as ai_e:
                    st.error(f"AI Reasoning Error: {ai_e}")

    except Exception as e:
        st.error(f"Operational Error: {e}")

# FOOTER NEXT STEP
st.divider()
st.caption("Data provided by yfinance and processed by Gemini 2.0. This is not financial advice.")
