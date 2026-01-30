import streamlit as st
import yfinance as yf
from google import genai
import plotly.graph_objects as go
import pandas as pd
from fpdf import FPDF
import requests

# --- 1. SETUP & AUTHENTICATION ---
st.set_page_config(page_title="AI Stock Agent 2026", layout="wide", page_icon="📈")

# Initializing client once at the top to prevent session errors
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
    """Resolves company name to ticker and finds the domain for the logo."""
    try:
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(search_url, headers=headers).json()
        ticker = response['quotes'][0]['symbol']
        
        stock_info = yf.Ticker(ticker).info
        # Extract domain for logo fetching
        website = stock_info.get('website', '').replace('http://', '').replace('https://', '').split('/')[0]
        name = stock_info.get('longName', ticker)
        return ticker, name, website
    except:
        return None, None, None

def generate_pdf(ticker, name, analysis):
    """Generates a professional PDF report and fixes encoding errors."""
    # 1. CLEAN THE TEXT
    # AI often uses Unicode dashes and curly quotes which crash standard PDF fonts
    clean_analysis = analysis.replace('–', '-').replace('—', '-').replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    
    pdf = FPDF()
    pdf.add_page()
    
    # Header
    pdf.set_font("Arial", "B", 18)
    pdf.cell(0, 15, f"AI Research Report: {name} ({ticker})", ln=True, align="C")
    pdf.ln(10)
    
    # Body Text
    pdf.set_font("Arial", size=11)
    # Using 'latin-1' encoding to ensure standard characters map correctly
    pdf.multi_cell(0, 8, clean_analysis.encode('latin-1', 'replace').decode('latin-1'))
    
    return pdf.output()

# --- 3. DASHBOARD UI ---
st.title("🤖 Autonomous AI Stock Intelligence")
st.markdown("---")

# Sidebar
st.sidebar.header("Search & Parameters")
user_query = st.sidebar.text_input("Enter Company or Ticker", value="Google")
time_period = st.sidebar.selectbox("Analysis Window", ["1mo", "3mo", "6mo", "1y"])

if st.sidebar.button("Run Comprehensive Analysis"):
    ticker, comp_name, domain = get_ticker_and_logo(user_query)
    
    if not ticker:
        st.error("Could not find a matching company. Please try the exact Ticker symbol.")
    else:
        # Header with Logo
        h_col1, h_col2 = st.columns([1, 6])
        with h_col1:
            if domain:
                st.image(f"https://logo.clearbit.com/{domain}", width=80)
        with h_col2:
            st.subheader(f"{comp_name} ({ticker})")
            st.caption(f"Strategy Period: {time_period}")

        # Data Acquisition
        with st.spinner("Analyzing market data..."):
            hist = yf.Ticker(ticker).history(period=time_period)
            
        if hist.empty:
            st.warning("No price data available.")
        else:
            # Layout: Chart and AI Logic
            col_chart, col_ai = st.columns([2, 1])
            
            with col_chart:
                fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], 
                                     high=hist['High'], low=hist['Low'], close=hist['Close'])])
                fig.update_layout(title="Technical Price Action", template="plotly_dark")
                st.plotly_chart(fig, use_container_width=True)

            with col_ai:
                st.write("### 🧠 AI Analysis")
                data_summary = hist.tail(5).to_string()
                
                # FIXED AI CALL: Wrapping contents in a list for 2026 SDK stability
                prompt = f"Analyze {comp_name} ({ticker}). Latest data:\n{data_summary}\nProvide a BUY/SELL/HOLD signal with 3 reasons."
                
                try:
                    response = client.models.generate_content(
                        model="gemini-3-flash-preview", # Using the latest 2026 model
                        contents=[prompt]
                    )
                    analysis_text = response.text
                    st.info(analysis_text)
                    
                    # 4. DOWNLOAD BUTTON (Visible only after successful analysis)
                    st.markdown("---")
                    pdf_data = generate_pdf(ticker, comp_name, analysis_text)
                    st.download_button(
                        label="📥 Download Research PDF",
                        data=bytes(pdf_data),
                        file_name=f"{ticker}_Report.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                except Exception as e:
                    st.error(f"AI Endpoint Error: {e}")
