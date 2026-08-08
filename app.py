import io
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from pypdf import PdfReader
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER

st.set_page_config(page_title="Agente QA V1", page_icon="QA", layout="wide")

MODEL = "gemini-2.5-flash"
PROMPT_FILE = Path("prompt_qa.txt")

SCHEMA = {
    "type": "object",
    "properties": {
        "TEST_CASES": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ID": {"type": "string"},
                    "Title": {"type": "string"},
                    "Description": {"type": "string"},
                    "Expected Result": {"type": "string"},
                    "Preconditions": {"type": "string"},
                    "Product": {"type": "string"},
                    "Module": {"type": "string"},
                    "Related Use Case": {"type": "string"},
                    "Steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Step #": {"type": "string"},
                                "Action": {"type": "string"},
                                "Expected value": {"type": "string"}
                            },
                            "required": ["Step #", "Action", "Expected value"]
                        }
                    },
                    "Alerts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Alert": {"type": "string"},
                                "Reason": {"type": "string"},
                                "Validation Required": {"type": "string"}
                            },
                            "required": ["Alert", "Reason", "Validation Required"]
                        }
                    }
                },
                "required": ["ID", "Title", "Description", "Expected Result",
                             "Preconditions", "Product", "Module", "Related Use Case",
                             "Steps", "Alerts"]
            }
        },
        "COVERAGE": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "Requirement / Use Case": {"type": "string"},
                    "Criterion": {"type": "string"},
                    "Scenario": {"type": "string"},
                    "Test Case": {"type": "string"},
                    "Validation Method": {"type": "string"},
                    "Coverage": {"type": "string"},
                    "Alerts": {"type": "string"}
                },
                "required": ["Requirement / Use Case", "Criterion", "Scenario",
                             "Test Case", "Validation Method", "Coverage", "Alerts"]
            }
        }
    },
    "required": ["TEST_CASES", "COVERAGE"]
}

def api_key():
    try:
        return st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        return os.getenv("GEMINI_API_KEY", "")

def read_file(f):
    name = f.name.lower()
    data = f.getvalue()
    if name.endswith((".txt", ".md", ".csv")):
        return data.decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    if name.endswith(".xlsx"):
        x = pd.ExcelFile(io.BytesIO(data))
        return "\n".join(
            f"--- SHEET: {s} ---\n{pd.read_excel(x, sheet_name=s, header=None).fillna('').to_string(index=False, header=False)}"
            for s in x.sheet_names
        )
    raise ValueError(f"Formato no soportado: {f.name}")

def process(files):
    key = api_key()
    if not key:
        raise RuntimeError("Falta GEMINI_API_KEY. La configuraremos en Streamlit Secrets.")
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    source = "\n\n".join(f"===== {f.name} =====\n{read_file(f)}" for f in files)
    source = source[:180000]
    instruction = f"""
Analiza exclusivamente la documentación suministrada.
Aplica todas las reglas del prompt del Agente QA.
No inventes información.
Genera VERSION PREVIA — DRAFT.
Conserva literalmente los mensajes definidos en la fuente.
Genera alertas ante cualquier ausencia, contradicción, ambigüedad o dependencia.
Devuelve únicamente JSON válido según el esquema.

DOCUMENTACIÓN:
{source}
"""
    client = genai.Client(api_key=key)
    r = client.models.generate_content(
        model=MODEL,
        contents=prompt + "\n\n" + instruction,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA,
            temperature=0.1
        )
    )
    return json.loads(r.text)

def case_df(result):
    return pd.DataFrame([{
        k: tc.get(k, "") for k in
        ["ID", "Title", "Description", "Expected Result", "Preconditions",
         "Product", "Module", "Related Use Case"]
    } for tc in result["TEST_CASES"]])

def steps_df(result):
    rows = []
    for tc in result["TEST_CASES"]:
        for s in tc.get("Steps", []):
            rows.append({"Test Case": tc["ID"], **s})
    return pd.DataFrame(rows, columns=["Test Case", "Step #", "Action", "Expected value"])

def alerts_df(result):
    rows = []
    for tc in result["TEST_CASES"]:
        for a in tc.get("Alerts", []):
            rows.append({"Test Case": tc["ID"], **a})
    return pd.DataFrame(rows, columns=["Test Case", "Alert", "Reason", "Validation Required"])

def excel_file(result):
    wb = Workbook()
    ws = wb.active
    ws.title = "TEST_CASES"
    headers = ["ID","Title","Description","Expected Result","Preconditions","Product","Module",
               "Related Use Case","Step #","Action","Expected value","Alerts"]
    ws.append(headers)
    for tc in result["TEST_CASES"]:
        alert_text = "\n".join(
            f'{a.get("Alert","")} | {a.get("Reason","")} | {a.get("Validation Required","")}'
            for a in tc.get("Alerts", [])
        )
        steps = tc.get("Steps", []) or [{}]
        for s in steps:
            ws.append([tc.get(h,"") for h in headers[:8]] +
                      [s.get("Step #",""), s.get("Action",""), s.get("Expected value",""), alert_text])

    cov = wb.create_sheet("COVERAGE")
    ch = ["Requirement / Use Case","Criterion","Scenario","Test Case","Validation Method","Coverage","Alerts"]
    cov.append(ch)
    for row in result["COVERAGE"]:
        cov.append([row.get(h,"") for h in ch])

    for sh in wb.worksheets:
        sh.freeze_panes = "A2"
        for i in range(1, sh.max_column + 1):
            sh.column_dimensions[get_column_letter(i)].width = min(45, max(14, max(
                (len(str(c.value or "")) for c in list(sh.iter_cols(min_col=i,max_col=i))[0][:30]), default=14
            ) + 2))
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()

def pdf_file(result):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=8, leading=10)
    story = [Paragraph("AGENTE QA V1 — VERSION PREVIA — DRAFT", styles["Title"]),
             Paragraph("Casos de prueba, trazabilidad, cobertura y alertas.", styles["BodyText"]),
             Spacer(1, 12)]
    for tc in result["TEST_CASES"]:
        story.append(Paragraph(f'{tc["ID"]} — {tc["Title"]}', styles["Heading2"]))
        for h in ["Description","Expected Result","Preconditions","Product","Module","Related Use Case"]:
            story.append(Paragraph(f'<b>{h}:</b> {tc.get(h,"")}', small))
        data = [["Step #","Action","Expected value"]]
        data += [[s.get("Step #",""),s.get("Action",""),s.get("Expected value","")] for s in tc.get("Steps",[])]
        if len(data) > 1:
            t = Table(data, colWidths=[45,220,250], repeatRows=1)
            t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),
                                   ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                                   ("VALIGN",(0,0),(-1,-1),"TOP"),
                                   ("FONTSIZE",(0,0),(-1,-1),7)]))
            story += [Spacer(1,6), t]
        for a in tc.get("Alerts",[]):
            story.append(Paragraph(
                f'<b>{a.get("Alert","")}</b> — {a.get("Reason","")} — {a.get("Validation Required","")}',
                small))
        story.append(PageBreak())
    story.append(Paragraph("MATRIZ DE COBERTURA", styles["Heading1"]))
    headers = ["Requirement / Use Case","Criterion","Scenario","Test Case","Validation Method","Coverage","Alerts"]
    data = [headers] + [[r.get(h,"") for h in headers] for r in result["COVERAGE"]]
    if len(data) > 1:
        t = Table(data, repeatRows=1)
        t.setStyle(TableStyle([("GRID",(0,0),(-1,-1),.4,colors.grey),
                               ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
                               ("FONTSIZE",(0,0),(-1,-1),6),
                               ("VALIGN",(0,0),(-1,-1),"TOP")]))
        story.append(t)
    doc.build(story)
    return out.getvalue()

st.title("Agente QA V1")
st.caption("Generador de casos de prueba funcionales — VERSION PREVIA — DRAFT")

files = st.file_uploader(
    "Cargar Historia de Usuario y documentos asociados",
    type=["txt","md","pdf","docx","xlsx","csv"],
    accept_multiple_files=True
)

if files and st.button("Procesar con Agente QA", type="primary"):
    with st.spinner("Analizando documentación..."):
        try:
            st.session_state["result"] = process(files)
            st.success("Análisis terminado.")
        except Exception as e:
            st.error(str(e))

if "result" in st.session_state:
    result = st.session_state["result"]
    st.subheader("Revisión y edición manual")

    cdf = st.data_editor(case_df(result), num_rows="dynamic", use_container_width=True, key="cases")
    sdf = st.data_editor(steps_df(result), num_rows="dynamic", use_container_width=True, key="steps")
    adf = st.data_editor(alerts_df(result), num_rows="dynamic", use_container_width=True, key="alerts")
    cvdf = st.data_editor(pd.DataFrame(result["COVERAGE"]), num_rows="dynamic", use_container_width=True, key="coverage")

    if st.button("Guardar edición"):
        byid = {tc["ID"]: tc for tc in result["TEST_CASES"]}
        for _, r in cdf.fillna("").iterrows():
            tcid = str(r["ID"])
            if tcid not in byid:
                byid[tcid] = {"ID":tcid,"Title":"","Description":"","Expected Result":"",
                              "Preconditions":"","Product":"","Module":"","Related Use Case":"",
                              "Steps":[],"Alerts":[]}
            for h in ["ID","Title","Description","Expected Result","Preconditions","Product","Module","Related Use Case"]:
                byid[tcid][h] = str(r[h])
        for tc in byid.values():
            tc["Steps"] = []
            tc["Alerts"] = []
        for _, r in sdf.fillna("").iterrows():
            if str(r["Test Case"]) in byid:
                byid[str(r["Test Case"])]["Steps"].append({
                    "Step #":str(r["Step #"]), "Action":str(r["Action"]), "Expected value":str(r["Expected value"])
                })
        for _, r in adf.fillna("").iterrows():
            if str(r["Test Case"]) in byid:
                byid[str(r["Test Case"])]["Alerts"].append({
                    "Alert":str(r["Alert"]), "Reason":str(r["Reason"]), "Validation Required":str(r["Validation Required"])
                })
        result["TEST_CASES"] = list(byid.values())
        result["COVERAGE"] = cvdf.fillna("").to_dict("records")
        st.session_state["result"] = result
        st.success("Cambios guardados.")

    st.subheader("Exportación")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("Descargar Excel", excel_file(result),
                           "Casos_Prueba_QA_DRAFT.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with col2:
        st.download_button("Descargar PDF", pdf_file(result),
                           "Casos_Prueba_QA_DRAFT.pdf",
                           "application/pdf",
                           use_container_width=True)
