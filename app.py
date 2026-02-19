import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
import tempfile
from pathlib import Path
from groq import Groq
import json
import time

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v3.0")
st.markdown("**T2526.25 DRFA Moura – Part 6 Checklist**  \nAdd tenders and upload one file per category")

checklist = [
    "Tender Form",
    "A1-A4",
    "B1-B2",
    "C1-C2",
    "D1-D3",
    "E1-E3",
    "F1-F2",
    "G1-G3",
    "H",
    "I",
    "J1-J3",
    "K-O"
]

if 'tenders' not in st.session_state:
    st.session_state.tenders = {}

# Add new tender
col1, col2 = st.columns([3,1])
with col1:
    new_name = st.text_input("New Tender Name")
with col2:
    if st.button("Add Tender", type="primary") and new_name.strip():
        if new_name not in st.session_state.tenders:
            st.session_state.tenders[new_name] = {cat: None for cat in checklist}
            st.success(f"Added: {new_name}")

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

def llm_deep_score(text, tender_name):
    if not groq_key:
        return 0, {}, "No API key"
    prompt = f"""Evaluate this tender response against the Banana Shire Council Part 6 checklist.

Checklist items:
{chr(10).join(checklist)}

Tender: {tender_name}

Text:
{text[:14000]}

Return ONLY valid JSON:
{{
  "overall_score": number 0-100,
  "item_scores": {{
    "Tender Form": 0-10,
    "A1-A4": 0-10,
    "B1-B2": 0-10,
    "C1-C2": 0-10,
    "D1-D3": 0-10,
    "E1-E3": 0-10,
    "F1-F2": 0-10,
    "G1-G3": 0-10,
    "H": 0-10,
    "I": 0-10,
    "J1-J3": 0-10,
    "K-O": 0-10
  }},
  "explanation": "short summary"
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
        return data.get("overall_score", 0), data.get("item_scores", {}), data.get("explanation", "")
    except Exception as e:
        return 0, {}, f"Error: {str(e)[:100]}"

# Show uploaders for each tender
for tender in list(st.session_state.tenders.keys()):
    with st.expander(f"📂 {tender}", expanded=False):
        for cat in checklist:
            uploaded_file = st.file_uploader(f"{cat}", key=f"{tender}_{cat}", type=['pdf','xlsx','docx','doc'])
            if uploaded_file:
                st.session_state.tenders[tender][cat] = uploaded_file

# Evaluate button
if st.button("🚀 Evaluate All Tenders", type="primary"):
    if not st.session_state.tenders:
        st.error("No tenders added")
    else:
        results = []
        progress = st.progress(0)
        for idx, (tender_name, files) in enumerate(st.session_state.tenders.items()):
            full_text = ""
            for cat, file in files.items():
                if file:
                    full_text += f"\n\n=== {cat} ===\n" + extract_text(file) + "\n"
            
            score, item_scores, expl = llm_deep_score(full_text, tender_name)
            
            row = {"Tender Name": tender_name, "Overall Score": score, "Explanation": expl}
            row.update(item_scores)
            results.append(row)
            progress.progress((idx+1) / len(st.session_state.tenders))
        
        df = pd.DataFrame(results)
        
        st.subheader("🏆 Final Ranking")
        ranked = df.sort_values("Overall Score", ascending=False).reset_index(drop=True)
        ranked["Rank"] = ranked.index + 1
        st.dataframe(ranked[["Rank", "Tender Name", "Overall Score", "Explanation"]], use_container_width=True)
        
        st.subheader("📋 Per-Category Scores")
        selected = st.multiselect("Select tenders", df["Tender Name"].tolist(), default=df["Tender Name"].tolist()[:3])
        if selected:
            cat_df = df[df["Tender Name"].isin(selected)][["Tender Name"] + checklist].set_index("Tender Name")
            st.dataframe(cat_df, use_container_width=True)
        
        st.download_button("📥 Download Full Results CSV", df.to_csv(index=False), "tender_evaluation_results.csv", "text/csv")

st.caption("v3.0 - Separate file uploads per category per tender")
