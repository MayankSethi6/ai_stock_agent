import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from fpdf import FPDF
import requests

# --- 1. INITIALIZATION ---
st.set_page_config(page_title="AI Stock Agent INR", layout="wide", page_icon="📈")

# Initialize Gemini Client
if 'client' not in st.session_state:
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.session_state.client = genai.Client(api_key=api_key)
    except Exception:
        st.error("Missing GOOGLE_API_KEY. Please add it to Streamlit Secrets.")
        st.stop()

# Initialize Persistence States
if 'stock_data' not in st.session_state: st.session_state.stock_data = None
if 'analysis_text' not in st.session_state: st.session_state.analysis_text = None
if 'comp_info' not in st.session_state: st.session_state.comp_info = {}
if 'conversion_rate' not in st.session_state: st.session_state.conversion_rate = 1.0

# --- 2. CORE UTILITY FUNCTIONS ---

def get_exchange_rate():
    """Fetch live USD to INR rate without manual session."""
    try:
        data = yf.Ticker("USDINR=X").history(period="1d")
        return data['Close'].iloc[-1]
    except:
        return 83.5  # Realistic fallback rate

def get_ticker_and_logo(query):
    """Resolves name to ticker using yfinance internal handling."""
    try:
        # Step 1: Search for ticker using Yahoo's query endpoint
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers).json()
        
        if response.get('quotes'):
            ticker_symbol = response['quotes'][0]['symbol']
        else:
            ticker_symbol = query.upper().strip() 
            
        # Step 2: Validate and get metadata via yf
        stock = yf.Ticker(ticker_symbol)
        info = stock.info
        
        if 'symbol' not in info and 'shortName' not in info:
            return None, None, None
            
        website = info.get('website', '').replace('https://', '').replace('http://', '').split('/')[0]
        name = info.get('longName', ticker_symbol)
        return ticker_symbol, name, website
    except:
        return None, None, None

def generate_pdf(ticker, name, analysis):
    """Generates PDF with character normalization for Latin-1 compatibility."""
    # Mapping UTF-8 AI characters to ASCII for FPDF
    clean_text = (analysis.replace('–', '-').replace('—', '-')
                          .replace('’', "'").replace('‘', "'")
                          .replace('“', '"').replace('”', '"')
                          .replace('•', '*').replace('₹', 'Rs.'))
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Equity Research Report: {name} ({ticker})", ln=True, align='C')
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Valuations in Indian Rupee (INR)", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=11)
    pdf.multi_cell(0, 8, clean_text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output()

# --- 3. DASHBOARD UI ---
tab1, tab2 = st.tabs(["🚀 Strategic Analysis", "📊 Accuracy Audit"])

with tab1:
    st.title("Autonomous AI Stock Agent (INR ₹)")
    
    with st.sidebar:
        st.header("Research Configuration")
        user_query = st.text_input("Enter Company or Ticker (e.g. RELIANCE.NS)").strip()
        time_period = st.selectbox("Historical Window", ["1mo", "3mo", "6mo", "1y", "2y"])
        
        if st.button("Generate Live Report"):
            if not user_query:
                st.warning("Please enter a name or ticker.")
            else:
                with st.spinner("Accessing Market Data..."):
                    ticker, name, domain = get_ticker_and_logo(user_query)
                    
                    if ticker:
                        # Fetch Data using yfinance's internal automation
                        ticker_obj = yf.Ticker(ticker)
                        hist = ticker_obj.history(period=time_period)
                        rate = get_exchange_rate()
                        
                        # Apply Currency Transformation
                        for col in ['Open', 'High', 'Low', 'Close']:
                            hist[col] = hist[col] * rate
                        
                        # Save to Session State
                        st.session_state.stock_data = hist
                        st.session_state.conversion_rate = rate
                        st.session_state.comp_info = {'ticker': ticker, 'name': name, 'domain': domain}
                        
                        # AI Synthesis
                        data_summary = hist.tail(10).to_string()
                        prompt = f"Analyze {name} ({ticker}) in INR (Rate: {rate}). Data:\n{data_summary}\nProvide BUY/SELL/HOLD signal."
                        
                        try:
                            response = st.session_state.client.models.generate_content(
                                model="gemini-3-flash-preview", 
                                contents=[prompt]
                            )
                            st.session_state.analysis_text = response.text
                        except Exception as e:
                            st.error(f"AI Reasoning Error: {e}")
                    else:
                        st.error("Ticker not found.")

    # DISPLAY ENGINE
    if st.session_state.stock_data is not None:
        info = st.session_state.comp_info
        hist = st.session_state.stock_data
        
        # Header
        col_img, col_txt = st.columns([1, 10])
        with col_img:
            if info['domain']: st.image(f"https://logo.clearbit.com/{info['domain']}", width=60)
        with col_txt:
            st.subheader(f"{info['name']} | {info['ticker']}")
        
        # Metric and Chart
        curr_price = hist['Close'].iloc[-1]
        st.metric("Latest Price (INR)", f"₹{curr_price:,.2f}")

        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], 
            low=hist['Low'], close=hist['Close']
        )])
        fig.update_layout(template="plotly_dark", yaxis_title="Price (₹)")
        st.plotly_chart(fig, use_container_width=True)

        if st.session_state.analysis_text:
            st.info(st.session_state.analysis_text)
            pdf_bytes = generate_pdf(info['ticker'], info['name'], st.session_state.analysis_text)
            st.download_button("📥 Download Report", data=bytes(pdf_bytes), file_name=f"{info['ticker']}_Report.pdf")

with tab2:
    st.header("Quant Strategy Audit")
    eval_ticker = st.text_input("Backtest Ticker", value=st.session_state.comp_info.get('ticker', 'AAPL'))
    if st.button("Run Audit"):
        audit_data = yf.Ticker(eval_ticker).history(period="1y")
        if not audit_data.empty:
            # Simple RSI for evaluation
            delta = audit_data['Close'].diff()
            up = delta.clip(lower=0).rolling(14).mean()
            down = -1 * delta.clip(upper=0).rolling(14).mean()
            audit_data['RSI'] = 100 - (100 / (1 + (up/down)))
            
            audit_data['Signal'] = np.where(audit_data['RSI'] < 35, 'BUY', 'WAIT')
            audit_data['Result'] = (audit_data['Close'].shift(-5) > audit_data['Close']).astype(int)
            hits = audit_data[audit_data['Signal'] == 'BUY'].dropna()
            
            if not hits.empty:
                st.metric("Accuracy Rate", f"{(hits['Result'].mean()*100):.1f}%")
                st.dataframe(hits[['Close', 'RSI', 'Result']].tail(5))
