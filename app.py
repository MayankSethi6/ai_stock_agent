import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from fpdf import FPDF
import requests

# --- 1. SETUP & AUTHENTICATION ---
st.set_page_config(page_title="AI Stock Agent 2026", layout="wide", page_icon="📈")

if 'client' not in st.session_state:
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.session_state.client = genai.Client(api_key=api_key)
    except Exception:
        st.error("Missing GOOGLE_API_KEY in Streamlit Secrets.")
        st.stop()

client = st.session_state.client

# --- 2. HELPER FUNCTIONS ---

def get_ticker_and_logo(query):
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers).json()
        ticker = response['quotes'][0]['symbol']
        stock_info = yf.Ticker(ticker).info
        website = stock_info.get('website', '').replace('http://', '').replace('https://', '').split('/')[0]
        name = stock_info.get('longName', ticker)
        return ticker, name, website
    except:
        return None, None, None

def generate_pdf(ticker, name, analysis):
    clean_analysis = analysis.replace('–', '-').replace('—', '-').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 15, f"AI Research: {name} ({ticker})", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, clean_analysis.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output()

# --- 3. DASHBOARD UI WITH TABS ---
tab1, tab2 = st.tabs(["🚀 Live Analysis", "📊 Model Accuracy"])

with tab1:
    st.title("Autonomous AI Stock Intelligence")
    st.sidebar.header("Agent Parameters")
    user_query = st.sidebar.text_input("Enter Company or Ticker", value="Tesla", key="live_search")
    time_period = st.sidebar.selectbox("History", ["1mo", "3mo", "6mo", "1y"], key="live_period")

    if st.sidebar.button("Run Live Analysis"):
        ticker, comp_name, domain = get_ticker_and_logo(user_query)
        if ticker:
            # Display Logo and Title
            col_l, col_t = st.columns([1, 8])
            with col_l: st.image(f"https://logo.clearbit.com/{domain}", width=60) if domain else None
            with col_t: st.subheader(f"{comp_name} ({ticker})")

            hist = yf.Ticker(ticker).history(period=time_period)
            
            # 1. Display Chart First
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            fig.update_layout(title="Technical Price Chart", template="plotly_dark")
            st.plotly_chart(fig, use_container_width=True)

            # 2. Display AI Analysis Below the Chart
            st.markdown("---")
            st.write("### 🧠 AI Strategic Analysis")
            data_summary = hist.tail(5).to_string()
            prompt = f"Analyze {comp_name} ({ticker}). Latest data:\n{data_summary}\nProvide a BUY/SELL/HOLD signal with reasoning."
            
            try:
                response = client.models.generate_content(model="gemini-2.0-flash", contents=[prompt])
                analysis_text = response.text
                st.info(analysis_text)
                
                # PDF Download
                pdf_data = generate_pdf(ticker, comp_name, analysis_text)
                st.download_button("📥 Download PDF Report", data=bytes(pdf_data), file_name=f"{ticker}_Report.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"AI Error: {e}")

with tab2:
    st.header("Historical Model Accuracy")
    st.write("This tab evaluates how well the Agent's technical triggers (RSI < 35) predicted a price increase over 5 days.")
    
    eval_ticker = st.text_input("Ticker to Evaluate", value="AAPL", key="eval_ticker")
    if st.button("Evaluate Confidence"):
        data = yf.Ticker(eval_ticker).history(period="1y")
        
        # Simple Backtest Logic: RSI Strategy
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        data['RSI'] = 100 - (100 / (1 + (gain / loss)))
        
        # Calculate 5-day forward return
        data['Forward_Return'] = data['Close'].shift(-5) / data['Close'] - 1
        data['Signal'] = np.where(data['RSI'] < 35, "BUY", "WAIT")
        
        buys = data[data['Signal'] == "BUY"].dropna()
        if not buys.empty:
            accuracy = (buys['Forward_Return'] > 0).mean() * 100
            st.metric("5-Day Accuracy Rate", f"{accuracy:.1f}%")
            st.write("#### Historical 'Buy' Signal Performance")
            st.dataframe(buys[['Close', 'RSI', 'Forward_Return']].tail(10))
        else:
            st.warning("No 'Buy' signals found in historical data for this ticker.")
