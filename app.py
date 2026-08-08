import streamlit as st
import pandas as pd
import json
import io
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import google.generativeai as genai

# Configuración de Streamlit
st.set_page_config(page_title="Agente QA V8 - Generador de Pruebas", layout="wide")

st.title("Agente QA V8 — Generador de Casos de Prueba")
st.caption("Cargue su Documento / Historia de Usuario / Caso de Uso para generar el Excel (Azure Import + Matriz QA) y el PDF DRAFT.")

# Cargar el prompt base
@st.cache_data
def load_system_prompt():
    prompt_path = "prompt_qa.txt"
    if os.path.exists(prompt_path):
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

system_prompt = load_system_prompt()

# Configuración de API Key (vía Sidebar o Secret)
api_key = st.sidebar.text_input("Google Gemini API Key", type="password")
selected_model = st.sidebar.selectbox("Modelo", ["gemini-1.5-pro", "gemini-1.5-flash"])

# Entrada de la Historia de Usuario / Fuente de Información
source_text = st.text_area("Ingrese la información fuente (HU, Criterios, Casos de Uso, Reglas de Negocio, etc.):", height=300)

def generate_qa_data(prompt_text, source_content, key, model_name):
    genai.configure(api_key=key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={"response_mime_type": "application/json"}
    )
    
    full_prompt = f"{prompt_text}\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n{source_content}"
    response = model.generate_content(full_prompt)
    return json.loads(response.text)

def create_excel_v8(data):
    output = io.BytesIO()
    
    # 1. Hoja Azure Import
    azure_rows = []
    for tc in data.get("TEST_CASES", []):
        tc_id = tc.get("ID", "")
        tc_title = tc.get("Title", "")
        steps = tc.get("Steps", [])
        
        for idx, step in enumerate(steps):
            # En la estructura Azure Import, el TestCaseId y Title suelen repetir por cada paso
            azure_rows.append({
                "TestCaseId": tc_id,
                "Title": tc_title,
                "TestStep": step.get("Step #", idx + 1),
                "StepAction": step.get("Action", ""),
                "StepExpected": step.get("Expected value", ""),
                "TestPointId": "",
                "Configuration": "",
                "Tester": "",
                "Outcome": "",
                "Comment": ""
            })
            
    df_azure = pd.DataFrame(azure_rows, columns=[
        "TestCaseId", "Title", "TestStep", "StepAction", "StepExpected",
        "TestPointId", "Configuration", "Tester", "Outcome", "Comment"
    ])
    
    # 2. Hoja Matriz QA
    matriz_rows = []
    for tc in data.get("TEST_CASES", []):
        alerts_list = tc.get("Alerts", [])
        alerts_str = " | ".join([f"{a.get('Alert')}: {a.get('Reason')}" for a in alerts_list]) if alerts_list else "Sin Alertas"
        
        matriz_rows.append({
            "TestCaseId": tc.get("ID", ""),
            "Title": tc.get("Title", ""),
            "Requirement / Use Case": tc.get("Related Use Case", ""),
            "Criterion": tc.get("Criterion", ""),
            "Scenario": tc.get("Scenario", ""),
            "Scenario Type": tc.get("Scenario Type", ""),
            "Description": tc.get("Description", ""),
            "Preconditions": tc.get("Preconditions", ""),
            "Validation Method": "UI",  # Valor por defecto o dinámico
            "Coverage": "Completa",     # Valor derivado
            "Alerts": alerts_str,
            "Effort": tc.get("Effort", "No definido")
        })
        
    df_matriz = pd.DataFrame(matriz_rows, columns=[
        "TestCaseId", "Title", "Requirement / Use Case", "Criterion",
        "Scenario", "Scenario Type", "Description", "Preconditions",
        "Validation Method", "Coverage", "Alerts", "Effort"
    ])
    
    # Generar archivo Excel con dos pestañas
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_azure.to_excel(writer, sheet_name="Azure Import", index=False)
        df_matriz.to_excel(writer, sheet_name="Matriz QA", index=False)
        
    output.seek(0)
    return output

def create_pdf_v8(data):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontSize=16, leading=20, textColor=colors.HexColor('#1A365D'))
    h2_style = ParagraphStyle('SectionHeader', parent=styles['Heading2'], fontSize=12, leading=16, textColor=colors.HexColor('#2B6CB0'))
    body_style = ParagraphStyle('BodyText', parent=styles['Normal'], fontSize=9, leading=12)
    bold_style = ParagraphStyle('BoldText', parent=body_style, fontName='Helvetica-Bold')

    # Encabezado
    story.append(Paragraph("VERSION PREVIA — DRAFT", bold_style))
    story.append(Paragraph("ANÁLISIS DE CASOS DE PRUEBA QA (V8)", title_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0')))
    story.append(Spacer(1, 10))
    
    # Resumen
    test_cases = data.get("TEST_CASES", [])
    total_cp = len(test_cases)
    
    story.append(Paragraph("RESUMEN GENERAL", h2_style))
    story.append(Paragraph(f"Total de Casos de Prueba: {total_cp}", body_style))
    story.append(Spacer(1, 10))
    
    # Detalle de Casos de Prueba
    story.append(Paragraph("CASOS DE PRUEBA", h2_style))
    story.append(Spacer(1, 5))
    
    for tc in test_cases:
        story.append(Paragraph(f"<b>{tc.get('ID', '')} - {tc.get('Title', '')}</b>", bold_style))
        story.append(Paragraph(f"<b>Descripción:</b> {tc.get('Description', '')}", body_style))
        story.append(Paragraph(f"<b>Precondiciones:</b> {tc.get('Preconditions', '')}", body_style))
        story.append(Paragraph(f"<b>Requisito/CU:</b> {tc.get('Related Use Case', '')} | <b>Escenario:</b> {tc.get('Scenario', '')} ({tc.get('Scenario Type', '')})", body_style))
        story.append(Paragraph(f"<b>Effort:</b> {tc.get('Effort', '')}", body_style))
        story.append(Spacer(1, 5))
        
        # Tabla de Steps
        steps_data = [["Step #", "Action", "Expected Value"]]
        for st in tc.get("Steps", []):
            steps_data.append([
                str(st.get("Step #", "")),
                Paragraph(st.get("Action", ""), body_style),
                Paragraph(st.get("Expected value", ""), body_style)
            ])
            
        t_steps = Table(steps_data, colWidths=[40, 240, 240])
        t_steps.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EDF2F7')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#2D3748')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(t_steps)
        story.append(Spacer(1, 10))
        
        # Alertas si existen
        alerts = tc.get("Alerts", [])
        if alerts:
            story.append(Paragraph("<b>ALERTAS:</b>", bold_style))
            for a in alerts:
                story.append(Paragraph(f"- <b>{a.get('Alert')}:</b> {a.get('Reason')} (<i>Validación: {a.get('Validation Required')}</i>)", body_style))
            story.append(Spacer(1, 10))
            
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
        story.append(Spacer(1, 10))
        
    doc.build(story)
    buffer.seek(0)
    return buffer

# Botón para procesar
if st.button("Generar Casos de Prueba (V8)"):
    if not api_key:
        st.error("Por favor ingrese su Gemini API Key.")
    elif not source_text.strip():
        st.warning("Por favor ingrese texto en la fuente de información.")
    else:
        with st.spinner("Analizando requerimientos y generando estructuración QA..."):
            try:
                result_json = generate_qa_data(system_prompt, source_text, api_key, selected_model)
                
                st.success("Análisis QA V8 generado exitosamente.")
                
                excel_file = create_excel_v8(result_json)
                pdf_file = create_pdf_v8(result_json)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.download_button(
                        label="📥 Descargar Excel (Azure Import + Matriz QA)",
                        data=excel_file,
                        file_name="QA_Casos_de_Prueba_V8.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    
                with col2:
                    st.download_button(
                        label="📄 Descargar PDF Draft Report",
                        data=pdf_file,
                        file_name="QA_Reporte_Draft_V8.pdf",
                        mime="application/pdf"
                    )
                    
                st.subheader("Vista previa del JSON generado:")
                st.json(result_json)
                
            except Exception as e:
                st.error(f"Ocurrió un error al procesar la solicitud: {str(e)}")