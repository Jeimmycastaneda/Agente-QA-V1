import streamlit as st
import pandas as pd
import json
import io
import os
import logging
import time
import re
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import google.generativeai as genai

# ============================================
# CONFIGURACIÓN INICIAL
# ============================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="Agente QA V8 - Generador de Pruebas",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# ESTILOS CSS PERSONALIZADOS
# ============================================

st.markdown("""
    <style>
    .main-header {
        background: linear-gradient(135deg, #1A365D 0%, #2B6CB0 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 2rem;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #2B6CB0;
        margin-bottom: 0.5rem;
    }
    .warning-box {
        background-color: #fff3cd;
        border: 1px solid #ffc107;
        padding: 0.75rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .info-box {
        background-color: #d1ecf1;
        border: 1px solid #17a2b8;
        padding: 0.75rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border: 1px solid #28a745;
        padding: 0.75rem;
        border-radius: 5px;
        margin: 0.5rem 0;
    }
    .draft-badge {
        background-color: #ffc107;
        color: #1A365D;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
    }
    </style>
""", unsafe_allow_html=True)

# ============================================
# HEADER
# ============================================

st.markdown("""
    <div class="main-header">
        <h1>🤖 Agente QA V8 — Generador de Casos de Prueba</h1>
        <p style="margin: 0; opacity: 0.9;">
            <span class="draft-badge">VERSION PREVIA — DRAFT</span>
            &nbsp; Análisis de Historias de Usuario y generación de casos de prueba para QA
        </p>
    </div>
""", unsafe_allow_html=True)

# ============================================
# ESTADO DE SESIÓN
# ============================================

if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'result_json' not in st.session_state:
    st.session_state.result_json = None
if 'last_processed' not in st.session_state:
    st.session_state.last_processed = None
if 'source_content' not in st.session_state:
    st.session_state.source_content = ""

# ============================================
# CARGA DEL PROMPT
# ============================================

@st.cache_data(ttl=3600)
def load_system_prompt():
    """Carga el prompt del sistema desde archivo"""
    prompt_path = "prompt_qa.txt"
    if os.path.exists(prompt_path):
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                content = f.read()
                if not content.strip():
                    return get_default_prompt()
                return content
        except Exception as e:
            st.error(f"❌ Error al cargar prompt_qa.txt: {str(e)}")
            return get_default_prompt()
    else:
        st.warning("⚠️ No se encontró prompt_qa.txt. Usando prompt por defecto.")
        return get_default_prompt()

def get_default_prompt():
    """Prompt por defecto en caso de error"""
    return """Eres un agente especializado en análisis de Historias de Usuario y generación de casos de prueba para QA.
    Genera una estructura JSON con TEST_CASES, ALERTS y COVERAGE.
    Cada caso de prueba debe tener: ID, Title, Description, Preconditions, Steps, Alerts.
    Los Steps deben tener: Step #, Action, Expected value.
    """

system_prompt = load_system_prompt()

# ============================================
# SIDEBAR - CONFIGURACIÓN
# ============================================

with st.sidebar:
    st.header("⚙️ Configuración")
    
    # API Key
    api_key_from_secrets = st.secrets.get("GEMINI_API_KEY") if hasattr(st, 'secrets') else None
    
    if api_key_from_secrets:
        st.success("✅ API Key configurada desde Secrets")
        api_key = api_key_from_secrets
        show_key_input = st.checkbox("Mostrar campo de API Key", value=False)
        if show_key_input:
            api_key = st.text_input("API Key (override)", type="password", value=api_key)
    else:
        st.warning("⚠️ No se encontró GEMINI_API_KEY en Secrets")
        api_key = st.text_input(
            "Google Gemini API Key",
            type="password",
            help="Obtén tu API Key en https://makersuite.google.com/app/apikey"
        )
    
    st.divider()
    
    # Configuración del modelo
    st.subheader("🎯 Modelo")
    selected_model = st.selectbox(
        "Seleccionar modelo",
        ["gemini-1.5-pro", "gemini-1.5-flash"],
        help="Gemini 1.5 Pro: Más preciso y detallado | Flash: Más rápido"
    )
    
    temperature = st.slider(
        "🌡️ Temperatura",
        min_value=0.0,
        max_value=0.5,
        value=0.1,
        step=0.05,
        help="0.0 = Máxima fidelidad a la fuente | 0.5 = Más creativo pero menos fiel"
    )
    
    st.divider()
    
    # Información del sistema
    st.subheader("📊 Estado")
    st.info(f"""
    **Prompt**: {'✅ Cargado' if system_prompt else '❌ No cargado'}
    **Modelo**: {selected_model}
    **Temperatura**: {temperature}
    **Token limit**: 8192
    **Versión**: VERSION PREVIA — DRAFT
    """)
    
    st.divider()
    
    # Ayuda
    with st.expander("📖 Ayuda rápida"):
        st.markdown("""
        **¿Cómo usar?**
        1. Ingresa tu HU o documento
        2. Configura API Key
        3. Haz clic en "Generar"
        4. Descarga Excel y PDF
        
        **¿Qué genera?**
        - Excel: Azure Import + Matriz QA
        - PDF: Reporte DRAFT completo
        
        **Principios**: Trazabilidad + Fidelidad + No invención
        """)

# ============================================
# TABS - ENTRADA DE DATOS
# ============================================

tab1, tab2, tab3 = st.tabs(["📝 Texto Manual", "📁 Carga de Archivo", "📋 Ejemplos"])

source_text = ""

with tab1:
    source_text = st.text_area(
        "📝 Ingrese la información fuente:",
        height=350,
        value=st.session_state.source_content if st.session_state.source_content else "",
        placeholder="""Ejemplo de entrada:

HISTORIA DE USUARIO:
Como usuario registrado del sistema de Autos Colectivos
Quiero iniciar sesión en la aplicación móvil
Para acceder a mis viajes y realizar reservas

CRITERIOS DE ACEPTACIÓN:
1. El sistema debe mostrar campos para usuario y contraseña
2. Debe validar que el usuario existe en la base de datos
3. La contraseña debe ser validada con hash SHA-256
4. Tras login exitoso, mostrar dashboard principal
5. Si falla, mostrar mensaje de error "Credenciales inválidas"
        """
    )
    if source_text:
        st.session_state.source_content = source_text

with tab2:
    uploaded_file = st.file_uploader(
        "📂 Cargue un archivo",
        type=['txt', 'md', 'pdf', 'docx'],
        help="Formatos soportados: TXT, MD, PDF, DOCX"
    )
    
    if uploaded_file:
        try:
            file_extension = uploaded_file.name.split('.')[-1].lower()
            
            if file_extension in ['txt', 'md']:
                file_content = uploaded_file.read().decode('utf-8')
                source_text = file_content
                st.session_state.source_content = file_content
                st.success(f"✅ Archivo {uploaded_file.name} cargado correctamente")
                
            elif file_extension == 'pdf':
                try:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(uploaded_file)
                    file_content = ""
                    for page in pdf_reader.pages:
                        file_content += page.extract_text()
                    source_text = file_content
                    st.session_state.source_content = file_content
                    st.success(f"✅ PDF {uploaded_file.name} procesado")
                except ImportError:
                    st.error("❌ Para procesar PDFs: pip install PyPDF2")
                except Exception as e:
                    st.error(f"❌ Error al procesar PDF: {str(e)}")
                    
            elif file_extension == 'docx':
                try:
                    import docx
                    doc = docx.Document(uploaded_file)
                    file_content = ""
                    for para in doc.paragraphs:
                        file_content += para.text + "\n"
                    source_text = file_content
                    st.session_state.source_content = file_content
                    st.success(f"✅ DOCX {uploaded_file.name} procesado")
                except ImportError:
                    st.error("❌ Para procesar DOCX: pip install python-docx")
                except Exception as e:
                    st.error(f"❌ Error al procesar DOCX: {str(e)}")
            
            with st.expander("📄 Vista previa del contenido"):
                st.text_area("Contenido:", file_content[:2000], height=200, disabled=True)
                if len(file_content) > 2000:
                    st.caption(f"... y {len(file_content) - 2000} caracteres más")
                    
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo: {str(e)}")

with tab3:
    st.subheader("📋 Ejemplos de entrada")
    
    col1, col2 = st.columns(2)
    
    with col1:
        with st.expander("🔐 Ejemplo: Login", expanded=False):
            st.code("""
HISTORIA DE USUARIO:
Como usuario registrado
Quiero iniciar sesión en el sistema
Para acceder a mis datos

CRITERIOS DE ACEPTACIÓN:
1. Mostrar campos usuario y contraseña
2. Validar credenciales contra BD
3. Tras login exitoso: dashboard
4. Si falla: mensaje "Credenciales inválidas"
5. Máximo 3 intentos
            """)
            if st.button("📥 Cargar Ejemplo Login", use_container_width=True):
                st.session_state.source_content = """HISTORIA DE USUARIO:
Como usuario registrado
Quiero iniciar sesión en el sistema
Para acceder a mis datos

CRITERIOS DE ACEPTACIÓN:
1. Mostrar campos usuario y contraseña
2. Validar credenciales contra BD
3. Tras login exitoso: dashboard
4. Si falla: mensaje "Credenciales inválidas"
5. Máximo 3 intentos"""
                st.success("✅ Ejemplo cargado en la pestaña 'Texto Manual'")
                st.rerun()
    
    with col2:
        with st.expander("📝 Ejemplo: Registro", expanded=False):
            st.code("""
CASO DE USO: Registrar Usuario
ACTOR: Usuario no registrado

FLUJO PRINCIPAL:
1. Acceder a formulario de registro
2. Completar: Nombre, Email, Teléfono, Contraseña
3. Aceptar términos y condiciones
4. Presionar "Registrar"
5. Sistema valida email único
6. Sistema crea usuario estado "Pendiente"
7. Mostrar mensaje "Registro exitoso"

FLUJO ALTERNATIVO:
5a. Email ya registrado
    5a1. Mostrar "Email ya registrado"
            """)
            if st.button("📥 Cargar Ejemplo Registro", use_container_width=True):
                st.session_state.source_content = """CASO DE USO: Registrar Usuario
ACTOR: Usuario no registrado

FLUJO PRINCIPAL:
1. Acceder a formulario de registro
2. Completar: Nombre, Email, Teléfono, Contraseña
3. Aceptar términos y condiciones
4. Presionar "Registrar"
5. Sistema valida email único
6. Sistema crea usuario estado "Pendiente"
7. Mostrar mensaje "Registro exitoso"

FLUJO ALTERNATIVO:
5a. Email ya registrado
    5a1. Mostrar "Email ya registrado" """
                st.success("✅ Ejemplo cargado en la pestaña 'Texto Manual'")
                st.rerun()

# ============================================
# MÉTRICAS DE ENTRADA
# ============================================

if source_text or st.session_state.source_content:
    text_to_measure = source_text or st.session_state.source_content
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("📝 Caracteres", len(text_to_measure))
    with col2:
        st.metric("📄 Líneas", len(text_to_measure.split('\n')))
    with col3:
        st.metric("💬 Palabras", len(text_to_measure.split()))
    with col4:
        st.metric("📋 Párrafos", len([p for p in text_to_measure.split('\n\n') if p.strip()]))

# ============================================
# FUNCIONES DE PROCESAMIENTO
# ============================================

def validate_qa_structure(data):
    """Valida la estructura del JSON generado"""
    required_keys = ["TEST_CASES", "ALERTS", "COVERAGE"]
    missing_keys = [k for k in required_keys if k not in data]
    
    if missing_keys:
        raise ValueError(f"Faltan claves requeridas: {', '.join(missing_keys)}")
    
    if not isinstance(data["TEST_CASES"], list):
        raise ValueError("TEST_CASES debe ser una lista")
    
    if len(data["TEST_CASES"]) == 0:
        raise ValueError("No se generaron casos de prueba.")
    
    # Validar formato de IDs
    id_pattern = r'^CP-[A-Z]+-[0-9]{5}$'
    for tc in data["TEST_CASES"]:
        tc_id = tc.get("ID", "")
        if tc_id and not re.match(id_pattern, tc_id):
            st.warning(f"⚠️ ID '{tc_id}' no sigue el formato CP-XXXX-#####")
    
    return data

def generate_qa_data(prompt_text, source_content, key, model_name, temperature=0.1):
    """Genera datos QA con Gemini"""
    if not key:
        raise ValueError("❌ API Key no configurada")
    
    if not source_content.strip():
        raise ValueError("❌ Fuente de información vacía")
    
    try:
        genai.configure(api_key=key)
        
        # Validar modelo disponible
        available_models = [m.name for m in genai.list_models()]
        model_found = any(model_name in m for m in available_models)
        if not model_found:
            st.warning(f"⚠️ Modelo {model_name} no disponible. Usando gemini-1.5-pro")
            model_name = "gemini-1.5-pro"
        
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "response_mime_type": "application/json",
                "max_output_tokens": 8192,
                "temperature": temperature,
                "top_p": 0.95
            }
        )
        
        # Limitar tamaño de entrada
        max_source_chars = 30000
        if len(source_content) > max_source_chars:
            st.warning(f"⚠️ Contenido de {len(source_content)} caracteres. Truncado a {max_source_chars}.")
            source_content = source_content[:max_source_chars] + "\n... [Contenido truncado]"
        
        full_prompt = f"{prompt_text}\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n{source_content}"
        
        # Progreso
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        status_text.text("⏳ Iniciando análisis de requisitos...")
        progress_bar.progress(10)
        
        # Llamada a Gemini
        response = model.generate_content(full_prompt)
        
        progress_bar.progress(70)
        status_text.text("⏳ Procesando respuesta...")
        
        if not response.text:
            raise ValueError("❌ Gemini no devolvió contenido")
        
        # Parsear JSON
        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            clean_text = response.text.strip()
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', clean_text)
            if json_match:
                clean_text = json_match.group(1)
            elif re.search(r'```\s*([\s\S]*?)\s*```', clean_text):
                clean_text = re.search(r'```\s*([\s\S]*?)\s*```', clean_text).group(1)
            
            try:
                data = json.loads(clean_text)
            except json.JSONDecodeError:
                raise ValueError(f"❌ Error al parsear JSON. Respuesta: {response.text[:200]}...")
        
        # Validar estructura
        validated_data = validate_qa_structure(data)
        
        progress_bar.progress(100)
        status_text.text("✅ Procesamiento completado")
        
        time.sleep(0.5)
        progress_bar.empty()
        status_text.empty()
        
        return validated_data
        
    except Exception as e:
        logger.error(f"Error en generate_qa_data: {str(e)}")
        raise

def get_safe_text(text, default=""):
    """Obtiene texto de manera segura"""
    if text is None:
        return default
    return str(text).strip()

def get_safe_steps(tc):
    """Obtiene steps de manera segura"""
    steps = tc.get("Steps")
    if not steps:
        return []
    if not isinstance(steps, list):
        return []
    return steps

def create_excel_v8(data):
    """Crea Excel con Azure Import y Matriz QA"""
    try:
        output = io.BytesIO()
        
        # Hoja 1: Azure Import
        azure_rows = []
        for tc in data.get("TEST_CASES", []):
            tc_id = get_safe_text(tc.get("ID"))
            tc_title = get_safe_text(tc.get("Title"))
            steps = get_safe_steps(tc)
            
            if not steps:
                azure_rows.append({
                    "TestCaseId": tc_id,
                    "Title": tc_title,
                    "TestStep": 1,
                    "StepAction": "Sin steps definidos",
                    "StepExpected": "Validar con equipo funcional",
                    "TestPointId": "",
                    "Configuration": "",
                    "Tester": "",
                    "Outcome": "",
                    "Comment": ""
                })
            else:
                for idx, step in enumerate(steps):
                    step_num = step.get("Step #", idx + 1)
                    azure_rows.append({
                        "TestCaseId": tc_id,
                        "Title": tc_title,
                        "TestStep": step_num,
                        "StepAction": get_safe_text(step.get("Action")),
                        "StepExpected": get_safe_text(step.get("Expected value")),
                        "TestPointId": "",
                        "Configuration": "",
                        "Tester": "",
                        "Outcome": "",
                        "Comment": ""
                    })
        
        df_azure = pd.DataFrame(azure_rows)
        
        # Hoja 2: Matriz QA
        matriz_rows = []
        for tc in data.get("TEST_CASES", []):
            alerts_list = tc.get("Alerts", [])
            alerts_str = " | ".join([f"{a.get('Alert', '')}: {a.get('Reason', '')}" 
                                   for a in alerts_list if a.get('Alert') and a.get('Reason')]) if alerts_list else "Sin Alertas"
            
            matriz_rows.append({
                "Requirement / Use Case": get_safe_text(tc.get("Related Use Case")),
                "Criterion": get_safe_text(tc.get("Criterion")),
                "Scenario": get_safe_text(tc.get("Scenario")),
                "Test Case": get_safe_text(tc.get("ID")),
                "Validation Method": get_safe_text(tc.get("Validation Method"), "UI"),
                "Coverage": get_safe_text(tc.get("Coverage"), "Pendiente"),
                "Alerts": alerts_str
            })
        
        df_matriz = pd.DataFrame(matriz_rows)
        
        # Guardar Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_azure.to_excel(writer, sheet_name="Azure Import", index=False)
            df_matriz.to_excel(writer, sheet_name="Matriz QA", index=False)
            
            # Ajustar anchos
            for sheet_name in writer.sheets:
                worksheet = writer.sheets[sheet_name]
                for column in worksheet.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            if len(str(cell.value)) > max_length:
                                max_length = len(str(cell.value))
                        except:
                            pass
                    adjusted_width = min(max_length + 2, 50)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        return output
        
    except Exception as e:
        logger.error(f"Error en create_excel_v8: {str(e)}")
        raise

def sanitize_text_for_pdf(text):
    """Sanitiza texto para ReportLab"""
    if not text:
        return ""
    replacements = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&apos;'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def create_pdf_v8(data):
    """Crea PDF con el reporte"""
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, 
            pagesize=letter, 
            rightMargin=36, 
            leftMargin=36, 
            topMargin=36, 
            bottomMargin=36
        )
        story = []
        
        styles = getSampleStyleSheet()
        
        # Estilos personalizados
        title_style = ParagraphStyle(
            'DocTitle', 
            parent=styles['Heading1'], 
            fontSize=16, 
            leading=20, 
            textColor=colors.HexColor('#1A365D'),
            spaceAfter=12
        )
        h2_style = ParagraphStyle(
            'SectionHeader', 
            parent=styles['Heading2'], 
            fontSize=12, 
            leading=16, 
            textColor=colors.HexColor('#2B6CB0'),
            spaceBefore=12,
            spaceAfter=6
        )
        body_style = ParagraphStyle(
            'BodyText', 
            parent=styles['Normal'], 
            fontSize=9, 
            leading=12,
            spaceAfter=3
        )
        bold_style = ParagraphStyle(
            'BoldText', 
            parent=body_style, 
            fontName='Helvetica-Bold'
        )
        small_style = ParagraphStyle(
            'SmallText', 
            parent=body_style, 
            fontSize=7, 
            textColor=colors.HexColor('#718096')
        )
        
        # Portada
        story.append(Paragraph("VERSION PREVIA — DRAFT", small_style))
        story.append(Spacer(1, 20))
        story.append(Paragraph("ANÁLISIS DE CASOS DE PRUEBA QA", title_style))
        story.append(Spacer(1, 5))
        story.append(Paragraph(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}", small_style))
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0')))
        story.append(Spacer(1, 20))
        
        # Resumen
        test_cases = data.get("TEST_CASES", [])
        total_cp = len(test_cases)
        total_alerts = len(data.get("ALERTS", []))
        
        story.append(Paragraph("RESUMEN GENERAL", h2_style))
        story.append(Paragraph(f"Total de Casos de Prueba: {total_cp}", body_style))
        story.append(Paragraph(f"Total de Alertas Generadas: {total_alerts}", body_style))
        
        # Distribución de escenarios
        scenario_types = {}
        for tc in test_cases:
            stype = tc.get("Scenario Type", "No definido")
            scenario_types[stype] = scenario_types.get(stype, 0) + 1
        
        if scenario_types:
            story.append(Spacer(1, 5))
            story.append(Paragraph("Distribución de Escenarios:", body_style))
            for stype, count in scenario_types.items():
                story.append(Paragraph(f"• {stype}: {count} casos", body_style))
        
        story.append(Spacer(1, 10))
        
        # Alertas Generales
        alerts = data.get("ALERTS", [])
        if alerts:
            story.append(Paragraph("ALERTAS GENERALES", h2_style))
            for alert in alerts:
                alert_text = sanitize_text_for_pdf(alert.get("Alert", ""))
                reason_text = sanitize_text_for_pdf(alert.get("Reason", ""))
                validation_text = sanitize_text_for_pdf(alert.get("Validation Required", ""))
                story.append(Paragraph(f"• <b>{alert_text}</b>: {reason_text}", body_style))
                if validation_text:
                    story.append(Paragraph(f"  <i>Validación: {validation_text}</i>", body_style))
            story.append(Spacer(1, 10))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
            story.append(Spacer(1, 10))
        
        # Casos de Prueba
        story.append(Paragraph("CASOS DE PRUEBA", h2_style))
        story.append(Spacer(1, 5))
        
        for idx, tc in enumerate(test_cases):
            # ID y Título
            tc_id = sanitize_text_for_pdf(tc.get('ID', f'CP-{idx+1:05d}'))
            tc_title = sanitize_text_for_pdf(tc.get('Title', 'Sin título'))
            story.append(Paragraph(f"<b>{tc_id}</b>", bold_style))
            story.append(Paragraph(f"<b>{tc_title}</b>", body_style))
            
            # Descripción
            desc = sanitize_text_for_pdf(tc.get('Description', 'Sin descripción'))
            if desc:
                story.append(Paragraph(f"<b>Descripción:</b> {desc}", body_style))
            
            # Precondiciones
            preconditions = sanitize_text_for_pdf(tc.get('Preconditions', 'No definidas'))
            story.append(Paragraph(f"<b>Precondiciones:</b> {preconditions}", body_style))
            
            # Metadatos
            related_uc = sanitize_text_for_pdf(tc.get('Related Use Case', 'No definido'))
            scenario = sanitize_text_for_pdf(tc.get('Scenario', 'No definido'))
            scenario_type = sanitize_text_for_pdf(tc.get('Scenario Type', 'No definido'))
            effort = sanitize_text_for_pdf(tc.get('Effort', 'No definido'))
            
            story.append(Paragraph(
                f"<b>Requisito:</b> {related_uc} | <b>Escenario:</b> {scenario} ({scenario_type}) | <b>Effort:</b> {effort}",
                body_style
            ))
            story.append(Spacer(1, 5))
            
            # Tabla de Steps
            steps = get_safe_steps(tc)
            if steps:
                steps_data = [["Step #", "Action", "Expected Value"]]
                for step in steps:
                    action = sanitize_text_for_pdf(step.get("Action", "No definida"))
                    expected = sanitize_text_for_pdf(step.get("Expected value", "No definido"))
                    step_num = step.get("Step #", len(steps_data))
                    steps_data.append([str(step_num), action, expected])
                
                t_steps = Table(steps_data, colWidths=[40, 220, 260])
                t_steps.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EDF2F7')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#2D3748')),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0,0), (-1,-1), 8),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                    ('VALIGN', (0,0), (-1,-1), 'TOP'),
                    ('PADDING', (0,0), (-1,-1), 4),
                ]))
                story.append(t_steps)
            else:
                story.append(Paragraph("<i>No se definieron steps para este caso</i>", body_style))
            
            story.append(Spacer(1, 5))
            
            # Alertas del caso
            case_alerts = tc.get("Alerts", [])
            if case_alerts:
                story.append(Paragraph("<b>ALERTAS:</b>", bold_style))
                for alert in case_alerts:
                    alert_text = sanitize_text_for_pdf(alert.get('Alert', ''))
                    reason = sanitize_text_for_pdf(alert.get('Reason', ''))
                    validation = sanitize_text_for_pdf(alert.get('Validation Required', ''))
                    story.append(Paragraph(
                        f"• <b>{alert_text}</b>: {reason}" + (f" <i>({validation})</i>" if validation else ""),
                        body_style
                    ))
                story.append(Spacer(1, 5))
            
            # Separador
            if idx < len(test_cases) - 1:
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
                story.append(Spacer(1, 5))
        
        # Pie de página
        story.append(Spacer(1, 20))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#CBD5E0')))
        story.append(Paragraph(
            f"VERSION PREVIA — DRAFT - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            small_style
        ))
        story.append(Paragraph("Documento generado automáticamente. Requiere revisión y validación por equipo funcional.", small_style))
        
        doc.build(story)
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        logger.error(f"Error en create_pdf_v8: {str(e)}")
        raise

# ============================================
# BOTÓN DE PROCESAMIENTO
# ============================================

col1, col2, col3 = st.columns([2, 1.5, 2])
with col2:
    process_button = st.button(
        "🚀 Generar Casos de Prueba",
        type="primary",
        use_container_width=True,
        disabled=st.session_state.processing,
        help="Inicia el análisis de la fuente y genera casos de prueba"
    )

# ============================================
# PROCESAR
# ============================================

if process_button:
    text_to_process = source_text or st.session_state.source_content
    
    if not api_key:
        st.error("❌ Por favor ingrese su Gemini API Key o configúrela en Secrets.")
    elif not text_to_process.strip():
        st.warning("⚠️ Por favor ingrese texto en la fuente de información o cargue un archivo.")
    else:
        st.session_state.processing = True
        
        progress_container = st.container()
        
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
        
        try:
            status_text.text("⏳ Iniciando análisis de requisitos...")
            progress_bar.progress(10)
            
            # Generar casos
            result_json = generate_qa_data(
                system_prompt, 
                text_to_process, 
                api_key, 
                selected_model,
                temperature
            )
            
            progress_bar.progress(50)
            status_text.text("⏳ Generando archivos Excel y PDF...")
            
            # Generar archivos
            excel_file = create_excel_v8(result_json)
            progress_bar.progress(70)
            
            pdf_file = create_pdf_v8(result_json)
            progress_bar.progress(90)
            
            # Guardar en sesión
            st.session_state.result_json = result_json
            st.session_state.last_processed = datetime.now()
            
            progress_bar.progress(100)
            status_text.text("✅ Procesamiento completado exitosamente!")
            
            # Mostrar resultados
            st.success("✅ Análisis QA generado exitosamente.")
            
            # Métricas
            test_cases = result_json.get("TEST_CASES", [])
            total_steps = sum(len(get_safe_steps(tc)) for tc in test_cases)
            total_alerts = len(result_json.get("ALERTS", []))
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📋 Casos", len(test_cases))
            with col2:
                st.metric("📝 Steps", total_steps)
            with col3:
                st.metric("⚠️ Alertas", total_alerts)
            with col4:
                st.metric("⏱️ Tiempo", f"{datetime.now() - st.session_state.last_processed if st.session_state.last_processed else 'N/A'}")
            
            # Resumen rápido
            with st.expander("📊 Resumen de escenarios", expanded=False):
                scenario_types = {}
                for tc in test_cases:
                    stype = tc.get("Scenario Type", "No definido")
                    scenario_types[stype] = scenario_types.get(stype, 0) + 1
                
                for stype, count in scenario_types.items():
                    st.write(f"**{stype}**: {count} casos")
            
            # Botones de descarga
            col1, col2 = st.columns(2)
            
            with col1:
                st.download_button(
                    label="📥 Descargar Excel (Azure Import + Matriz QA)",
                    data=excel_file,
                    file_name=f"QA_Casos_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                
            with col2:
                st.download_button(
                    label="📄 Descargar PDF Draft Report",
                    data=pdf_file,
                    file_name=f"QA_Reporte_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            
            # Vista previa JSON
            with st.expander("🔍 Ver JSON generado"):
                st.json(result_json)
            
            # Limpiar progreso
            time.sleep(2)
            progress_bar.empty()
            status_text.empty()
            
        except Exception as e:
            st.error(f"❌ Error al procesar: {str(e)}")
            logger.error(f"Error: {str(e)}")
            
            st.info("""
            💡 **Posibles soluciones:**
            1. Verifica que tu API Key sea válida
            2. Asegúrate de que la fuente tenga información suficiente
            3. Prueba con un modelo diferente (Pro vs Flash)
            4. Reduce la longitud del texto de entrada
            5. Revisa que prompt_qa.txt exista
            """)
            
        finally:
            st.session_state.processing = False

# ============================================
# FOOTER
# ============================================

st.divider()
st.caption("""
**Agente QA V8** — VERSION PREVIA — DRAFT | 
Desarrollado con Streamlit y Google Gemini | 
Principios: Trazabilidad + Fidelidad + No Invención
""")