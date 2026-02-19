import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
import tempfile
from pathlib import Path
from groq import Groq
import json
import time

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v3.5")
st.markdown("**T2526.25 DRFA Moura – Official Weighted Evaluation**  \nMultiple files per schedule • Detailed Per-Criteria Breakdown")

# Official Criteria & Weightings from RFT Part 2
criteria_weighting = {
    "Price": 50,
    "Experience & Capability": 10,
    "Demonstrated Understanding & Resources": 15,
    "Quality, Environmental, Safety & Management": 15,
    "Local Content": 10
}

# All schedules from Part 6
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

mode = st.radio("Upload Mode", ["Simple Mode (One Main Document)", "Detailed Mode (Per Schedule)"], horizontal=True)

groq_key = st.text_input("Groq API Key", type="password")

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

def llm_deep_score(full_text, tender_name):
    if not groq_key:
        return 0, {}, "No API key"
    prompt = f"""You are an expert tender evaluator for Banana Shire Council.

Evaluate this tender against the official criteria and weightings:

- Price (50%)
- Experience & Capability (10%)
- Demonstrated Understanding & Resources (15%)
- Quality, Environmental, Safety & Management (15%)
- Local Content (10%)

Tender: {tender_name}
Text: {full_text[:14000]}

Return ONLY valid JSON:
{{
  "overall_score": 0-100,
  "criteria_scores": {{
    "Price": 0-100,
    "Experience & Capability": 0-100,
    "Demonstrated Understanding & Resources": 0-100,
    "Quality, Environmental, Safety & Management": 0-100,
    "Local Content": 0-100
  }},
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
        return data.get("overall_score", 0), data.get("criteria_scores", {}), data.get("explanation", "")
    except:
        return 0, {}, "LLM error"

# Add Tender
new_name = st.text_input("New Tender Name")
if st.button("Add Tender") and new_name.strip():
    if new_name not in st.session_state.tenders:
        st.session_state.tenders[new_name] = {sched: [] for sched in schedules}
        st.success(f"Added {new_name}")

# Upload Section
for tender in list(st.session_state.tenders.keys()):
    with st.expander(f"📂 {tender}", expanded=True):
        if mode == "Simple Mode (One Main Document)":
            file = st.file_uploader("Upload main document", key=f"simple_{tender}")
            st.session_state.tenders[tender]["Main Document"] = [file] if file else []
        else:
            for sched in schedules:
                files = st.file_uploader(f"{sched} (multiple files allowed)", 
                                       key=f"{tender}_{sched}", 
                                       accept_multiple_files=True)
                st.session_state.tenders[tender][sched] = files if files else []

# Evaluate
if st.button("🚀 Evaluate All Tenders", type="primary"):
    if not st.session_state.tenders:
        st.error("No tenders added")
    else:
        results = []
        progress = st.progress(0)
        
        for idx, (tender_name, schedules_dict) in enumerate(st.session_state.tenders.items()):
            full_text = ""
            for sched, file_list in schedules_dict.items():
                if file_list:
                    full_text += f"\n\n=== {sched} ===\n"
                    for file in file_list:
                        full_text += extract_text(file) + "\n"
            
            llm_score, criteria_scores, expl = llm_deep_score(full_text, tender_name)
            
            # Calculate Official Weighted Score
            weighted = sum((criteria_scores.get(crit, 0) / 100) * weight 
                          for crit, weight in criteria_weighting.items())
            
            row = {
                "Tender Name": tender_name,
                "Weighted Score": round(weighted, 1),
                "LLM Overall": llm_score,
                "Explanation": expl[:300] + "..." if len(expl) > 300 else expl,
                **criteria_scores  # Add all criteria scores as columns
            }
            results.append(row)
            progress.progress((idx + 1) / len(st.session_state.tenders))
        
        df = pd.DataFrame(results)
        ranked = df.sort_values("Weighted Score", ascending=False).reset_index(drop=True)
        ranked["Rank"] = ranked.index + 1
        
        st.subheader("🏆 Final Ranking (Official Weighting)")
        st.dataframe(ranked[["Rank", "Tender Name", "Weighted Score", "LLM Overall", "Explanation"]], 
                     use_container_width=True, height=600)
        
        # Detailed Per-Criteria Breakdown
        st.subheader("📊 Detailed Per-Criteria Breakdown")
        selected = st.multiselect("Select tenders to compare", df["Tender Name"].tolist(), default=df["Tender Name"].tolist()[:4])
        if selected:
            compare_df = df[df["Tender Name"].isin(selected)]
            breakdown_cols = ["Tender Name"] + list(criteria_weighting.keys())
            breakdown = compare_df[breakdown_cols].set_index("Tender Name")
            st.dataframe(breakdown.style.format("{:.1f}"), use_container_width=True)
            
            # Weighted Contribution
            st.subheader("Weighted Contribution (%)")
            contrib = {}
            for crit, weight in criteria_weighting.items():
                contrib[crit] = compare_df[crit] * (weight / 100)
            contrib_df = pd.DataFrame(contrib, index=compare_df["Tender Name"])
            st.dataframe(contrib_df.style.format("{:.1f}"), use_container_width=True)
        
        st.download_button("📥 Download Full Results CSV", df.to_csv(index=False), "evaluation_results.csv", "text/csv")
        
        st.success("✅ Evaluation complete with official weighting and detailed breakdown")
