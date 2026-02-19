import streamlit as st
import pandas as pd
from PyPDF2 import PdfReader
import re
import tempfile
import zipfile
from pathlib import Path
from groq import Groq
import json
import time

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v2.1")
st.markdown("**T2526.25 DRFA Moura – Part 6 Response Schedules**  \nUpload ZIP files (one tender per ZIP) or individual files")

# Checklist
checklist = {
    "Tender Form": "Signed offer, price, program",
    "A1-A4": "Details, Conflict, Legal, Privacy",
    "B1-B2": "Solvency & Financial Statements",
    "C1-C2": "Insurances",
    "D1-D3": "Local Content, Employment, Environmental",
    "E1-E3": "Experience, Past Projects, Resources",
    "F1-F2": "Key Personnel CVs & Allocation + Subs",
    "G1-G3": "WHS, Environmental, Quality Systems",
    "H": "Methodology",
    "I": "Program / Gantt",
    "J1-J3": "Pricing, Cash Flow, Variation Rates",
    "K-O": "Technical Data, Departures, Additional Info"
}

groq_key = st.text_input("Groq API Key (for LLM deep scoring)", type="password")

def extract_text_from_file(file_path):
    text = ""
    try:
        if file_path.suffix.lower() == ".pdf":
            reader = PdfReader(str(file_path))
            for page in reader.pages:
                text += page.extract_text() or ""
        elif file_path.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(file_path)
            text = df.to_string()
        elif file_path.suffix.lower() in [".docx", ".doc"]:
            from docx import Document
            doc = Document(file_path)
            text = "\n".join([para.text for para in doc.paragraphs])
        else:
            text = file_path.read_text(encoding="utf-8", errors="ignore")
    except:
        pass
    return text

def llm_deep_score(full_text, tender_name, retries=2):
    if not groq_key:
        return 0, "No API key"
    
    prompt = f"""You are an expert tender evaluator for Banana Shire Council.

Evaluate the following tender response against the Part 6 checklist.

Checklist items (score each 0-10):
{chr(10).join([f"- {k}: {v}" for k, v in checklist.items()])}

Tender Name: {tender_name}
Text: {full_text[:15000]}

Return **ONLY** valid JSON in this exact format. Do not add any extra text:

{{
  "overall_score": number between 0 and 100,
  "explanation": "Brief 2-3 sentence summary of strengths and weaknesses"
}}

If the text is unclear or incomplete, still return valid JSON with your best estimate."""

    for attempt in range(retries + 1):
        try:
            client = Groq(api_key=groq_key)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0,
                max_tokens=600,
                response_format={"type": "json_object"}
            )
            
            result = chat_completion.choices[0].message.content.strip()
            data = json.loads(result)
            
            return data.get("overall_score", 0), data.get("explanation", "No explanation provided")
            
        except Exception as e:
            if attempt == retries:
                return 0, f"LLM failed after {retries+1} attempts: {str(e)[:100]}"
            time.sleep(1)  # small delay before retry
    
    return 0, "Unknown error"

# Upload
uploaded = st.file_uploader("Upload ZIP files (one tender per ZIP) or individual files", 
                           accept_multiple_files=True, type=['zip', 'pdf', 'xlsx', 'docx'])

if uploaded and groq_key:
    results = []
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded):
        tender_name = file.name.replace(".zip", "") if file.name.endswith(".zip") else file.name.split('.')[0]
        full_text = ""
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            if file.name.endswith(".zip"):
                with zipfile.ZipFile(file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                for f in tmp_path.rglob("*"):
                    if f.is_file():
                        full_text += extract_text_from_file(f) + "\n"
            else:
                with open(tmp_path / file.name, "wb") as f:
                    f.write(file.getbuffer())
                full_text = extract_text_from_file(tmp_path / file.name)
        
        llm_score, explanation = llm_deep_score(full_text, tender_name)
        
        results.append({
            "Tender Name": tender_name,
            "LLM Deep Score": f"{llm_score}%",
            "Explanation": explanation[:300] + "..." if len(explanation) > 300 else explanation
        })
        
        progress_bar.progress((i + 1) / len(uploaded))
    
    df = pd.DataFrame(results)
    st.dataframe(df, use_container_width=True, height=700)
    
    # Side-by-side comparison
    st.subheader("🔍 Side-by-Side Comparison")
    selected = st.multiselect("Select tenders to compare", df["Tender Name"].tolist(), default=df["Tender Name"].tolist()[:3])
    if selected:
        compare_df = df[df["Tender Name"].isin(selected)].set_index("Tender Name")
        st.dataframe(compare_df, use_container_width=True)
    
    st.download_button("📥 Download Results CSV", df.to_csv(index=False), "tender_evaluation_results.csv", "text/csv")
    
    st.success(f"✅ Evaluated {len(uploaded)} tenders with improved LLM prompt")
