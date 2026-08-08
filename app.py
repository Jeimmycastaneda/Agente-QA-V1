import os
import io
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

st.set_page_config(page_title="Agente QA V1", layout="wide")

MODEL_NAME = "gemini-3.1-flash-lite"
PROMPT_FILE = "prompt_qa.txt"

st.title("Agente QA V1")
st.caption("Generador de casos de prueba funcionales — VERSION PREVIA — DRAFT")

def get_prompt():
    return Path(PROMPT_FILE).read_text(encoding="utf-8")

def get_key():
    return st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

def excel_bytes(data):
    rows = []
    for tc in data.get("TEST_CASES", []):
        alerts = "; ".join(
            a.get("Alert", "") if isinstance(a, dict) else str(a)
            for a in tc.get("Alerts", [])
        )
        steps = tc.get("Steps", []) or [{"Step #": "", "Action": "", "Expected value": ""}]
        for s in steps:
            rows.append({
                "ID": tc.get("ID", ""),
                "Title": tc.get("Title", ""),
                "Description": tc.get("Description", ""),
                "Expected Result": tc.get("Expected Result", ""),
                "Preconditions": tc.get("Preconditions", ""),
                "Product": tc.get("Product", ""),
                "Module": tc.get("Module", ""),
                "Related Use Case": tc.get("Related Use Case", ""),
                "Step #": s.get("Step #", ""),
                "Action": s.get("Action", ""),
                "Expected value": s.get("Expected value", ""),
                "Alerts": alerts
            })
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="Test Cases")
        pd.DataFrame(data.get("COVERAGE", [])).to_excel(writer, index=False, sheet_name="Coverage")
        pd.DataFrame(data.get("ALERTS", [])).to_excel(writer, index=False, sheet_name="Alerts")
    return out.getvalue()

def pdf_bytes(data):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = [Paragraph("Agente QA V1 — VERSION PREVIA — DRAFT", styles["Title"]), Spacer(1, 12)]
    for tc in data.get("TEST_CASES", []):
        story.append(Paragraph(f"{tc.get('ID','')} — {tc.get('Title','')}", styles["Heading2"]))
        for field in ["Description","Expected Result","Preconditions","Product","Module","Related Use Case"]:
            story.append(Paragraph(f"<b>{field}:</b> {tc.get(field,'')}", styles["BodyText"]))
        steps = [["Step #", "Action", "Expected value"]]
        for s in tc.get("Steps", []):
            steps.append([str(s.get("Step #","")), str(s.get("Action","")), str(s.get("Expected value",""))])
        if len(steps) > 1:
            t = Table(steps, repeatRows=1)
            t.setStyle(TableStyle([
                ("GRID",(0,0),(-1,-1),0.5,colors.grey),
                ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                ("VALIGN",(0,0),(-1,-1),"TOP")
            ]))
            story += [Spacer(1, 6), t]
        story.append(PageBreak())
    doc.build(story)
    return out.getvalue()

files = st.file_uploader(
    "Cargar Historia de Usuario y documentos asociados",
    type=["txt", "md", "pdf", "docx", "xlsx", "csv"],
    accept_multiple_files=True
)

if files:
    st.write("Archivos cargados:", ", ".join(f.name for f in files))

if files and st.button("Procesar con Agente QA", type="primary"):
    key = get_key()
    if not key:
        st.error("No se encontró GEMINI_API_KEY en Secrets.")
        st.stop()

    try:
        with st.spinner(f"Procesando con {MODEL_NAME}..."):
            client = genai.Client(api_key=key)
            instruction = get_prompt() + """
La salida debe ser exclusivamente JSON válido.
Usa exactamente estas claves raíz: TEST_CASES, ALERTS, COVERAGE.
No agregues texto antes ni después del JSON.
"""
            parts = [types.Part.from_text(text=instruction)]
            for f in files:
                raw = f.getvalue()
                if f.type == "application/pdf":
                    parts.append(types.Part.from_bytes(data=raw, mime_type="application/pdf"))
                else:
                    try:
                        text = raw.decode("utf-8")
                    except Exception:
                        text = f"Archivo proporcionado: {f.name}"
                    parts.append(types.Part.from_text(text=f"FUENTE: {f.name}\n{text}"))

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json"
                )
            )
            result = json.loads(response.text)
            st.session_state["result"] = result
            st.success("Procesamiento completado.")
    except Exception as e:
        st.error(f"Error al procesar: {e}")

if "result" in st.session_state:
    result = st.session_state["result"]
    st.subheader("Resultados — VERSION PREVIA — DRAFT")
    edited = st.text_area(
        "Editar resultado antes de exportar",
        value=json.dumps(result, ensure_ascii=False, indent=2),
        height=450
    )
    try:
        result = json.loads(edited)
        st.session_state["result"] = result
        st.download_button(
            "Descargar Excel", excel_bytes(result), "Agente_QA_V1.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        st.download_button(
            "Descargar PDF", pdf_bytes(result), "Agente_QA_V1.pdf", "application/pdf"
        )
    except json.JSONDecodeError:
        st.warning("El resultado editado todavía no contiene JSON válido.")
