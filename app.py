import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from fpdf import FPDF
import requests

# --- 1. SETUP & AUTHENTICATION ---
st.set_page_config(page_title="AI Stock Agent INR", layout="wide", page_icon="📈")

# Initialize Gemini Client
if 'client' not in st.session_state:
    try:
        api_key = st.secrets["GOOGLE_API_KEY"]
        st.session_state.client = genai.Client(api_key=api_key)
    except Exception:
        st.error("Missing GOOGLE_API_KEY. Please add it to Streamlit Secrets.")
        st.stop()

# Initialize Session State
if 'stock_data' not in st.session_state:
    st.session_state.stock_data = None
if 'analysis_text' not in st.session_state:
    st.session_state.analysis_text = None
if 'comp_info' not in st.session_state:
    st.session_state.comp_info = {}
if 'conversion_rate' not in st.session_state:
    st.session_state.conversion_rate = 1.0

client = st.session_state.client

# --- 2. HELPER FUNCTIONS ---

def get_exchange_rate():
    """Fetch live USD to INR rate."""
    try:
        data = yf.Ticker("USDINR=X").history(period="1d")
        return data['Close'].iloc[-1]
    except:
        return 83.0  # Fallback approximate rate

def get_ticker_and_logo(query):
    """Resolves name to ticker with fallback logic."""
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers).json()
        
        if response.get('quotes'):
            ticker = response['quotes'][0]['symbol']
        else:
            ticker = query.upper().strip() # Fallback to direct ticker input
            
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Validation
        if 'symbol' not in info and 'shortName' not in info:
            return None, None, None
            
        website = info.get('website', '').replace('https://', '').replace('http://', '').split('/')[0]
        name = info.get('longName', ticker)
        return ticker, name, website
    except:
        return None, None, None

def generate_pdf(ticker, name, analysis):
    """Generates PDF with INR currency and sanitized characters."""
    # Character Sanitization
    clean_text = analysis.replace('–', '-').replace('—', '-').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"AI Research Report: {name} ({ticker})", ln=True, align='C')
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Values converted to Indian Rupee (INR)", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=11)
    # Using 'replace' to avoid crashing on unknown symbols
    pdf.multi_cell(0, 8, clean_text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output()

# --- 3. DASHBOARD UI ---
tab1, tab2 = st.tabs(["🚀 Live Analysis", "📊 Accuracy Validation"])

with tab1:
    st.title("AI Stock Intelligence (INR ₹)")
    
    with st.sidebar:
        st.header("Search Parameters")
        user_query = st.text_input("Enter Company or Ticker", value="NVIDIA").strip()
        time_period = st.selectbox("Historical Window", ["1mo", "3mo", "6mo", "1y"])
        
        if st.button("Generate Report"):
            with st.spinner("Fetching market data and converting currency..."):
                ticker, name, domain = get_ticker_and_logo(user_query)
                
                if ticker:
                    # 1. Fetch Data & Rate
                    hist = yf.Ticker(ticker).history(period=time_period)
                    rate = get_exchange_rate()
                    
                    # 2. Convert Data to INR
                    for col in ['Open', 'High', 'Low', 'Close']:
                        hist[col] = hist[col] * rate
                    
                    # 3. Store in State
                    st.session_state.stock_data = hist
                    st.session_state.conversion_rate = rate
                    st.session_state.comp_info = {'ticker': ticker, 'name': name, 'domain': domain}
                    
                    # 4. AI Reasoning
                    data_summary = hist.tail(5).to_string()
                    prompt = f"Analyze {name} ({ticker}) based on these prices in INR (₹). Rate used: {rate}.\nData:\n{data_summary}\nProvide a BUY/SELL/HOLD signal with technical reasoning."
                    
                    try:
                        response = client.models.generate_content(model="gemini-2.0-flash", contents=[prompt])
                        st.session_state.analysis_text = response.text
                    except Exception as e:
                        st.error(f"AI Logic Error: {e}")
                else:
                    st.error("Ticker not found. Try a specific symbol (e.g., AAPL or RELIANCE.NS)")

    # DISPLAY SECTION
    if st.session_state.stock_data is not None:
        info = st.session_state.comp_info
        hist = st.session_state.stock_data
        
        # Header with Logo
        col_l, col_t = st.columns([1, 8])
        if info['domain']:
            with col_l: st.image(f"https://logo.clearbit.com/{info['domain']}", width=60)
        with col_t: st.subheader(f"{info['name']} ({info['ticker']})")
        
        # Price Metric
        curr_price = hist['Close'].iloc[-1]
        st.metric("Latest Price (INR)", f"₹{curr_price:,.2f}", delta=f"{hist['Close'].diff().iloc[-1]:,.2f}")

        # Plotly Chart
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], 
            low=hist['Low'], close=hist['Close'], name="Price (₹)"
        )])
        fig.update_layout(template="plotly_dark", height=500, yaxis_title="Price in INR (₹)")
        st.plotly_chart(fig, use_container_width=True)

        # AI Analysis
        if st.session_state.analysis_text:
            st.markdown("---")
            st.write("### 🧠 AI Strategic Insights")
            st.info(st.session_state.analysis_text)
            
            # PDF Generation
            pdf_data = generate_pdf(info['ticker'], info['name'], st.session_state.analysis_text)
            st.download_button("📥 Download INR Report (PDF)", data=bytes(pdf_data), file_name=f"{info['ticker']}_INR_Report.pdf")

with tab2:
    st.header("Strategy Backtest (INR Context)")
    st.write("Evaluating the RSI-35 strategy's success rate over the last year.")
    
    eval_ticker = st.text_input("Ticker to Evaluate", value=st.session_state.comp_info.get('ticker', 'AAPL'))
    
    if st.button("Run Accuracy Check"):
        data = yf.Ticker(eval_ticker).history(period="1y")
        if not data.empty:
            # RSI Calculation
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            data['RSI'] = 100 - (100 / (1 + (gain / loss)))
            
            # Accuracy Metric
            data['Next_5D'] = data['Close'].shift(-5)
            data['Signal'] = np.where(data['RSI'] < 35, "BUY", "WAIT")
            buys = data[data['Signal'] == "BUY"].dropna()
            
            if not buys.empty:
                success_rate = (buys['Next_5D'] > buys['Close']).mean() * 100
                st.metric("Model Prediction Confidence", f"{success_rate:.1f}%")
                st.dataframe(buys[['Close', 'RSI', 'Next_5D']].tail(10))
            else:
                st.warning("No 'Buy' triggers found in history for this ticker.")
