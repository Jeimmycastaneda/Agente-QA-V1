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

# ============================================
# IMPORTACIÓN CORRECTA DE GEMINI
# ============================================
from google import genai
from google.genai import types

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
    .draft-badge {
        background-color: #ffc107;
        color: #1A365D;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-weight: bold;
        font-size: 0.8rem;
        display: inline-block;
    }
    .upload-section {
        background-color: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        border: 2px dashed #2B6CB0;
        text-align: center;
    }
    .model-badge {
        background-color: #28a745;
        color: white;
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
            &nbsp; Análisis de documentos y generación de casos de prueba para QA
            <span class="model-badge" style="margin-left: 10px;">Gemini 3.6 Flash</span>
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
if 'valid_models' not in st.session_state:
    st.session_state.valid_models = []
if 'quota_exceeded' not in st.session_state:
    st.session_state.quota_exceeded = False
if 'retry_count' not in st.session_state:
    st.session_state.retry_count = 0

# ============================================
# MODELO GEMINI 3.6 FLASH (PREDETERMINADO)
# ============================================

# Modelo por defecto según especificación
MODEL = "gemini-3.6-flash"

# Modelos alternativos (fallback)
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-2.5-flash", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-1.5-pro"]

# ============================================
# ESQUEMA JSON PARA LA RESPUESTA - NO CAMBIAR
# ============================================

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
                    "Criterion": {"type": "string"},
                    "Scenario": {"type": "string"},
                    "Scenario Type": {"type": "string"},
                    "Effort": {"type": "string"},
                    "Steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Step #": {"type": "integer"},
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
                "required": ["ID", "Title", "Description", "Preconditions", "Steps"]
            }
        },
        "ALERTS": {
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
                "required": ["Requirement / Use Case", "Criterion", "Scenario", "Test Case"]
            }
        }
    },
    "required": ["TEST_CASES", "ALERTS", "COVERAGE"]
}

# ============================================
# CARGA DEL PROMPT V8 - NO CAMBIAR
# ============================================

@st.cache_data(ttl=3600)
def load_system_prompt():
    """Carga el prompt V8 desde archivo - NO CAMBIAR"""
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
    """Prompt por defecto en caso de error - NO CAMBIAR"""
    return """Eres un agente especializado en análisis de Historias de Usuario y generación de casos de prueba para QA.
    Genera una estructura JSON con TEST_CASES, ALERTS y COVERAGE.
    Cada caso de prueba debe tener: ID, Title, Description, Preconditions, Steps, Alerts.
    Los Steps deben tener: Step #, Action, Expected value.
    """

# PROMPT V8 - NO CAMBIAR
system_prompt = load_system_prompt()

# ============================================
# FUNCIÓN PARA OBTENER MODELOS VÁLIDOS
# ============================================

@st.cache_data(ttl=3600)
def get_valid_models(api_key):
    """Obtiene los modelos Gemini disponibles"""
    try:
        client = genai.Client(api_key=api_key)
        models = client.models.list()
        
        valid_models = []
        for model in models:
            model_name = model.name.split('/')[-1]
            if 'gemini' in model_name.lower():
                if '2.0' not in model_name.lower():
                    valid_models.append(model_name)
        
        if MODEL not in valid_models:
            valid_models.insert(0, MODEL)
        
        if not valid_models:
            valid_models = FALLBACK_MODELS.copy()
        
        return sorted(set(valid_models))
        
    except Exception as e:
        st.warning(f"⚠️ No se pudieron listar los modelos: {str(e)}")
        return FALLBACK_MODELS.copy()

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
    else:
        st.warning("⚠️ No se encontró GEMINI_API_KEY en Secrets")
        api_key = st.text_input(
            "🔑 Google Gemini API Key",
            type="password",
            help="Obtén tu API Key en https://makersuite.google.com/app/apikey"
        )
    
    if api_key:
        try:
            valid_models = get_valid_models(api_key)
            st.session_state.valid_models = valid_models
        except Exception as e:
            valid_models = FALLBACK_MODELS.copy()
            st.session_state.valid_models = valid_models
    else:
        valid_models = FALLBACK_MODELS.copy()
        st.session_state.valid_models = valid_models
    
    st.divider()
    
    # Configuración del modelo
    st.subheader("🎯 Modelo")
    
    if MODEL in valid_models:
        default_index = valid_models.index(MODEL)
    else:
        default_index = 0
    
    selected_model = st.selectbox(
        "Seleccionar modelo",
        options=valid_models,
        index=default_index if MODEL in valid_models else 0,
        help="Modelos Gemini disponibles. Se recomienda Gemini 3.6 Flash"
    )
    
    if selected_model == MODEL:
        st.success("✅ Modelo recomendado: Gemini 3.6 Flash")
    else:
        st.info(f"ℹ️ Modelo seleccionado: {selected_model}")
    
    # Opciones avanzadas
    with st.expander("⚙️ Opciones avanzadas"):
        temperature = st.slider(
            "🌡️ Temperatura",
            min_value=0.0,
            max_value=0.5,
            value=0.1,
            step=0.05,
            help="0.0 = Máxima fidelidad | 0.5 = Más creativo"
        )
        
        max_retries = st.number_input(
            "🔄 Máximo de reintentos",
            min_value=1,
            max_value=5,
            value=3,
            help="Número de reintentos si hay límite de cuota"
        )
        
        wait_time = st.number_input(
            "⏱️ Espera inicial (segundos)",
            min_value=5,
            max_value=60,
            value=10,
            help="Tiempo de espera inicial entre reintentos"
        )
    
    st.divider()
    
    # Información del sistema
    st.subheader("📊 Estado")
    st.info(f"""
    **Prompt V8**: {'✅ Cargado' if system_prompt else '❌ No cargado'}
    **Modelo**: {selected_model}
    **Temperatura**: {temperature}
    **Reintentos**: {max_retries}
    **Max tokens**: 65536
    **Modelos disponibles**: {len(valid_models)}
    """)
    
    if st.session_state.quota_exceeded:
        st.warning("⚠️ Cuota excedida. Espera unos minutos y reintenta.")
    
    if st.session_state.retry_count > 0:
        st.info(f"🔄 Reintentos: {st.session_state.retry_count}")

# ============================================
# SECCIÓN PRINCIPAL - CARGA DE ARCHIVOS
# ============================================

st.subheader("📁 Carga de Documento")

st.markdown("""
<div class="upload-section">
    <p style="font-size: 1.2rem; margin-bottom: 1rem;">
        📄 Arrastra o selecciona un archivo con la información fuente
    </p>
    <p style="color: #6c757d; font-size: 0.9rem;">
        Formatos soportados: <strong>TXT, MD, PDF, DOCX</strong>
    </p>
</div>
""", unsafe_allow_html=True)

uploaded_file = st.file_uploader(
    "Selecciona un archivo",
    type=['txt', 'md', 'pdf', 'docx'],
    label_visibility="collapsed"
)

source_text = ""

if uploaded_file:
    try:
        file_extension = uploaded_file.name.split('.')[-1].lower()
        
        with st.spinner(f"⏳ Procesando {uploaded_file.name}..."):
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
        
        with st.expander("📄 Vista previa del contenido", expanded=True):
            st.text_area(
                "Contenido del archivo:",
                file_content[:3000],
                height=200,
                disabled=True
            )
            if len(file_content) > 3000:
                st.caption(f"... y {len(file_content) - 3000} caracteres más")
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📝 Caracteres", len(file_content))
            with col2:
                st.metric("📄 Líneas", len(file_content.split('\n')))
            with col3:
                st.metric("💬 Palabras", len(file_content.split()))
        
    except Exception as e:
        st.error(f"❌ Error al procesar el archivo: {str(e)}")

if not uploaded_file and not st.session_state.source_content:
    st.info("💡 También puedes ingresar texto manualmente en el área inferior")
    source_text = st.text_area(
        "✏️ O ingresa el texto manualmente:",
        height=200,
        placeholder="Pega aquí tu Historia de Usuario, casos de uso o documentación..."
    )
    if source_text:
        st.session_state.source_content = source_text
elif not uploaded_file and st.session_state.source_content:
    source_text = st.session_state.source_content

# ============================================
# FUNCIÓN PRINCIPAL CON GEMINI 3.6 FLASH
# ============================================

def generate_qa_data_with_gemini(prompt_text, source_content, key, model_name, temperature=0.1, max_retries=3, initial_wait=10):
    """
    Genera datos QA usando Gemini 3.6 Flash
    NO CAMBIAR - Mantiene prompt V8, SCHEMA y estructura
    """
    
    if not key:
        raise ValueError("❌ API Key no configurada")
    
    if not source_content.strip():
        raise ValueError("❌ Fuente de información vacía")
    
    # ============================================
    # CONFIGURACIÓN DEL CLIENTE GEMINI
    # ============================================
    
    client = genai.Client(api_key=key)
    
    # Limitar tamaño de entrada
    max_source_chars = 30000
    if len(source_content) > max_source_chars:
        st.warning(f"⚠️ Contenido de {len(source_content)} caracteres. Truncado a {max_source_chars}.")
        source_content = source_content[:max_source_chars] + "\n... [Contenido truncado]"
    
    # Preparar el prompt completo (Prompt V8 - NO CAMBIAR)
    full_prompt = f"{prompt_text}\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n{source_content}"
    
    # Progreso
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Intentar con reintentos
    last_error = None
    wait_time = initial_wait
    
    for attempt in range(max_retries + 1):
        try:
            status_text.text(f"⏳ Intento {attempt + 1} de {max_retries + 1} con {model_name}...")
            progress_bar.progress(10 + (attempt * 20))
            
            # ============================================
            # LLAMADA A GEMINI CON LA CONFIGURACIÓN ESPECIFICADA
            # ============================================
            
            r = client.models.generate_content(
                model=model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SCHEMA,      # SCHEMA - NO CAMBIAR
                    max_output_tokens=65536      # 65536 tokens para respuestas largas
                )
            )
            
            progress_bar.progress(70)
            status_text.text("⏳ Procesando respuesta...")
            
            # Obtener el texto de la respuesta
            text = r.text.strip()
            
            # Intentar parsear el JSON
            try:
                data = json.loads(text)
            except json.JSONDecodeError as e:
                # Intentar limpiar la respuesta
                clean_text = text
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', clean_text)
                if json_match:
                    clean_text = json_match.group(1)
                elif re.search(r'```\s*([\s\S]*?)\s*```', clean_text):
                    clean_text = re.search(r'```\s*([\s\S]*?)\s*```', clean_text).group(1)
                
                try:
                    data = json.loads(clean_text)
                except json.JSONDecodeError:
                    # Lanzar error detallado
                    raise RuntimeError(
                        f"✖ Error al parsear JSON. Detalle: {e}. "
                        f"Respuesta: {text[:3000]}"
                    )
            
            # Validar estructura
            validated_data = validate_qa_structure(data)
            
            # Éxito - resetear contadores
            st.session_state.quota_exceeded = False
            st.session_state.retry_count = 0
            
            progress_bar.progress(100)
            status_text.text(f"✅ Procesamiento completado con {model_name}")
            
            time.sleep(0.5)
            progress_bar.empty()
            status_text.empty()
            
            return validated_data
            
        except Exception as e:
            last_error = e
            error_str = str(e)
            
            # Verificar si es error de cuota (429)
            if '429' in error_str or 'quota' in error_str.lower() or 'rate limit' in error_str.lower():
                st.session_state.quota_exceeded = True
                st.session_state.retry_count = attempt + 1
                
                if attempt < max_retries:
                    retry_time = wait_time * (attempt + 1)
                    try:
                        time_match = re.search(r'retry in (\d+\.?\d*)s', error_str)
                        if time_match:
                            retry_time = float(time_match.group(1)) + 5
                    except:
                        pass
                    
                    status_text.text(f"⏳ Cuota excedida. Esperando {retry_time:.0f} segundos...")
                    progress_bar.progress(20 + (attempt * 15))
                    
                    st.warning(f"⚠️ Cuota excedida. Reintentando en {retry_time:.0f} segundos... (Intento {attempt + 1} de {max_retries + 1})")
                    
                    for i in range(int(retry_time)):
                        time.sleep(1)
                        progress_bar.progress(25 + (attempt * 15) + (i / retry_time * 20))
                    
                    continue
                else:
                    st.error("❌ Se agotaron los reintentos. La cuota de Gemini sigue excedida.")
                    raise ValueError("Cuota de Gemini excedida. Por favor espera unos minutos y reintenta.")
            else:
                raise
        
        finally:
            if attempt == max_retries and last_error:
                progress_bar.empty()
                status_text.empty()
    
    raise last_error if last_error else ValueError("Error desconocido al procesar")

# ============================================
# FUNCIÓN DE VALIDACIÓN
# ============================================

def validate_qa_structure(data):
    """Valida la estructura del JSON generado - NO CAMBIAR"""
    required_keys = ["TEST_CASES", "ALERTS", "COVERAGE"]
    missing_keys = [k for k in required_keys if k not in data]
    
    if missing_keys:
        raise ValueError(f"Faltan claves requeridas: {', '.join(missing_keys)}")
    
    if not isinstance(data["TEST_CASES"], list):
        raise ValueError("TEST_CASES debe ser una lista")
    
    if len(data["TEST_CASES"]) == 0:
        raise ValueError("No se generaron casos de prueba.")
    
    return data

# ============================================
# FUNCIÓN PARA GENERAR EXCEL CON ESTRUCTURA ESPECÍFICA
# ============================================

def create_excel_v8(data):
    """
    Crea Excel con la estructura exacta para Azure Import
    Basado en el ejemplo: OTE_Siniestros Fasecolda_-- All --_-- All --.xlsx
    """
    try:
        output = io.BytesIO()
        
        # ============================================
        # HOJA 1: AZURE IMPORT - ESTRUCTURA EXACTA
        # ============================================
        # Columnas según el ejemplo:
        # TestCaseId | Title | TestStep | StepAction | StepExpected | TestPointId | Configuration | Tester | Outcome | Comment
        # ============================================
        
        azure_rows = []
        
        # Generar un ID numérico secuencial para TestCaseId
        # Empezando desde 28454 como en el ejemplo
        base_id = 28454
        
        for idx, tc in enumerate(data.get("TEST_CASES", [])):
            # Extraer el ID del caso (ej: CP-ACSF-00001)
            case_id = get_safe_text(tc.get("ID", f"CP-ACSF-{idx+1:05d}"))
            case_title = get_safe_text(tc.get("Title", f"{case_id} Sin título"))
            steps = get_safe_steps(tc)
            
            # Asignar TestCaseId numérico
            test_case_id = base_id + idx
            
            if not steps:
                # Si no hay steps, crear una fila con mensaje
                azure_rows.append({
                    "TestCaseId": test_case_id,
                    "Title": case_title,
                    "TestStep": "",
                    "StepAction": "Sin steps definidos",
                    "StepExpected": "Validar con equipo funcional",
                    "TestPointId": "",
                    "Configuration": "Default configuration created @ 26/05/2023 15:22:17",
                    "Tester": "",
                    "Outcome": "",
                    "Comment": ""
                })
            else:
                # Crear una fila por cada step
                for step_idx, step in enumerate(steps):
                    step_num = step.get("Step #", step_idx + 1)
                    azure_rows.append({
                        "TestCaseId": test_case_id,
                        "Title": case_title,
                        "TestStep": step_num,
                        "StepAction": get_safe_text(step.get("Action", "")),
                        "StepExpected": get_safe_text(step.get("Expected value", "")),
                        "TestPointId": "",
                        "Configuration": "Default configuration created @ 26/05/2023 15:22:17",
                        "Tester": "",
                        "Outcome": "",
                        "Comment": ""
                    })
        
        df_azure = pd.DataFrame(azure_rows)
        
        # ============================================
        # HOJA 2: MATRIZ QA
        # ============================================
        
        matriz_rows = []
        for tc in data.get("TEST_CASES", []):
            alerts_list = tc.get("Alerts", [])
            alerts_str = " | ".join([f"{a.get('Alert', '')}: {a.get('Reason', '')}" 
                                   for a in alerts_list if a.get('Alert') and a.get('Reason')]) if alerts_list else "Sin Alertas"
            
            matriz_rows.append({
                "Requirement / Use Case": get_safe_text(tc.get("Related Use Case", "")),
                "Criterion": get_safe_text(tc.get("Criterion", "")),
                "Scenario": get_safe_text(tc.get("Scenario", "")),
                "Test Case": get_safe_text(tc.get("ID", "")),
                "Validation Method": get_safe_text(tc.get("Validation Method", "UI")),
                "Coverage": get_safe_text(tc.get("Coverage", "Pendiente")),
                "Alerts": alerts_str
            })
        
        df_matriz = pd.DataFrame(matriz_rows)
        
        # ============================================
        # GUARDAR EXCEL CON AMBAS HOJAS
        # ============================================
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_azure.to_excel(writer, sheet_name="28443;Fase 3 - RENK170 Siniestr", index=False)
            df_matriz.to_excel(writer, sheet_name="Matriz QA", index=False)
            
            # Ajustar anchos de columnas
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
                    adjusted_width = min(max_length + 2, 60)
                    worksheet.column_dimensions[column_letter].width = adjusted_width
        
        output.seek(0)
        return output
        
    except Exception as e:
        logger.error(f"Error en create_excel_v8: {str(e)}")
        raise

# ============================================
# FUNCIONES AUXILIARES
# ============================================

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

# ============================================
# FUNCIÓN PARA GENERAR PDF - NO CAMBIAR
# ============================================

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
    """Crea PDF con el reporte - NO CAMBIAR"""
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
        
        test_cases = data.get("TEST_CASES", [])
        total_cp = len(test_cases)
        total_alerts = len(data.get("ALERTS", []))
        
        story.append(Paragraph("RESUMEN GENERAL", h2_style))
        story.append(Paragraph(f"Total de Casos de Prueba: {total_cp}", body_style))
        story.append(Paragraph(f"Total de Alertas Generadas: {total_alerts}", body_style))
        
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
        
        story.append(Paragraph("CASOS DE PRUEBA", h2_style))
        story.append(Spacer(1, 5))
        
        for idx, tc in enumerate(test_cases):
            tc_id = sanitize_text_for_pdf(tc.get('ID', f'CP-{idx+1:05d}'))
            tc_title = sanitize_text_for_pdf(tc.get('Title', 'Sin título'))
            story.append(Paragraph(f"<b>{tc_id}</b>", bold_style))
            story.append(Paragraph(f"<b>{tc_title}</b>", body_style))
            
            desc = sanitize_text_for_pdf(tc.get('Description', 'Sin descripción'))
            if desc:
                story.append(Paragraph(f"<b>Descripción:</b> {desc}", body_style))
            
            preconditions = sanitize_text_for_pdf(tc.get('Preconditions', 'No definidas'))
            story.append(Paragraph(f"<b>Precondiciones:</b> {preconditions}", body_style))
            
            related_uc = sanitize_text_for_pdf(tc.get('Related Use Case', 'No definido'))
            scenario = sanitize_text_for_pdf(tc.get('Scenario', 'No definido'))
            scenario_type = sanitize_text_for_pdf(tc.get('Scenario Type', 'No definido'))
            effort = sanitize_text_for_pdf(tc.get('Effort', 'No definido'))
            
            story.append(Paragraph(
                f"<b>Requisito:</b> {related_uc} | <b>Escenario:</b> {scenario} ({scenario_type}) | <b>Effort:</b> {effort}",
                body_style
            ))
            story.append(Spacer(1, 5))
            
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
            
            if idx < len(test_cases) - 1:
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#E2E8F0')))
                story.append(Spacer(1, 5))
        
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
        help="Inicia el análisis del documento y genera casos de prueba"
    )

# ============================================
# PROCESAR
# ============================================

if process_button:
    text_to_process = source_text or st.session_state.source_content
    
    if not api_key:
        st.error("❌ Por favor ingrese su Gemini API Key o configúrela en Secrets.")
    elif not text_to_process.strip():
        st.warning("⚠️ Por favor cargue un archivo o ingrese texto para analizar.")
    else:
        st.session_state.processing = True
        
        try:
            result_json = generate_qa_data_with_gemini(
                system_prompt,
                text_to_process,
                api_key,
                selected_model,
                temperature,
                max_retries,
                wait_time
            )
            
            # Éxito - mostrar resultados
            st.success("✅ Análisis QA generado exitosamente con Gemini 3.6 Flash")
            
            # Generar archivos
            with st.spinner("⏳ Generando archivos Excel y PDF..."):
                excel_file = create_excel_v8(result_json)
                pdf_file = create_pdf_v8(result_json)
            
            # Guardar en sesión
            st.session_state.result_json = result_json
            st.session_state.last_processed = datetime.now()
            
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
            
            with st.expander("🔍 Ver JSON generado"):
                st.json(result_json)
            
        except Exception as e:
            st.error(f"❌ Error al procesar: {str(e)}")
            logger.error(f"Error: {str(e)}")
            
            st.info("""
            💡 **Posibles soluciones:**
            1. Espera unos minutos y vuelve a intentar (cuota de Gemini)
            2. Cambia a un modelo diferente en la barra lateral
            3. Reduce el tamaño del documento
            4. Verifica que tu API Key sea válida
            5. Modelo recomendado: gemini-3.6-flash
            """)
            
        finally:
            st.session_state.processing = False

# ============================================
# FOOTER
# ============================================

st.divider()
st.caption("""
**Agente QA V8** — VERSION PREVIA — DRAFT | 
Desarrollado con Streamlit y Google Gemini 3.6 Flash | 
Principios: Trazabilidad + Fidelidad + No Invención
""")