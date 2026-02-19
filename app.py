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
from fpdf import FPDF

st.set_page_config(page_title="Tender Evaluator", layout="wide")
st.title("🍌 Banana Shire Council Tender Evaluator v2.4")
st.markdown("**T2526.25 DRFA Moura – Part 6 Checklist**  \nUpload ZIPs (preferred) or multiple individual files")

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

groq_key = st.text_input("Groq API Key", type="password")

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

def llm_deep_score(full_text, tender_name):
    if not groq_key:
        return 0, {}, "No API key"
    
    prompt = f"""You are an expert tender evaluator.

Evaluate this tender against the Banana Shire Council Part 6 checklist.

Checklist:
{chr(10).join([f"- {k}: {v}" for k, v in checklist.items()])}

Tender: {tender_name}
Text: {full_text[:14000]}

Return ONLY valid JSON:
{{
  "overall_score": 0-100,
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
  "explanation": "Brief 2-3 sentence summary"
}}"""

    for attempt in range(3):
        try:
            client = Groq(api_key=groq_key)
            chat = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.0,
                max_tokens=800,
                response_format={"type": "json_object"}
            )
            data = json.loads(chat.choices[0].message.content.strip())
            return data.get("overall_score", 0), data.get("item_scores", {}), data.get("explanation", "")
        except:
            time.sleep(1)
    return 0, {}, "LLM failed after retries"

# Upload
uploaded = st.file_uploader("Upload ZIP files (one tender per ZIP with folders) or multiple individual files", 
                           accept_multiple_files=True, type=['zip', 'pdf', 'xlsx', 'docx'])

if uploaded and groq_key:
    results = []
    progress_bar = st.progress(0)
    
    for i, file in enumerate(uploaded):
        tender_name = file.name.replace(".zip", "") if file.name.endswith(".zip") else file.name.split('.')[0]
        full_text = ""
        category_texts = {cat: "" for cat in checklist.keys()}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            if file.name.endswith(".zip"):
                with zipfile.ZipFile(file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                for f in tmp_path.rglob("*"):
                    if f.is_file():
                        text = extract_text_from_file(f)
                        full_text += text + "\n"
                        # Auto-detect category
                        for cat in checklist.keys():
                            if any(word in f.name.lower() for word in cat.lower().split("-") + cat.lower().split()):
                                category_texts[cat] += text + "\n"
                                break
            else:
                with open(tmp_path / file.name, "wb") as f:
                    f.write(file.getbuffer())
                text = extract_text_from_file(tmp_path / file.name)
                full_text = text
                for cat in checklist.keys():
                    if any(word in file.name.lower() for word in cat.lower().split()):
                        category_texts[cat] = text
                        break
        
        llm_score, item_scores, explanation = llm_deep_score(full_text, tender_name)
        
        row = {
            "Tender Name": tender_name,
            "Overall Score": llm_score,
            "Explanation": explanation[:300] + "..." if len(explanation) > 300 else explanation,
            **item_scores
        }
        results.append(row)
        progress_bar.progress((i + 1) / len(uploaded))
    
    df = pd.DataFrame(results)
    
    # Automatic Ranking with Colour Coding
    st.subheader("🏆 Automatic Ranking")
    ranked_df = df.sort_values(by="Overall Score", ascending=False).reset_index(drop=True)
    ranked_df["Rank"] = ranked_df.index + 1
    st.dataframe(
        ranked_df.style.background_gradient(subset=["Overall Score"], cmap="RdYlGn")
        .format({"Overall Score": "{:.1f}"}),
        use_container_width=True,
        height=600
    )
    
    # Side-by-side + Per-Category Table
    st.subheader("🔍 Detailed Comparison")
    selected = st.multiselect("Select tenders to compare", df["Tender Name"].tolist(), default=df["Tender Name"].tolist()[:4])
    
    if selected:
        compare_df = df[df["Tender Name"].isin(selected)]
        st.dataframe(compare_df, use_container_width=True)
        
        st.subheader("📋 Per-Category Scoring Table")
        cat_df = compare_df[["Tender Name"] + list(checklist.keys())].set_index("Tender Name")
        st.dataframe(
            cat_df.style.background_gradient(cmap="RdYlGn", axis=None)
            .format("{:.1f}"),
            use_container_width=True
        )
        
        # PDF Export
        if st.button("📄 Export Full Comparison Report as PDF"):
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", "B", 16)
            pdf.cell(0, 10, "Banana Shire Council Tender Comparison Report", ln=True, align="C")
            pdf.ln(10)
            
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, "Ranked Results", ln=True)
            for _, row in ranked_df.iterrows():
                pdf.cell(0, 8, f"Rank {row['Rank']}: {row['Tender Name']} - {row['Overall Score']}%", ln=True)
            
            pdf.ln(10)
            pdf.cell(0, 10, "Per-Category Scores", ln=True)
            pdf.set_font("Arial", "", 10)
            for cat in checklist.keys():
                pdf.cell(0, 8, f"{cat}:", ln=True)
                for t in selected:
                    score = compare_df.loc[compare_df["Tender Name"] == t, cat].values[0]
                    pdf.cell(0, 8, f"   {t}: {score}/10", ln=True)
            
            pdf.output("comparison_report.pdf")
            with open("comparison_report.pdf", "rb") as f:
                st.download_button("Download PDF Report", f, "comparison_report.pdf", "application/pdf")
    
    st.success(f"✅ Evaluated {len(uploaded)} tenders with automatic ranking & colour coding")
