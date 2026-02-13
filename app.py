import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from fpdf import FPDF
import requests

# --- 1. SESSION & AUTHENTICATION SETUP ---
st.set_page_config(page_title="AI Stock Agent INR", layout="wide", page_icon="📈")

# Initialize persistent requests session to fix "Invalid Crumb/401" errors
if 'http_session' not in st.session_state:
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    st.session_state.http_session = session

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
    """Fetch live USD to INR rate using the persistent session."""
    try:
        data = yf.Ticker("USDINR=X", session=st.session_state.http_session).history(period="1d")
        return data['Close'].iloc[-1]
    except:
        return 83.5  # Realistic fallback rate

def get_ticker_and_logo(query):
    """Resolves name to ticker with session headers and fallback logic."""
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        response = st.session_state.http_session.get(search_url).json()
        
        if response.get('quotes'):
            ticker = response['quotes'][0]['symbol']
        else:
            ticker = query.upper().strip() # Fallback to direct input
            
        stock = yf.Ticker(ticker, session=st.session_state.http_session)
        info = stock.info
        
        if 'symbol' not in info and 'shortName' not in info:
            return None, None, None
            
        website = info.get('website', '').replace('https://', '').replace('http://', '').split('/')[0]
        name = info.get('longName', ticker)
        return ticker, name, website
    except:
        return None, None, None

def generate_pdf(ticker, name, analysis):
    """Generates PDF with character normalization for Latin-1 compatibility."""
    # Mapping UTF-8 AI characters to ASCII for FPDF
    clean_text = (analysis.replace('–', '-').replace('—', '-')
                          .replace('’', "'").replace('‘', "'")
                          .replace('“', '"').replace('”', '"')
                          .replace('•', '*'))
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Equity Research Report: {name} ({ticker})", ln=True, align='C')
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, "Valuations in Indian Rupee (INR)", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", size=11)
    # latin-1 encoding with 'replace' to ensure no crashes on emojis
    pdf.multi_cell(0, 8, clean_text.encode('latin-1', 'replace').decode('latin-1'))
    return pdf.output()

# --- 3. UI TABS & DASHBOARD ---
tab1, tab2 = st.tabs(["🚀 Strategic Analysis", "📊 Accuracy Audit"])

with tab1:
    st.title("Autonomous AI Stock Agent (INR ₹)")
    
    with st.sidebar:
        st.header("Research Configuration")
        user_query = st.text_input("Enter Company (e.g., Apple) or Ticker (e.g., RELIANCE.NS)").strip()
        time_period = st.selectbox("Historical Window", ["1mo", "3mo", "6mo", "1y", "2y"])
        
        if st.button("Generate Live Report"):
            if not user_query:
                st.warning("Please enter a name or ticker.")
            else:
                with st.spinner("Analyzing Market Cycles..."):
                    ticker, name, domain = get_ticker_and_logo(user_query)
                    
                    if ticker:
                        # Fetch and Localize Data
                        ticker_obj = yf.Ticker(ticker, session=st.session_state.http_session)
                        hist = ticker_obj.history(period=time_period)
                        rate = get_exchange_rate()
                        
                        # Apply Currency Transformation
                        for col in ['Open', 'High', 'Low', 'Close']:
                            hist[col] = hist[col] * rate
                        
                        # Save to Session State for Persistence
                        st.session_state.stock_data = hist
                        st.session_state.conversion_rate = rate
                        st.session_state.comp_info = {'ticker': ticker, 'name': name, 'domain': domain}
                        
                        # AI Synthesis
                        data_summary = hist.tail(10).to_string()
                        prompt = f"""You are a SEBI-certified analyst. Analyze {name} ({ticker}) prices in INR (₹). 
                        Conversion Rate: {rate}.
                        Last 10 Days Data:
                        {data_summary}
                        Provide:
                        1. Technical Sentiment (Bullish/Bearish)
                        2. Support & Resistance in INR
                        3. Strategic Signal (BUY/SELL/HOLD)"""
                        
                        try:
                            response = st.session_state.client.models.generate_content(
                                model="gemini-2.0-flash", 
                                contents=[prompt]
                            )
                            st.session_state.analysis_text = response.text
                        except Exception as e:
                            st.error(f"AI Reasoning Error: {e}")
                    else:
                        st.error("Invalid Ticker. Check spelling or try adding '.NS' for Indian stocks.")

    # DISPLAY ENGINE
    if st.session_state.stock_data is not None:
        info = st.session_state.comp_info
        hist = st.session_state.stock_data
        
        # Identity Header
        col_img, col_txt = st.columns([1, 10])
        with col_img:
            if info['domain']: st.image(f"https://logo.clearbit.com/{info['domain']}", width=60)
        with col_txt:
            st.subheader(f"{info['name']} | Ticker: {info['ticker']}")
        
        # Real-time Metrics
        curr_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2]
        st.metric("Current Market Price (INR)", f"₹{curr_price:,.2f}", delta=f"{curr_price - prev_price:,.2f}")

        # Candlestick Visualization
        fig = go.Figure(data=[go.Candlestick(
            x=hist.index, open=hist['Open'], high=hist['High'], 
            low=hist['Low'], close=hist['Close'], name="INR Price"
        )])
        fig.update_layout(template="plotly_dark", height=500, yaxis_title="Price in ₹ (INR)")
        st.plotly_chart(fig, use_container_width=True)

        # AI Reasoning Output
        if st.session_state.analysis_text:
            st.markdown("---")
            st.write("### 🧠 Agentic Strategic Reasoning")
            st.info(st.session_state.analysis_text)
            
            # PDF Download
            pdf_bytes = generate_pdf(info['ticker'], info['name'], st.session_state.analysis_text)
            st.download_button("📥 Download Research PDF", data=bytes(pdf_bytes), 
                             file_name=f"{info['ticker']}_Research.pdf", mime="application/pdf")

with tab2:
    st.header("Quantitative Strategy Audit")
    eval_ticker = st.text_input("Enter Ticker for Backtest", value=st.session_state.comp_info.get('ticker', 'AAPL'))
    
    if st.button("Evaluate RSI Strategy"):
        with st.spinner("Crunching historical returns..."):
            audit_data = yf.Ticker(eval_ticker, session=st.session_state.http_session).history(period="1y")
            if not audit_data.empty:
                # RSI Logic
                delta = audit_data['Close'].diff()
                up = delta.clip(lower=0)
                down = -1 * delta.clip(upper=0)
                ema_up = up.ewm(com=13, adjust=False).mean()
                ema_down = down.ewm(com=13, adjust=False).mean()
                rs = ema_up / ema_down
                audit_data['RSI'] = 100 - (100 / (1 + rs))
                
                # Signal Accuracy (5-Day Forward)
                audit_data['Signal'] = np.where(audit_data['RSI'] < 35, 'BUY', 'WAIT')
                audit_data['Future_Price'] = audit_data['Close'].shift(-5)
                audit_data['Result'] = (audit_data['Future_Price'] > audit_data['Close']).astype(int)
                
                hits = audit_data[audit_data['Signal'] == 'BUY'].dropna()
                if not hits.empty:
                    accuracy = hits['Result'].mean() * 100
                    st.metric("Historical Strategy Accuracy", f"{accuracy:.1f}%")
                    st.write("Recent 'Oversold' Buy Signals:")
                    st.dataframe(hits[['Close', 'RSI', 'Result']].tail(5))
                else:
                    st.warning("No 'Oversold' (RSI < 35) signals detected in the last 12 months.")
