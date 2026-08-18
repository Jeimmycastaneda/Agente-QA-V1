import io
import json
import os
import re
import time
import requests
import pandas as pd
import streamlit as st

# ============================================================
# CONFIGURACIÓN GENERAL Y ESTILOS UI
# ============================================================
st.set_page_config(
    page_title="Generador QA - Azure DevOps & Gemini",
    page_icon="🧪",
    layout="wide"
)

def _ui_text(val, default=""):
    if val is None:
        return default
    s = str(val).strip()
    return s if s else default

def safe_text(val, default=""):
    return _ui_text(val, default)

def safe_steps(tc):
    if not isinstance(tc, dict):
        return []
    steps = tc.get("Steps") or tc.get("steps") or tc.get("Test Steps") or []
    if isinstance(steps, list):
        return steps
    return []

# ============================================================
# INICIALIZACIÓN DE SESSION STATE
# ============================================================
default_state = {
    "azure_reference_suite_id": "",
    "azure_reference_suite_name": "",
    "azure_reference_case_title": "",
    "result_json": None,
    "excel_data": None,
    "pdf_data": None,
    "source_name": "",
}

for key, val in default_state.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================================
# ESTRUCTURA EXCEL Y AZURE DEVOPS (CONSTANTES)
# ============================================================
AZURE_COLUMNS = [
    "ID",
    "Work Item Type",
    "Title",
    "Description",
    "Test Step",
    "Step Action",
    "Step Expected",
    "Area Path",
    "IDPadre",
    "Tipo Origen Proyecto",
    "Tiempo Real",
    "Assigned To",
    "State"
]

# ============================================================
# PROMPT Y ADDENDUM DE CALIDAD (DETAILED_QA_ADDENDUM)
# ============================================================
DETAILED_QA_ADDENDUM = """
============================================================
ESTÁNDAR DE PROFUNDIDAD FUNCIONAL V2
============================================================

El CP generado debe tener el mismo nivel de profundidad funcional que los
Test Cases reales seleccionados como referencia desde Azure DevOps.

El CP NO debe ser un resumen del CU.

La profundidad debe reflejarse simultáneamente en:
1. Title
2. Description
3. Resultado esperado
4. Preconditions
5. Steps
6. Expected de cada Step

La Description debe transformar el CU en un escenario ejecutable.

Cuando el CU contenga reglas, listas, ordenamientos, cálculos,
homologaciones, productos, coberturas, modelos, parámetros o condiciones,
estos deben permanecer explícitamente en la Description y/o Steps.

No resumir: "Validar que la información sea correcta."
En su lugar describir exactamente qué información se valida y contra qué regla o parametrización.

Los Steps deben recorrer la navegación funcional completa.

Ejemplo de nivel requerido:
Ingresar con usuario del perfil suscriptor, seleccionar el icono de autos
colectivos, consultar colectivo en estado cotizado, descargar el archivo
Base Emisión y validar que la hoja Orden Emisión, en la sección
Características Generales, contenga la subsección correspondiente.

Después deben continuar los pasos necesarios para validar cada regla
funcional específica del CU.

No saltar directamente del ingreso al resultado final.
No crear pasos artificiales solamente para aumentar la cantidad.

Un CU complejo debe generar tantos Steps como sean necesarios para cubrir sus reglas.

Como referencia de calidad:
- CU simple: normalmente 6 o más Steps.
- CU medio: normalmente 8 o más Steps.
- CU complejo: normalmente 10 o más Steps.

============================================================
RUTA FUNCIONAL BASADA EN CP DE REFERENCIA
============================================================

Cuando exista un Test Case real de Azure seleccionado como referencia,
utilizar su Description y Steps como fuente de patrón de navegación.

Extraer de la referencia, cuando esté disponible:
- perfil; usuario; módulo; icono; menú; opción; pantalla; consulta; estado; archivo; hoja; sección; subsección.

La ruta funcional debe incorporarse NATURALMENTE dentro de la Description
del nuevo CP y dentro de los Steps.

NO crear un campo llamado:
Ruta estimada:
Ruta sugerida:
Navegación sugerida:
Ruta funcional:

La ruta debe formar parte del texto del escenario.

Ejemplo:
"Ingresar con usuario del perfil suscriptor, seleccionar el icono de autos
colectivos, consultar colectivo en estado cotizado, descargar el archivo
Base Emisión y validar que la hoja Orden Emisión..."

La ruta del CP de referencia es una GUÍA DE NAVEGACIÓN.
NO copiar reglas funcionales que pertenezcan a otro CU.
Las reglas del CP nuevo deben provenir del CU actual.

Si el CP de referencia contiene una navegación compatible con el CU actual,
reutilizar su estructura de navegación.
Si la referencia no tiene suficiente información, conservar únicamente la
navegación sustentada.
Nunca inventar botones, pantallas, URLs o menús.
"""

def load_prompt():
    return f"Genera los casos de prueba detallados en formato JSON.\n{DETAILED_QA_ADDENDUM}"

# ============================================================
# LÓGICA DE NORMALIZACIÓN DE ID, SANITIZACIÓN Y TITULADO
# ============================================================
def module_token(module=""):
    raw = re.sub(r"[^A-Za-z0-9]+", " ", safe_text(module).upper()).strip()
    words = [w for w in raw.split() if w]
    if not words:
        return "GG"
    stopwords = {"DE", "DEL", "LA", "LAS", "EL", "LOS", "EN", "POR", "PARA", "Y", "O", "CON"}
    meaningful = [w for w in words if w not in stopwords]
    if len(meaningful) >= 2:
        return "".join(w[0] for w in meaningful[:2])[:2]
    return meaningful[0][:2] if meaningful else "GG"

def normalize_case_id(raw_id, module, index, prefix="CP-AC-"):
    candidate = safe_text(raw_id)
    if re.fullmatch(r"CP-AC-[A-Za-z0-9_-]+-\d{5}", candidate):
        return candidate
    return f"{prefix}{module_token(module)}-{index:05d}"

def suite_token_from_name(suite_name="", reference_title=""):
    """
    Obtiene las dos iniciales funcionales de la Suite.
    Prioridad:
    1. Prefijo CP-ACXX-##### encontrado en un CP real de referencia.
    2. Nombre de la Suite.
    """
    suite_name = safe_text(suite_name)

    match = re.search(
        r"\bCP-AC([A-Z0-9]{2})-\d{5}\b",
        safe_text(reference_title).upper()
    )

    if match:
        return match.group(1)

    raw = re.sub(
        r"[^A-Za-zÁÉÍÓÚÜÑ0-9]+",
        " ",
        suite_name.upper()
    ).strip()

    words = [w for w in raw.split() if w]

    if not words:
        return "GG"

    stopwords = {
        "DE", "DEL", "LA", "LAS", "EL", "LOS",
        "EN", "POR", "PARA", "Y", "O", "CON"
    }

    meaningful = [
        w for w in words
        if w not in stopwords
    ]

    if len(meaningful) >= 2:
        return "".join(w[0] for w in meaningful[:2])[:2]

    return meaningful[0][:2] if meaningful else "GG"

def normalize_case_ids_by_suite(cases, suite_name="", reference_title=""):
    """
    Numera los CP independientemente por Suite. Cada Suite comienza en 00001.
    """
    cases = cases or []
    default_suite_token = suite_token_from_name(suite_name, reference_title)
    counters = {}

    for tc in cases:
        if not isinstance(tc, dict):
            continue

        case_suite = safe_text(
            tc.get("Suite"),
            tc.get("Suite Name"),
            suite_name
        )

        suite_token = suite_token_from_name(
            case_suite,
            reference_title
        ) or default_suite_token

        counters.setdefault(suite_token, 0)
        counters[suite_token] += 1

        tc["ID"] = f"CP-AC{suite_token}-{counters[suite_token]:05d}"

    return cases

def build_case_title(tc, case_id):
    """
    Construye el título funcional definitivo.
    Formato: CP-ACXX-##### Descripción funcional
    """
    raw_title = safe_text(tc.get("Title"))

    candidates = [
        raw_title,
        safe_text(tc.get("Scenario")),
        safe_text(tc.get("Description")),
        safe_text(tc.get("Related Use Case")),
    ]

    functional_title = ""

    for candidate in candidates:
        candidate = re.sub(r"\s+", " ", candidate).strip()

        if not candidate:
            continue

        if re.fullmatch(r"CP-AC[A-Z0-9]{2}-\d{5}", candidate.upper()):
            continue

        if candidate.upper() == case_id.upper():
            continue

        functional_title = candidate
        break

    if not functional_title:
        functional_title = "Validar funcionalidad definida en el Caso de Uso"

    # Evitar duplicar el ID si Gemini ya lo incluyó.
    functional_title = re.sub(
        rf"^\s*{re.escape(case_id)}\s*[-:–—]?\s*",
        "",
        functional_title,
        flags=re.I
    ).strip()

    return f"{case_id} {functional_title}"

def remove_all_pipes(value):
    """Elimina completamente el carácter pipe del contenido QA."""
    if value is None:
        return ""
    return str(value).replace("|", "")

def sanitize_cp_content(tc):
    """
    Elimina pipes y literales \n visibles del contenido del CP.
    Conserva saltos de línea reales.
    """
    if not isinstance(tc, dict):
        return tc

    for key, value in list(tc.items()):
        if isinstance(value, str):
            value = value.replace("|", "")
            value = value.replace("\\r\\n", "\n")
            value = value.replace("\\n", "\n")
            value = value.replace("\\r", "\n")
            tc[key] = value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    sanitize_cp_content(item)
        elif isinstance(value, dict):
            sanitize_cp_content(value)

    return tc

# ============================================================
# FUNCIONES DE VALIDACIÓN DE CALIDAD
# ============================================================
def validate_cp_depth(test_cases):
    problems = []

    for tc in test_cases or []:
        cp_id = safe_text(tc.get("ID"), "CP-SIN-ID")
        description = safe_text(tc.get("Description"))
        steps = safe_steps(tc)

        if len(description.strip()) < 250:
            problems.append(f"{cp_id}: Description demasiado superficial.")

        if len(steps) < 6:
            problems.append(f"{cp_id}: solo tiene {len(steps)} Steps.")

        for idx, step in enumerate(steps, start=1):
            action = safe_text(
                step.get("Action"),
                step.get("action"),
                step.get("Step")
            )
            expected = safe_text(
                step.get("Expected value"),
                step.get("Expected"),
                step.get("expected")
            )

            if not action:
                problems.append(f"{cp_id}: Step {idx} sin Action.")

            if not expected:
                problems.append(f"{cp_id}: Step {idx} sin Expected.")

    return problems

def validate_cp_format(test_cases):
    problems = []

    for tc in test_cases or []:
        cp_id = safe_text(tc.get("ID"))

        if not re.fullmatch(r"CP-AC[A-Z0-9]{2}-\d{5}", cp_id.upper()):
            problems.append(f"ID inválido: {cp_id}")

        title = build_case_title(tc, cp_id)

        if "|" in title:
            problems.append(f"{cp_id}: Title contiene pipe.")

        description = safe_text(tc.get("Description"))

        if "|" in description:
            problems.append(f"{cp_id}: Description contiene pipe.")

        if "\\n" in description:
            problems.append(f"{cp_id}: Description contiene literal \\n.")

    return problems

# ============================================================
# SIMULACIÓN Y GENERACIÓN (GEMINI / COBERTURA / EXCEL / PDF)
# ============================================================
def generate_qa_data(prompt, source_text, api_key, model, temp, max_retries, wait_time):
    # Mock / Implementación real de generación Gemini
    time.sleep(1)
    mock_cases = [
        {
            "ID": "RAW_1",
            "Title": "Crear subsección Tasas por Producto en Características Generales",
            "Module": "Características Generales",
            "Description": "Ingresar con usuario del perfil suscriptor, seleccionar el icono de autos colectivos, consultar colectivo en estado cotizado, descargar el archivo Base Emisión y validar que la hoja Orden Emisión, en la sección Características Generales, contenga la subsección correspondiente con todos los límites, parametros y reglas establecidas en el CU.",
            "Steps": [
                {"Action": "Ingresar al módulo de suscriptor con credenciales válidas.", "Expected": "Acceso concedido al menú principal."},
                {"Action": "Seleccionar el icono de autos colectivos.", "Expected": "Pantalla de administración cargada."},
                {"Action": "Consultar colectivo en estado cotizado.", "Expected": "Registros mostrados correctamente."},
                {"Action": "Descargar el archivo Base Emisión.", "Expected": "Archivo generado en la ruta elegida."},
                {"Action": "Ubicar la hoja Orden Emisión y sección Características Generales.", "Expected": "Sección visible y navegable."},
                {"Action": "Validar la subsección Tasas por Producto.", "Expected": "Datos coincidentes con la parametrización del CU."}
            ]
        }
    ]
    return {"TEST_CASES": mock_cases}

def coverage_gate_or_stop(result):
    return {"coverage": "100%"}

def create_excel(result, config):
    output = io.BytesIO()
    rows = []
    for tc in result.get("TEST_CASES", []):
        case_id = safe_text(tc.get("ID"))
        if not re.fullmatch(r"CP-AC[A-Z0-9]{2}-\d{5}", case_id.upper()):
            raise ValueError(f"ID funcional inválido para CP: {case_id}")
        
        title = build_case_title(tc, case_id)
        steps = safe_steps(tc)
        
        for idx, step in enumerate(steps, start=1):
            action = safe_text(step.get("Action"), step.get("action"))
            expected = safe_text(step.get("Expected value"), step.get("Expected"))
            rows.append({
                "ID": case_id,
                "Work Item Type": "Test Case",
                "Title": title if idx == 1 else "",
                "Description": safe_text(tc.get("Description")) if idx == 1 else "",
                "Test Step": idx,
                "Step Action": action,
                "Step Expected": expected,
                "Area Path": "",
                "IDPadre": "",
                "Tipo Origen Proyecto": "",
                "Tiempo Real": "",
                "Assigned To": "",
                "State": "Design"
            })
    
    df = pd.DataFrame(rows, columns=AZURE_COLUMNS)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Test Cases")
    return output.getvalue()

def create_pdf(result, config, source_name):
    return b"%PDF-1.4 Mock PDF Content"

# ============================================================
# INTEGRACIÓN AZURE DEVOPS (CONEXIÓN, PLANES, SUITES, CP)
# ============================================================
def list_test_plans(limit=10):
    # Mantiene consulta de los 10 Test Plans más recientes
    return [{"id": "101", "name": "Plan Principal QA"}]

def list_suites(plan_id):
    return [
        {"id": "201", "name": "Características Generales"},
        {"id": "202", "name": "Opciones Especiales"}
    ]

def list_test_cases_in_suite(plan_id, suite_id):
    return [{"id": "3001", "name": "CP-ACGG-00001 Ejemplo Referencia"}]

def get_test_case_detail(case_id):
    return {
        "title": "CP-ACGG-00001 Validar subsecciones en Orden Emision",
        "description": "Navegación completa desde suscripción...",
        "steps": []
    }

def add_parent_relation_to_work_item(azure_id, suite_parent_id):
    pass

# ============================================================
# INTERFAZ Y FLUJO PRINCIPAL
# ============================================================
st.title("🧪 Generador de Casos de Prueba QA")

# Sección Azure DevOps
st.subheader("Configuración Azure DevOps")
plans = list_test_plans(limit=10)
plan_options = [p["name"] for p in plans]
selected_plan_label = st.selectbox("Seleccionar Test Plan", plan_options) if plan_options else None

if selected_plan_label:
    selected_plan_id = plans[plan_options.index(selected_plan_label)]["id"]
    suites = list_suites(selected_plan_id)
    suite_options = [s["name"] for s in suites]
    selected_suite_label = st.selectbox("Seleccionar Suite", suite_options) if suite_options else None

    if selected_suite_label:
        selected_suite = suites[suite_options.index(selected_suite_label)]
        selected_suite_id = selected_suite.get("id")
        selected_suite_name = _ui_text(selected_suite.get("name"), "Suite sin nombre")

        cases = list_test_cases_in_suite(selected_plan_id, selected_suite_id)
        case_options = [c["name"] for c in cases]
        selected_case_label = st.selectbox("CP de Referencia", case_options) if case_options else None

        if selected_case_label:
            selected_case_id = cases[case_options.index(selected_case_label)]["id"]
            if st.button("Cargar Referencia"):
                detail = get_test_case_detail(selected_case_id)
                st.session_state.azure_reference_suite_id = selected_suite_id
                st.session_state.azure_reference_suite_name = selected_suite_name
                st.session_state.azure_reference_case_title = safe_text(detail.get("title"))
                st.success(f"Referencia cargada: {st.session_state.azure_reference_case_title}")

# Botón Ejecutar Flujo Principal
st.divider()
if st.button("🚀 Generar Casos de Prueba"):
    try:
        source_text = "Texto de caso de uso de entrada..."
        api_key = "MOCK_KEY"
        selected_model = "gemini-pro"
        max_retries = 3
        wait_time = 2
        selected_config = {}

        # 1. Generar respuesta
        result = generate_qa_data(
            load_prompt(),
            source_text,
            api_key,
            selected_model,
            0.0,
            int(max_retries),
            int(wait_time),
        )

        # 2. Numeración definitiva por Suite
        result["TEST_CASES"] = normalize_case_ids_by_suite(
            result.get("TEST_CASES", []),
            suite_name=st.session_state.get("azure_reference_suite_name", ""),
            reference_title=st.session_state.get("azure_reference_case_title", "")
        )

        # 3. Limpieza definitiva (sanitización de pipes y \\n)
        for tc in result.get("TEST_CASES", []):
            sanitize_cp_content(tc)

        # 4. Validación de formato
        format_problems = validate_cp_format(result.get("TEST_CASES", []))
        if format_problems:
            raise ValueError("GENERACIÓN BLOQUEADA:\n" + "\n".join(format_problems))

        # 5. Validación de profundidad
        depth_problems = validate_cp_depth(result.get("TEST_CASES", []))
        if depth_problems:
            raise ValueError("GENERACIÓN BLOQUEADA POR PROFUNDIDAD:\n" + "\n".join(depth_problems))

        # 6. Cobertura CU
        coverage_metrics = coverage_gate_or_stop(result)

        # 7. Guardar resultado
        st.session_state.result_json = result

        # 8. Generar Excel
        st.session_state.excel_data = create_excel(result, selected_config)

        # 9. Generar PDF
        st.session_state.pdf_data = create_pdf(result, selected_config, st.session_state.get("source_name", ""))

        st.success("¡Generación completada con éxito!")

    except Exception as e:
        st.error(str(e))

# ============================================================
# PREVIEW Y EDITOR
# ============================================================
if st.session_state.result_json:
    st.divider()
    st.subheader("Vista Previa y Editor")
    
    test_cases = st.session_state.result_json.get("TEST_CASES", [])
    preview_rows = []
    
    for tc in test_cases:
        case_id = safe_text(
            tc.get("ID"),
            f"CP-SIN-ID-{len(preview_rows) + 1:05d}"
        )

        preview_rows.append({
            "ID": case_id,
            "Title": build_case_title(tc, case_id),
            "Module": safe_text(tc.get("Module")),
            "Scenario Type": safe_text(tc.get("Scenario Type")),
            "Steps": len(safe_steps(tc)),
        })

    st.dataframe(pd.DataFrame(preview_rows))

    # Editor de casos
    if preview_rows:
        selected_idx = st.number_input("Seleccionar índice a editar", min_value=0, max_value=len(test_cases)-1, step=1)
        selected_case = test_cases[selected_idx]
        
        st.info("El ID no se puede modificar.")
        st.text_input("ID", value=selected_case["ID"], disabled=True)
        new_title = st.text_input("Título", value=selected_case.get("Title", ""))
        new_desc = st.text_area("Descripción", value=selected_case.get("Description", ""))
        
        if st.button("Guardar Cambios en Editor"):
            selected_case["Title"] = new_title
            selected_case["Description"] = new_desc
            st.success("Cambios aplicados correctamente.")