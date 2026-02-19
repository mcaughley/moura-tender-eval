import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
import tempfile
from pathlib import Path
from groq import Groq
import json
import time
import zipfile
import io
import os

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v3.9")
st.markdown("**T2526.25 DRFA Moura – Official Weighted Evaluation**  \nUnlimited files • Delete Tenders • Save / Load Full Session")

# Official Weightings from RFT
criteria_weighting = {
    "Price": 50,
    "Experience & Capability": 10,
    "Demonstrated Understanding & Resources": 15,
    "Quality, Environmental, Safety & Management": 15,
    "Local Content": 10
}

# Exact Schedules from Part 6
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

mode = st.radio("Upload Mode", ["Simple Mode (unlimited documents)", "Detailed Mode (per schedule)"], horizontal=True)

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
    prompt = f"""Evaluate this tender against the official criteria:

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

# Upload & Delete Section
for tender in list(st.session_state.tenders.keys()):
    with st.expander(f"📂 {tender}", expanded=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            if mode == "Simple Mode (unlimited documents)":
                files = st.file_uploader("Upload documents (unlimited)", 
                                       key=f"simple_{tender}", 
                                       accept_multiple_files=True)
                st.session_state.tenders[tender]["Main Documents"] = files if files else []
            else:
                for sched in schedules:
                    files = st.file_uploader(f"{sched} (multiple allowed)", 
                                           key=f"{tender}_{sched}", 
                                           accept_multiple_files=True)
                    st.session_state.tenders[tender][sched] = files if files else []
        with col2:
            if st.button("🗑️ Delete", key=f"del_{tender}"):
                if st.session_state.tenders.pop(tender, None):
                    st.success(f"Deleted {tender}")
                    st.rerun()

# Save / Load Session
st.subheader("💾 Session Management")
col_save, col_load = st.columns(2)

with col_save:
    if st.button("💾 Save Current Session"):
        if not st.session_state.tenders:
            st.warning("Nothing to save")
        else:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                manifest = {"tenders": {}}
                
                for tender_name, data in st.session_state.tenders.items():
                    manifest["tenders"][tender_name] = {}
                    tender_path = tmp_path / tender_name
                    tender_path.mkdir()
                    
                    for sched, file_list in data.items():
                        manifest["tenders"][tender_name][sched] = []
                        if file_list:
                            sched_path = tender_path / sched.replace("/", "_").replace(" ", "_")
                            sched_path.mkdir(exist_ok=True)
                            for i, file in enumerate(file_list):
                                file_path = sched_path / file.name
                                with open(file_path, "wb") as f:
                                    f.write(file.getbuffer())
                                manifest["tenders"][tender_name][sched].append(file.name)
                
                with open(tmp_path / "manifest.json", "w") as f:
                    json.dump(manifest, f, indent=2)
                
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zipf:
                    for root, dirs, files in os.walk(tmp_path):
                        for file in files:
                            file_path = Path(root) / file
                            arcname = file_path.relative_to(tmp_path)
                            zipf.write(file_path, arcname)
                
                zip_buffer.seek(0)
                st.download_button(
                    label="📥 Download Session Backup ZIP",
                    data=zip_buffer,
                    file_name="tender_session_backup.zip",
                    mime="application/zip"
                )

with col_load:
    uploaded_zip = st.file_uploader("📂 Load Saved Session (ZIP)", type=["zip"])
    if uploaded_zip and st.button("Restore Session"):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with zipfile.ZipFile(uploaded_zip, "r") as zip_ref:
                zip_ref.extractall(tmp_path)
            
            manifest_path = tmp_path / "manifest.json"
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = json.load(f)
                
                st.session_state.tenders = {}
                for tender_name, sched_data in manifest["tenders"].items():
                    st.session_state.tenders[tender_name] = {sched: [] for sched in schedules}
                    for sched, filenames in sched_data.items():
                        for fname in filenames:
                            file_path = tmp_path / tender_name / sched.replace("/", "_").replace(" ", "_") / fname
                            if file_path.exists():
                                with open(file_path, "rb") as f:
                                    bytes_data = f.read()
                                # Create fake UploadedFile
                                fake_file = type('obj', (object,), {
                                    'name': fname,
                                    'getbuffer': lambda b=bytes_data: b
                                })()
                                st.session_state.tenders[tender_name][sched].append(fake_file)
                
                st.success("✅ Session restored successfully!")
                st.rerun()
            else:
                st.error("Invalid backup file")

# ==================== EVALUATE SECTION ====================
if st.button("🚀 Evaluate All Tenders", type="primary"):
    if not st.session_state.tenders:
        st.error("No tenders added")
    else:
        results = []
        progress = st.progress(0)
        
        for idx, (tender_name, schedules_dict) in enumerate(st.session_state.tenders.items()):
            full_text = ""
            for cat_name, file_list in schedules_dict.items():
                if file_list:
                    full_text += f"\n\n=== {cat_name} ===\n"
                    for file in file_list:
                        full_text += extract_text(file) + "\n"
            
            llm_score, criteria_scores, expl = llm_deep_score(full_text, tender_name)
            
            weighted = sum((criteria_scores.get(crit, 0) / 100) * weight 
                          for crit, weight in criteria_weighting.items())
            
            row = {
                "Tender Name": tender_name,
                "Weighted Score": round(weighted, 1),
                "LLM Overall": llm_score,
                "Explanation": expl[:300] + "..." if len(expl) > 300 else expl,
                **criteria_scores
            }
            results.append(row)
            progress.progress((idx + 1) / len(st.session_state.tenders))
        
        df = pd.DataFrame(results)
        ranked = df.sort_values("Weighted Score", ascending=False).reset_index(drop=True)
        ranked["Rank"] = ranked.index + 1
        
        st.subheader("🏆 Final Ranking (Official Weighting)")
        st.dataframe(ranked[["Rank", "Tender Name", "Weighted Score", "LLM Overall", "Explanation"]], 
                     use_container_width=True, height=600)
        
        st.subheader("📊 Detailed Per-Criteria Breakdown")
        selected = st.multiselect("Select tenders to compare", df["Tender Name"].tolist(), default=df["Tender Name"].tolist()[:4])
        if selected:
            compare_df = df[df["Tender Name"].isin(selected)]
            breakdown = compare_df[["Tender Name"] + list(criteria_weighting.keys())].set_index("Tender Name")
            st.dataframe(breakdown.style.format("{:.1f}"), use_container_width=True)
        
        st.download_button("📥 Download Full Results CSV", df.to_csv(index=False), "evaluation_results.csv", "text/csv")
        
        st.success("✅ Evaluation complete")
