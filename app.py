import io
import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from google import genai
from google.genai import types
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

MODEL_NAME = "gemini-3.1-flash-lite"
PROMPT_FILE = "prompt_qa.txt"

st.set_page_config(page_title="Agente QA V1.2", layout="wide")
st.title("Agente QA V1.2")
st.caption("VERSION PREVIA — DRAFT | Generación de casos de prueba y Excel compatible con Azure Test Plans")

def get_key():
    return st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")

def load_prompt():
    return Path(PROMPT_FILE).read_text(encoding="utf-8")

def safe_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
    return json.loads(text.strip())

def normalize(data):
    if not isinstance(data, dict):
        data = {}
    data.setdefault("TEST_CASES", [])
    data.setdefault("ALERTS", [])
    data.setdefault("COVERAGE", [])
    return data

def case_alert_text(alerts):
    return "; ".join(
        a.get("Alert", "") if isinstance(a, dict) else str(a)
        for a in (alerts or [])
    )

def build_qa_df(data):
    rows = []
    for tc in data["TEST_CASES"]:
        alerts = case_alert_text(tc.get("Alerts", []))
        steps = tc.get("Steps", []) or []
        for step in steps:
            rows.append({
                "ID": tc.get("ID", ""),
                "Title": tc.get("Title", ""),
                "Description": tc.get("Description", ""),
                "Expected Result": tc.get("Expected Result", ""),
                "Preconditions": tc.get("Preconditions", ""),
                "Product": tc.get("Product", ""),
                "Module": tc.get("Module", ""),
                "Related Use Case": tc.get("Related Use Case", ""),
                "Step #": step.get("Step #", ""),
                "Action": step.get("Action", ""),
                "Expected value": step.get("Expected value", ""),
                "Alerts": alerts
            })
    return pd.DataFrame(rows)

def build_azure_df(data):
    rows = []
    for tc in data["TEST_CASES"]:
        title = tc.get("Title", "")
        # New cases: Azure ID remains empty.
        for step in tc.get("Steps", []) or []:
            rows.append({
                "TestCaseId": "",
                "Title": title,
                "TestStep": step.get("Step #", ""),
                "StepAction": step.get("Action", ""),
                "StepExpected": step.get("Expected value", ""),
                "TestPointId": "",
                "Configuration": "",
                "Tester": "",
                "Outcome": "",
                "Comment": ""
            })
    return pd.DataFrame(rows)

def format_sheet(ws):
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="D9EAF7")
        cell.alignment = Alignment(vertical="top", wrap_text=True)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        max_len = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 45)

def excel_file(data):
    qa = build_qa_df(data)
    azure = build_azure_df(data)

    # Second sheet: additional QA information.
    extra_rows = []
    for tc in data["TEST_CASES"]:
        alerts = case_alert_text(tc.get("Alerts", []))
        steps = tc.get("Steps", []) or [None]
        for step in steps[:1]:
            extra_rows.append({
                "TestCaseId": "",
                "Description": tc.get("Description", ""),
                "Preconditions": tc.get("Preconditions", ""),
                "Product": tc.get("Product", ""),
                "Module": tc.get("Module", ""),
                "Related Use Case": tc.get("Related Use Case", ""),
                "Criterion": "",
                "Scenario": "",
                "Validation Method": "",
                "Coverage": "",
                "Alerts": alerts
            })
    extra = pd.DataFrame(extra_rows, columns=[
        "TestCaseId", "Description", "Preconditions", "Product", "Module",
        "Related Use Case", "Criterion", "Scenario", "Validation Method",
        "Coverage", "Alerts"
    ])

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        azure.to_excel(writer, index=False, sheet_name="Azure Import")
        extra.to_excel(writer, index=False, sheet_name="Datos Adicionales")

    wb = load_workbook(io.BytesIO(out.getvalue()))
    # Ensure Azure Import is the first sheet.
    wb._sheets = [wb["Azure Import"], wb["Datos Adicionales"]]
    for ws in wb.worksheets:
        format_sheet(ws)

    final = io.BytesIO()
    wb.save(final)
    return final.getvalue()


def pdf_file(data):
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=landscape(A4),
        rightMargin=24, leftMargin=24, topMargin=24, bottomMargin=24
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    title_style.alignment = TA_CENTER
    small = ParagraphStyle("small", parent=styles["BodyText"], fontSize=7, leading=9)
    heading = styles["Heading2"]
    story = [
        Paragraph("AGENTE QA — VERSION PREVIA — DRAFT", title_style),
        Spacer(1, 8),
        Paragraph("Casos de prueba funcionales, trazabilidad, cobertura y alertas", styles["BodyText"]),
        Spacer(1, 12)
    ]

    for tc in data["TEST_CASES"]:
        story.append(Paragraph(f'{tc.get("ID","")} — {tc.get("Title","")}', heading))
        story.append(Paragraph(f'<b>Description:</b> {tc.get("Description","")}', small))
        story.append(Paragraph(f'<b>Expected Result:</b> {tc.get("Expected Result","")}', small))
        story.append(Paragraph(f'<b>Preconditions:</b> {tc.get("Preconditions","")}', small))
        story.append(Spacer(1, 5))

        rows = [["Step #", "Action", "Expected value"]]
        for step in tc.get("Steps", []) or []:
            rows.append([
                str(step.get("Step #", "")),
                Paragraph(str(step.get("Action", "")), small),
                Paragraph(str(step.get("Expected value", "")), small)
            ])
        table = Table(rows, colWidths=[45, 330, 330], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#D9EAF7")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("FONTSIZE", (0,0), (-1,-1), 7),
        ]))
        story.append(table)

        alerts = tc.get("Alerts", []) or []
        if alerts:
            story.append(Spacer(1, 6))
            story.append(Paragraph("<b>Alerts</b>", styles["Heading3"]))
            for a in alerts:
                if isinstance(a, dict):
                    text = f'{a.get("Alert","")} — {a.get("Reason","")} — {a.get("Validation Required","")}'
                else:
                    text = str(a)
                story.append(Paragraph(text, small))

        story.append(Spacer(1, 14))

    if data.get("COVERAGE"):
        story.append(PageBreak())
        story.append(Paragraph("MATRIZ DE COBERTURA", heading))
        rows = [["Requirement / Use Case", "Criterion", "Scenario", "Test Case",
                 "Validation Method", "Coverage", "Alerts"]]
        for c in data["COVERAGE"]:
            rows.append([
                Paragraph(str(c.get("Requirement / Use Case","")), small),
                Paragraph(str(c.get("Criterion","")), small),
                Paragraph(str(c.get("Scenario","")), small),
                Paragraph(str(c.get("Test Case","")), small),
                Paragraph(str(c.get("Validation Method","")), small),
                Paragraph(str(c.get("Coverage","")), small),
                Paragraph(str(c.get("Alerts","")), small),
            ])
        table = Table(rows, colWidths=[100,100,100,65,100,65,130], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#D9EAF7")),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
            ("FONTSIZE", (0,0), (-1,-1), 6),
        ]))
        story.append(table)

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
            prompt = load_prompt()
            instruction = prompt + """
IMPORTANTE PARA ESTA EJECUCIÓN:
Genera Steps atómicos siguiendo estrictamente las reglas del prompt.
Devuelve únicamente JSON válido.
Claves raíz obligatorias: TEST_CASES, ALERTS, COVERAGE.
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
                    parts.append(types.Part.from_text(
                        text=f"FUENTE: {f.name}\n{text}"
                    ))

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json"
                )
            )

            result = normalize(safe_json(response.text))
            st.session_state["result"] = result
            st.success("Procesamiento completado.")
    except Exception as e:
        st.error(f"Error al procesar: {e}")

if "result" in st.session_state:
    result = st.session_state["result"]
    st.subheader("Resultados — VERSION PREVIA — DRAFT")

    edited = st.text_area(
        "Editar resultado JSON antes de exportar",
        value=json.dumps(result, ensure_ascii=False, indent=2),
        height=500
    )

    try:
        result = normalize(json.loads(edited))
        st.session_state["result"] = result

        excel_bytes = excel_file(result)
        pdf_bytes = pdf_file(result)

        st.download_button(
            "Descargar Excel — Azure + Datos QA",
            data=excel_bytes,
            file_name="Agente_QA_V1_4_Azure_QA.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        st.download_button(
            "Descargar PDF — Resumen QA",
            data=pdf_bytes,
            file_name="Agente_QA_V1_4_Resumen_QA.pdf",
            mime="application/pdf"
        )

    except json.JSONDecodeError:
        st.warning("El resultado editado todavía no contiene JSON válido.")
