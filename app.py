import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
import tempfile
from pathlib import Path
from groq import Groq
import json
import time

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v3.1")
st.markdown("**T2526.25 DRFA Moura – Part 6 Response Schedules**")

# Exact Schedule Titles from Criteria
schedules = [
    "Tender Form",
    "Schedule A – Respondent’s Details, Conflict of Interest and Legal Matters",
    "Schedule A1 – Respondent’s Details",
    "Schedule A2 – Respondent’s Further Details",
    "Schedule A3 – Conflict of Interest",
    "Schedule A4 – Legal MattersPrivacy and Data Management",
    "Schedule B – Solvency and Financial Details",
    "Schedule B1 – Solvency of Respondent",
    "Schedule B2 – Financial Details of Respondent",
    "Schedule C – Insurances",
    "Schedule C1 - Insurances",
    "Schedule C2 – Additional Insurances",
    "Schedule D – Business Profile (Local Content, Employment and Environmental)",
    "Schedule D1 – Local Content",
    "Schedule D2 – Employment",
    "Schedule D3 – Environmental",
    "Schedule E – Experience and Capability of Respondent",
    "Schedule E1 – Similar Engagements Currently Underway",
    "Schedule E2 – Past Similar Engagements",
    "Schedule E3 – Resources",
    "Schedule F – Experience and Capability of Respondent’s Key Personnel, Subcontractors, Suppliers and Consultants",
    "Schedule G – Management Systems",
    "Schedule H – Methodology",
    "Schedule I – Program",
    "Schedule J – Pricing, Cash Flow and Variation Rates",
    "Schedule K – Technical Data",
    "Schedule L – Statement of Departures",
    "Schedule M – Additional Information",
    "Schedule N – Australian Government Work Health and Safety Accreditation Scheme",
    "Schedule O – Queensland Code of Practice for the Building and Construction Industry"
]

if 'tenders' not in st.session_state:
    st.session_state.tenders = {}

mode = st.radio("Upload Mode", ["Simple Mode (One Document per Tender)", "Detailed Mode (One File per Schedule)"], horizontal=True)

groq_key = st.text_input("Groq API Key (for LLM scoring)", type="password")

def extract_text(file):
    text = ""
    try:
        if file.name.endswith(".pdf"):
            reader = PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() or ""
        elif file.name.endswith((".xlsx", ".xls")):
            df = pd.read_excel(file)
            text = df.to_string()
        elif file.name.endswith((".docx", ".doc")):
            from docx import Document
            doc = Document(file)
            text = "\n".join([p.text for p in doc.paragraphs])
        else:
            text = file.read().decode("utf-8", errors="ignore")
    except:
        pass
    return text

def llm_deep_score(text, tender_name):
    if not groq_key:
        return 0, {}, "No API key"
    # Robust prompt
    prompt = f"""Evaluate this tender response against the Banana Shire Council Part 6 checklist.

Tender: {tender_name}
Text: {text[:14000]}

Return ONLY valid JSON:
{{
  "overall_score": 0-100,
  "explanation": "brief summary"
}}"""
    try:
        client = Groq(api_key=groq_key)
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        data = json.loads(chat.choices[0].message.content)
        return data.get("overall_score", 0), {}, data.get("explanation", "")
    except:
        return 0, {}, "LLM error"

# Add Tender
new_name = st.text_input("Tender Name")
if st.button("Add Tender") and new_name:
    if new_name not in st.session_state.tenders:
        st.session_state.tenders[new_name] = {}
        st.success(f"Added {new_name}")

# Upload Section
for tender in list(st.session_state.tenders.keys()):
    with st.expander(f"📂 {tender}", expanded=True):
        if mode == "Simple Mode (One Document per Tender)":
            file = st.file_uploader("Upload main document for this tender", key=f"simple_{tender}")
            st.session_state.tenders[tender] = {"Main Document": file}
        else:
            for sched in schedules:
                file = st.file_uploader(f"{sched}", key=f"{tender}_{sched}")
                st.session_state.tenders[tender][sched] = file

# Evaluate
if st.button("🚀 Evaluate All Tenders", type="primary"):
    results = []
    for tender, files in st.session_state.tenders.items():
        full_text = ""
        for name, file in files.items():
            if file:
                full_text += f"\n\n=== {name} ===\n" + extract_text(file) + "\n"
        
        score, item_scores, expl = llm_deep_score(full_text, tender)
        
        row = {"Tender Name": tender, "Overall Score": score, "Explanation": expl}
        results.append(row)
    
    df = pd.DataFrame(results)
    ranked = df.sort_values("Overall Score", ascending=False).reset_index(drop=True)
    ranked["Rank"] = ranked.index + 1
    
    st.subheader("🏆 Final Ranking")
    st.dataframe(ranked[["Rank", "Tender Name", "Overall Score", "Explanation"]], use_container_width=True)
    
    st.download_button("📥 Download Results CSV", df.to_csv(index=False), "evaluation_results.csv", "text/csv")
