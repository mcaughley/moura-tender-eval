import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

st.set_page_config(page_title="Moura T25/26.25 Tender Evaluator", layout="wide")

# ==================== PASSWORD ====================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🍃 Banana Shire Council – Moura Area Tender Evaluation")
    pw = st.text_input("Enter password", type="password")
    if st.button("Login"):
        if pw == "banana2026":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    st.stop()

# ==================== DATA ====================
if "tenderers" not in st.session_state:
    st.session_state.tenderers = pd.DataFrame(columns=[
        'Tenderer', 'ABN', 'Total Price Exc GST', 'Price Score',
        'Experience Score', 'Understanding Score', 'Management Score',
        'Local Content Score', 'Total Weighted Score', 'Notes', 'Last Updated'
    ])

df = st.session_state.tenderers
COUNCIL_ESTIMATE = 3247850  # Pre-loaded from your tender list Excel

# ==================== TABS ====================
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard & Ranking", "➕ Add/Edit Tenderer", "📤 Upload K1 Excel", "✅ Compliance Checklist"])

with tab1:
    st.header("Current Ranking")
    if len(df) == 0:
        st.info("No tenderers added yet")
    else:
        # Auto price scoring
        if df['Total Price Exc GST'].sum() > 0:
            min_price = df['Total Price Exc GST'].min()
            df['Price Score'] = df['Total Price Exc GST'].apply(lambda x: round(50 * (min_price / x), 1) if x > 0 else 0)
        
        df['Total Weighted Score'] = (
            df['Price Score'] * 0.50 +
            df['Experience Score'] * 0.10 +
            df['Understanding Score'] * 0.15 +
            df['Management Score'] * 0.15 +
            df['Local Content Score'] * 0.10
        )
        
        ranked = df.sort_values('Total Weighted Score', ascending=False).reset_index(drop=True)
        ranked.index = ranked.index + 1
        
        ranked['% of Council Estimate'] = (ranked['Total Price Exc GST'] / COUNCIL_ESTIMATE * 100).round(1)
        
        st.dataframe(ranked.style.format({
            'Total Price Exc GST': '${:,.0f}',
            'Total Weighted Score': '{:.1f}',
            '% of Council Estimate': '{:.1f}%'
        }).background_gradient(subset=['Total Weighted Score'], cmap='RdYlGn'), use_container_width=True)

        # PDF Report
        def create_pdf():
            buffer = io.BytesIO()
            c = canvas.Canvas(buffer, pagesize=A4)
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, 800, "Moura Area Tender Evaluation Report - T25/26.25")
            c.setFont("Helvetica", 12)
            c.drawString(50, 780, f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')}")
            c.drawString(50, 760, f"Council Estimate: ${COUNCIL_ESTIMATE:,.0f}")
            
            y = 720
            for i, row in ranked.iterrows():
                c.drawString(50, y, f"{i}. {row['Tenderer']} - ${row['Total Price Exc GST']:,.0f} ({row['% of Council Estimate']}% of estimate) - Score: {row['Total Weighted Score']:.1f}")
                y -= 22
            c.save()
            buffer.seek(0)
            return buffer.getvalue()
        
        st.download_button("📄 Download PDF Report", create_pdf(), "Moura_Tender_Report.pdf", "application/pdf")

with tab2:
    st.header("Add or Edit Tenderer")
    with st.form("add_form"):
        name = st.text_input("Tenderer Name *")
        abn = st.text_input("ABN")
        price = st.number_input("Total Price Exc GST ($)", min_value=0.0, step=1000.0, format="%.0f")
        col1, col2, col3, col4 = st.columns(4)
        with col1: exp = st.slider("Experience (0-100)", 0, 100, 70)
        with col2: und = st.slider("Understanding & Resources", 0, 100, 70)
        with col3: man = st.slider("QES Management", 0, 100, 70)
        with col4: loc = st.slider("Local Content", 0, 100, 80)
        notes = st.text_area("Notes")
        if st.form_submit_button("Save Tenderer"):
            if name:
                new_row = pd.DataFrame([{
                    'Tenderer': name, 'ABN': abn, 'Total Price Exc GST': price,
                    'Experience Score': exp, 'Understanding Score': und,
                    'Management Score': man, 'Local Content Score': loc,
                    'Notes': notes, 'Last Updated': datetime.now().strftime("%Y-%m-%d %H:%M")
                }])
                st.session_state.tenderers = pd.concat([df, new_row], ignore_index=True)
                st.success(f"✅ {name} saved")
                st.rerun()

with tab3:
    st.header("Upload Schedule K1 Excel")
    tenderer_sel = st.selectbox("Select Tenderer", df['Tenderer'].tolist() if len(df) > 0 else ["New"])
    uploaded = st.file_uploader("Upload K1 Excel", type=["xlsx"])
    if uploaded and st.button("Parse Price"):
        try:
            xls = pd.ExcelFile(uploaded)
            summary = pd.read_excel(xls, 'Summary', header=None)
            total = None
            for _, row in summary.iterrows():
                if isinstance(row[0], str) and "Total Excluding GST" in str(row[0]):
                    total = float(row[4])
                    break
            if total:
                st.success(f"✅ Parsed: **${total:,.0f}**")
                if tenderer_sel != "New":
                    idx = df[df['Tenderer'] == tenderer_sel].index[0]
                    df.at[idx, 'Total Price Exc GST'] = total
                    st.session_state.tenderers = df
                    st.rerun()
        except:
            st.error("Could not parse file")

with tab4:
    st.header("Part 6 Compliance Checklist")
    items = ["Tender Form signed", "Schedule A1 Details", "Schedule A3 Conflict of Interest", "Schedule B1 Financials",
             "Schedule C Insurances", "Schedule D Local Content", "Schedule E Experience", "Schedule F1 Key Personnel",
             "Schedule G Resources", "Schedule H1 WHS", "Schedule H2 Environmental", "Schedule H3 Quality",
             "Schedule I Methodology", "Schedule J Program", "Schedule K1 Pricing", "Schedule K3 Variation Rates",
             "Schedule L Departures"]
    for item in items:
        st.checkbox(item, key=item)

st.sidebar.success("✅ App ready — add all your tenders now!")
st.sidebar.caption("Password: banana2026\nCouncil Estimate: $3,247,850")
