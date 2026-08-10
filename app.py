import io
import json
import logging
import os
import re
import time
from pathlib import Path
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

APP_VERSION = "V17"
MODEL = "gemini-3.6-flash"
FALLBACK_MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

# ============================================================
# COLUMNAS APROBADAS — NO AGREGAR NI CAMBIAR TÍTULOS
# ============================================================
AZURE_COLUMNS = [
    "TestCaseId", "Title", "TestStep", "StepAction", "StepExpected",
    "TestPointId", "Configuration", "Tester", "Outcome", "Comment"
]

MATRIZ_COLUMNS = [
    "TestCaseId", "Title", "Requirement / Use Case", "Criterion", "Scenario",
    "Scenario Type", "Description", "Preconditions", "Validation Method",
    "Coverage", "Alerts", "Effort"
]

EXCEL_CONFIGS = {
    "Autos Colectivos": {
        "sheet_name": "Azure Import",
        "base_id": 10001,
        "base_testpoint": 1001,
        "configuration": "Default configuration",
        "tester": "",
        "title_prefix": "CP-AC-",
        "user_default": "Usuario registrado",
        "steps_with_users": True,
    },
    "Siniestros Fasecolda": {
        "sheet_name": "28443;Fase 3 - RENK170 Siniestr",
        "base_id": 28454,
        "base_testpoint": 6552,
        "configuration": "Default configuration created @ 26/05/2023 15:22:17",
        "tester": "Isabel Cristina Mejía López",
        "title_prefix": "CP-ACSF-",
        "user_default": "Suscriptor Oficina Principal, suscriptor sucursal autos",
        "steps_with_users": True,
    },
    "General QA": {
        "sheet_name": "Casos de Prueba",
        "base_id": 20001,
        "base_testpoint": 2001,
        "configuration": "",
        "tester": "",
        "title_prefix": "CP-",
        "user_default": "",
        "steps_with_users": False,
    },
}

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
                    "Coverage": {"type": "string"},
                    "Validation Method": {"type": "string"},
                    "Steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Step #": {"type": "integer"},
                                "Action": {"type": "string"},
                                "Expected value": {"type": "string"},
                            },
                            "required": ["Step #", "Action", "Expected value"],
                        },
                    },
                    "Alerts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "Alert": {"type": "string"},
                                "Reason": {"type": "string"},
                                "Validation Required": {"type": "string"},
                            },
                            "required": ["Alert", "Reason", "Validation Required"],
                        },
                    },
                },
                "required": ["ID", "Title", "Description", "Preconditions", "Steps"],
            },
        },
        "ALERTS": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "Alert": {"type": "string"},
                    "Reason": {"type": "string"},
                    "Validation Required": {"type": "string"},
                },
                "required": ["Alert", "Reason", "Validation Required"],
            },
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
                    "Alerts": {"type": "string"},
                },
                "required": ["Requirement / Use Case", "Criterion", "Scenario", "Test Case"],
            },
        },
    },
    "required": ["TEST_CASES", "ALERTS", "COVERAGE"],
}


def safe_text(value, default=""):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def safe_steps(tc):
    steps = tc.get("Steps", [])
    return steps if isinstance(steps, list) else []


def normalize_coverage(value):
    v = safe_text(value).strip().lower()
    allowed = {
        "completa": "Completa",
        "parcial": "Parcial",
        "no cubierta": "No cubierta",
        "fuera de alcance": "Fuera de alcance",
    }
    return allowed.get(v, safe_text(value, "Pendiente"))


def normalize_validation_method(value):
    v = safe_text(value).strip().lower()
    mapping = {
        "ui": "UI",
        "interfaz": "UI",
        "interfaz de usuario": "UI",
        "bd": "BD",
        "base de datos": "BD",
        "database": "BD",
        "api": "API",
        "web service": "API",
        "web services": "API",
        "mixta": "Mixta",
        "mixto": "Mixta",
    }
    return mapping.get(v, safe_text(value, "Pendiente"))


def module_token(module, title="", scenario=""):
    raw = safe_text(module) or safe_text(title) or safe_text(scenario) or "GENERAL"
    raw = re.sub(r"[^A-Za-z0-9]+", " ", raw).strip().upper()
    words = raw.split()
    if not words:
        return "GENERAL"
    if len(words) == 1:
        return words[0][:12]
    return "".join(w[0] for w in words)[:8]


def build_case_title(tc, case_id):
    """
    V12: garantiza que Title sea un título funcional y no el CP ID.
    Prioridad:
      1) Title generado por el modelo si no es solo el ID.
      2) Scenario
      3) Description
      4) Related Use Case
      5) fallback controlado.
    """
    raw_title = safe_text(tc.get("Title"))
    normalized_title = re.sub(r"\s+", " ", raw_title).strip()

    # Un título igual al ID no es un título funcional.
    if (
        not normalized_title
        or normalized_title.upper() == case_id.upper()
        or re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}", normalized_title.upper())
    ):
        candidates = [
            safe_text(tc.get("Scenario")),
            safe_text(tc.get("Description")),
            safe_text(tc.get("Related Use Case")),
        ]

        for candidate in candidates:
            candidate = re.sub(r"\s+", " ", candidate).strip()
            if candidate and candidate.upper() != case_id.upper():
                normalized_title = candidate
                break

    if not normalized_title:
        normalized_title = f"Caso de prueba {case_id}"

    return normalized_title


def normalize_case_id(raw_id, module, index, prefix="CP-AC-"):
    candidate = safe_text(raw_id)
    if re.fullmatch(r"CP-AC-[A-Za-z0-9_-]+-\d{5}", candidate):
        return candidate
    return f"{prefix}{module_token(module)}-{index:05d}"


def find_coverage(data, tc):
    tc_id = safe_text(tc.get("ID"))
    for row in data.get("COVERAGE", []) if isinstance(data.get("COVERAGE", []), list) else []:
        if safe_text(row.get("Test Case")) == tc_id:
            return row
    return {}


def aggregate_case_alerts(data, tc):
    parts = []
    case_alerts = tc.get("Alerts", [])
    if isinstance(case_alerts, list):
        for alert in case_alerts:
            text = safe_text(alert.get("Alert"))
            reason = safe_text(alert.get("Reason"))
            validation = safe_text(alert.get("Validation Required"))
            if text:
                if reason:
                    text += f": {reason}"
                if validation:
                    text += f" | Validación: {validation}"
                parts.append(text)
    return " | ".join(parts) if parts else "Sin Alertas"


# ============================================================
# EXTRACCIÓN ROBUSTA DE DOCUMENTOS
# ============================================================
def extract_txt(uploaded_file):
    raw = uploaded_file.getvalue()
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("No fue posible decodificar el archivo de texto.")


def extract_pdf(uploaded_file):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "La dependencia 'pypdf' no está disponible en el entorno. "
            "Verifica requirements.txt y vuelve a desplegar la aplicación."
        ) from exc

    reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append(f"[Página {page_number}]\n{text}")

    content = "\n\n".join(pages).strip()
    if not content:
        raise ValueError(
            "El PDF se abrió correctamente, pero no contiene texto extraíble. "
            "Si es un PDF escaneado, esta versión requiere OCR."
        )
    return content


def extract_docx(uploaded_file):
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "La dependencia 'python-docx' no está disponible. "
            "Verifica requirements.txt y vuelve a desplegar la aplicación."
        ) from exc

    doc = Document(io.BytesIO(uploaded_file.getvalue()))
    blocks = [p.text for p in doc.paragraphs if p.text.strip()]

    for table in doc.tables:
        for row in table.rows:
            blocks.append(" | ".join(cell.text.strip() for cell in row.cells))

    content = "\n".join(blocks).strip()
    if not content:
        raise ValueError("El DOCX se abrió correctamente, pero no contiene texto.")
    return content


def extract_source(uploaded_file):
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower()

    if extension in ("txt", "md"):
        content = extract_txt(uploaded_file)
    elif extension == "pdf":
        content = extract_pdf(uploaded_file)
    elif extension == "docx":
        content = extract_docx(uploaded_file)
    else:
        raise ValueError(f"Formato no soportado: .{extension}")

    if not content.strip():
        raise ValueError("El documento no contiene contenido utilizable.")

    return content


# ============================================================
# PROMPT EXISTENTE — SE CONSERVA SIN CAMBIOS
# ============================================================
@st.cache_data(ttl=3600)
def load_prompt():
    path = "prompt_qa.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content

    return (
        "Eres un agente QA especializado en análisis de documentación. "
        "Analiza exclusivamente la fuente proporcionada, no inventes información "
        "y genera TEST_CASES, ALERTS y COVERAGE en JSON."
    )


@st.cache_data(ttl=3600)
def get_valid_models(api_key):
    if genai is None:
        return FALLBACK_MODELS

    try:
        client = genai.Client(api_key=api_key)
        names = []
        for model in client.models.list():
            name = model.name.split("/")[-1]
            if "gemini" in name.lower():
                names.append(name)
        return sorted(set(names)) or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


def validate_qa_structure(data):
    if not isinstance(data, dict):
        raise ValueError("La respuesta de Gemini no es un objeto JSON.")

    for key in ("TEST_CASES", "ALERTS", "COVERAGE"):
        if key not in data:
            raise ValueError(f"Falta la clave requerida: {key}")

    if not isinstance(data["TEST_CASES"], list) or not data["TEST_CASES"]:
        raise ValueError("No se generaron casos de prueba.")

    if not isinstance(data["ALERTS"], list):
        data["ALERTS"] = []

    if not isinstance(data["COVERAGE"], list):
        data["COVERAGE"] = []

    return data


def _is_gemini_3x(model_name):
    return safe_text(model_name).lower().startswith(("gemini-3.", "gemini-3"))


def _extract_error_detail(exc):
    raw = str(exc)
    # Keep the useful API message but avoid dumping huge exception payloads.
    return raw[:1800]


def _generate_once(client, model_name, full_prompt):
    """
    V10:
    - Gemini 3.x: no temperature/top_p/top_k.
    - Uses structured JSON output.
    - Limits output to 32K tokens for stability.
    """
    # google-genai actual Python SDK format:
    # response_mime_type + response_schema.
    # Do NOT use response_format here; that shape is rejected by
    # GenerateContentConfig in the installed SDK.
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SCHEMA,
        max_output_tokens=32768,
    )

    return client.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config=config,
    )


def generate_qa_data(
    prompt_text,
    source_content,
    api_key,
    model_name,
    temperature=0.1,
    max_retries=2,
    initial_wait=10,
):
    if genai is None:
        raise RuntimeError("No está instalada la librería google-genai.")

    if not api_key:
        raise ValueError("API Key no configurada.")

    if not source_content.strip():
        raise ValueError("Fuente de información vacía.")

    max_source_chars = 28000
    if len(source_content) > max_source_chars:
        source_content = source_content[:max_source_chars] + (
            "\n...[CONTENIDO TRUNCADO POR LÍMITE DE SEGURIDAD]"
        )

    full_prompt = (
        prompt_text
        + "\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n"
        + source_content
        + "\n\n==================== REGLA DE SALIDA ====================\n"
        "Devuelve exclusivamente JSON válido que cumpla el esquema solicitado. "
        "No agregues explicaciones fuera del JSON."
    )

    client = genai.Client(api_key=api_key)

    # Prefer selected model, then use stable/available fallbacks.
    candidates = []
    for candidate in [model_name] + FALLBACK_MODELS:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    errors = []

    for candidate in candidates:
        for attempt in range(max_retries + 1):
            try:
                response = _generate_once(
                    client,
                    candidate,
                    full_prompt,
                )

                response_text = (response.text or "").strip()

                if not response_text:
                    raise RuntimeError(
                        f"{candidate}: Gemini devolvió una respuesta vacía."
                    )

                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    match = re.search(
                        r"```(?:json)?\s*([\s\S]*?)\s*```",
                        response_text,
                    )
                    if not match:
                        raise RuntimeError(
                            f"{candidate}: la respuesta no es JSON válido. "
                            f"Respuesta: {response_text[:1200]}"
                        )
                    data = json.loads(match.group(1))

                validated = validate_qa_structure(data)

                st.session_state.quota_exceeded = False
                st.session_state.retry_count = 0

                return validated

            except Exception as exc:
                detail = _extract_error_detail(exc)
                errors.append(f"{candidate} / intento {attempt + 1}: {detail}")

                error_text = detail.lower()

                is_quota = (
                    "429" in detail
                    or "quota" in error_text
                    or "rate limit" in error_text
                    or "resource exhausted" in error_text
                )

                is_retryable_internal = (
                    "500" in detail
                    or "internal" in error_text
                    or "503" in detail
                    or "unavailable" in error_text
                    or "deadline" in error_text
                    or "timeout" in error_text
                )

                if is_quota:
                    st.session_state.quota_exceeded = True
                    st.session_state.retry_count = attempt + 1

                # A 400 caused by an unsupported request/schema should not
                # be retried against the same model; move to next candidate.
                is_bad_request = (
                    "400" in detail
                    or "invalid argument" in error_text
                    or "invalid_argument" in error_text
                    or "unsupported" in error_text
                )

                if (
                    attempt < max_retries
                    and (is_quota or is_retryable_internal)
                ):
                    time.sleep(initial_wait * (attempt + 1))
                    continue

                if is_bad_request or is_retryable_internal or is_quota:
                    break

                # Validation/JSON errors are meaningful and should be shown,
                # but we still allow another model to try.
                break

    joined = "\n\n".join(errors[-8:])
    raise RuntimeError(
        "Gemini no pudo completar la generación con los modelos probados.\n\n"
        "Detalle técnico:\n" + joined
    )


# ============================================================
# EXCEL — ESTRUCTURA APROBADA
# ============================================================
def create_excel(data, config_key):
    config = EXCEL_CONFIGS[config_key]
    output = io.BytesIO()

    azure_rows = []
    matriz_rows = []
    cases = data.get("TEST_CASES", [])

    for idx, tc in enumerate(cases, start=1):
        module = safe_text(tc.get("Module"), "GENERAL")
        case_id = normalize_case_id(
            tc.get("ID"), module, idx, config["title_prefix"]
        )
        title = build_case_title(tc, case_id)
        description = safe_text(tc.get("Description"))
        preconditions = safe_text(tc.get("Preconditions"))
        scenario = safe_text(tc.get("Scenario"), description)
        steps = safe_steps(tc)

        coverage = find_coverage(data, tc)

        validation_method = normalize_validation_method(
            coverage.get("Validation Method", tc.get("Validation Method", "Pendiente"))
        )

        coverage_value = normalize_coverage(
            coverage.get("Coverage", tc.get("Coverage", "Pendiente"))
        )

        alerts = safe_text(coverage.get("Alerts")) or aggregate_case_alerts(data, tc)

        if alerts == "Sin Alertas" and data.get("ALERTS"):
            general_alerts = []
            for alert in data["ALERTS"]:
                alert_name = safe_text(alert.get("Alert"))
                reason = safe_text(alert.get("Reason"))
                if alert_name:
                    general_alerts.append(
                        f"{alert_name}: {reason}" if reason else alert_name
                    )
            if general_alerts:
                alerts = " | ".join(general_alerts)

        # Azure Import
        azure_case_id = config["base_id"] + idx - 1
        test_point_id = f"{config['base_testpoint'] + idx - 1}:0"

        azure_rows.append({
            "TestCaseId": azure_case_id,
            "Title": title,
            "TestStep": "",
            "StepAction": "",
            "StepExpected": "",
            "TestPointId": test_point_id,
            "Configuration": config["configuration"],
            "Tester": config["tester"],
            "Outcome": "",
            "Comment": "",
        })

        if not steps:
            azure_rows.append({
                "TestCaseId": "",
                "Title": "",
                "TestStep": 1,
                "StepAction": "Información insuficiente para definir el paso.",
                "StepExpected": "Validar con el equipo funcional antes de ejecutar.",
                "TestPointId": "",
                "Configuration": "",
                "Tester": "",
                "Outcome": "",
                "Comment": "ALERTA: caso sin pasos definidos.",
            })
        else:
            for step_index, step in enumerate(steps, start=1):
                azure_rows.append({
                    "TestCaseId": "",
                    "Title": "",
                    "TestStep": step.get("Step #", step_index),
                    "StepAction": safe_text(
                        step.get("Action"), "Acción no definida"
                    ),
                    "StepExpected": safe_text(
                        step.get("Expected value"),
                        "Resultado esperado no definido",
                    ),
                    "TestPointId": "",
                    "Configuration": "",
                    "Tester": "",
                    "Outcome": "",
                    "Comment": "",
                })

        # Matriz QA
        matriz_rows.append({
            "TestCaseId": case_id,
            "Title": title,
            "Requirement / Use Case": safe_text(
                coverage.get("Requirement / Use Case", tc.get("Related Use Case"))
            ),
            "Criterion": safe_text(
                coverage.get("Criterion", tc.get("Criterion"))
            ),
            "Scenario": scenario,
            "Scenario Type": safe_text(tc.get("Scenario Type"), "No definido"),
            "Description": description,
            "Preconditions": preconditions,
            "Validation Method": validation_method,
            "Coverage": coverage_value,
            "Alerts": alerts,
            "Effort": safe_text(tc.get("Effort"), "No definido"),
        })

    df_azure = pd.DataFrame(azure_rows, columns=AZURE_COLUMNS)
    df_matriz = pd.DataFrame(matriz_rows, columns=MATRIZ_COLUMNS)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        azure_sheet = config["sheet_name"][:31]
        df_azure.to_excel(writer, sheet_name=azure_sheet, index=False)
        df_matriz.to_excel(writer, sheet_name="Matriz QA", index=False)

        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions

            for column_cells in ws.columns:
                letter = column_cells[0].column_letter
                max_len = max(
                    len(str(cell.value or "")) for cell in column_cells
                )
                ws.column_dimensions[letter].width = min(
                    max(max_len + 2, 12), 60
                )

    output.seek(0)
    return output.getvalue()


# ============================================================
# PDF
# ============================================================
def pdf_text(value):
    return escape(safe_text(value)).replace("\n", "<br/>")


def _unique_values(cases, key):
    values = []
    seen = set()
    for tc in cases:
        value = re.sub(r"\s+", " ", safe_text(tc.get(key))).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            values.append(value)
    return values


def _pdf_bullets(story, items, style, prefix="•"):
    for item in items:
        text = safe_text(item)
        if text:
            story.append(Paragraph(f"{prefix} {pdf_text(text)}", style))


def _coverage_summary(data):
    rows = []
    for item in data.get("COVERAGE", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "Requirement / Use Case": safe_text(item.get("Requirement / Use Case")),
            "Criterion": safe_text(item.get("Criterion")),
            "Scenario": safe_text(item.get("Scenario")),
            "Test Case": safe_text(item.get("Test Case")),
            "Validation Method": normalize_validation_method(
                item.get("Validation Method")
            ),
            "Coverage": normalize_coverage(item.get("Coverage")),
            "Alerts": safe_text(item.get("Alerts")),
        })
    return rows


def _register_reference_fonts():
    """Use Aptos from the supplied client reference when bundled."""
    font_dir = Path(__file__).resolve().parent / "fonts"
    regular = font_dir / "Aptos.ttf"
    bold = font_dir / "Aptos-Bold.ttf"
    italic = font_dir / "Aptos-BoldItalic.ttf"

    if regular.exists() and bold.exists():
        try:
            pdfmetrics.registerFont(TTFont("Aptos", str(regular)))
            pdfmetrics.registerFont(TTFont("Aptos-Bold", str(bold)))
            if italic.exists():
                pdfmetrics.registerFont(TTFont("Aptos-BoldItalic", str(italic)))
            return "Aptos", "Aptos-Bold", "Aptos-BoldItalic"
        except Exception:
            pass
    return "Helvetica", "Helvetica-Bold", "Helvetica-BoldOblique"


def _case_bullets_as_paragraphs(story, text, style):
    """Render source-style bullets without introducing a new table/column."""
    value = safe_text(text)
    if not value:
        return
    lines = [x.strip() for x in value.splitlines() if x.strip()]
    for line in lines:
        clean = re.sub(r"^[•\-]\s*", "", line)
        story.append(Paragraph(f"• {pdf_text(clean)}", style))


def create_pdf(data, config_key, source_name=""):
    """
    V16 — PDF alineado visual y estructuralmente con el Test Plan del cliente.

    Se conserva la estructura de referencia:
      1) bloque inicial tipo tabla: Descripción del Software, Objetivos,
         Elementos requeridos, Lista de ítems que no serán probados y Entregables;
      2) Test plan Ejecución;
      3) DETALLE DE LOS CASOS DE PRUEBA;
      4) por caso: Test case, SUMMARY, Producto, Módulo, Descripción,
         Resultado esperado de la prueba, Precondiciones y Caso de uso relacionado.

    No agrega columnas ni bloques de resumen que no existen en el documento de
    referencia. Los datos del caso siguen proviniendo del resultado QA.
    """
    buffer = io.BytesIO()
    regular_font, bold_font, italic_font = _register_reference_fonts()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=36,
        title="Test plan Ejecución — VERSION PREVIA — DRAFT",
        author="Agente QA",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ref_title", parent=styles["Normal"], fontName=bold_font,
        fontSize=9.5, leading=11, spaceAfter=4,
    )
    cell_label = ParagraphStyle(
        "ref_label", parent=styles["Normal"], fontName=bold_font,
        fontSize=8, leading=9.5,
    )
    cell_body = ParagraphStyle(
        "ref_body", parent=styles["Normal"], fontName=regular_font,
        fontSize=8, leading=10,
    )
    cell_body_bold = ParagraphStyle(
        "ref_body_bold", parent=cell_body, fontName=bold_font,
    )
    section = ParagraphStyle(
        "ref_section", parent=styles["Normal"], fontName=bold_font,
        fontSize=9.5, leading=11, spaceBefore=8, spaceAfter=5,
    )
    case_head = ParagraphStyle(
        "ref_case", parent=styles["Normal"], fontName=bold_font,
        fontSize=8.8, leading=10.5, spaceBefore=6, spaceAfter=5,
    )
    summary = ParagraphStyle(
        "ref_summary", parent=styles["Normal"], fontName=bold_font,
        fontSize=9, leading=11, spaceBefore=4, spaceAfter=5,
    )
    body = ParagraphStyle(
        "ref_body_main", parent=styles["Normal"], fontName=regular_font,
        fontSize=8.3, leading=11, spaceAfter=4,
    )
    body_bold = ParagraphStyle(
        "ref_body_bold_main", parent=body, fontName=bold_font,
    )
    small_note = ParagraphStyle(
        "ref_note", parent=body, fontName=italic_font,
        fontSize=7.5, leading=9.5,
    )

    cases = data.get("TEST_CASES", []) or []
    products = _unique_values(cases, "Product")
    modules = _unique_values(cases, "Module")
    product_text = ", ".join(products) if products else "No definido en la fuente"
    module_text = ", ".join(modules) if modules else "No definido en la fuente"

    # Fuente del documento: solo se usa para identificar el entregable, no para inventar un ID.
    plan_name = safe_text(source_name, "Documentación proporcionada")

    # Descripción y objetivos se derivan de los casos generados, sin inventar información adicional.
    descriptions = []
    objectives = []
    for tc in cases:
        desc = safe_text(tc.get("Description"))
        if desc and desc.lower() not in {x.lower() for x in descriptions}:
            descriptions.append(desc)
        scenario = safe_text(tc.get("Scenario")) or build_case_title(
            tc, safe_text(tc.get("ID"), "CP-00001")
        )
        if scenario and scenario.lower() not in {x.lower() for x in objectives}:
            objectives.append(scenario)

    description_text = " ".join(descriptions[:3]) if descriptions else (
        "La documentación analizada contiene la información funcional utilizada "
        "para derivar los casos de prueba."
    )

    # ========================================================
    # BLOQUE INICIAL — MISMA ESTRUCTURA DE LA REFERENCIA
    # ========================================================
    story = []
    story.append(Paragraph(f"Test plan: {pdf_text(plan_name)}", title_style))

    objectives_flow = []
    for i, objective in enumerate(objectives[:10], start=1):
        objectives_flow.append(Paragraph(f"{i}. {pdf_text(objective)}", cell_body))

    elements_flow = [
        Paragraph("<i>Test plan para la documentación de los casos de prueba y su ejecución:</i>", cell_body),
        Spacer(1, 3),
        Paragraph("1. Software Screen Recorder o capturador de pantallas para grabar las evidencias.", cell_body),
        Spacer(1, 2),
        Paragraph("2. Tipos de pruebas:", cell_body),
        Paragraph("a. Pruebas de integración: Validar de manera general el funcionamiento de los módulos afectados por el ajuste.", cell_body),
        Paragraph("b. Pruebas funcionales: Validaciones de los módulos involucrados en el ajuste según casos de prueba diseñados.", cell_body),
    ]

    out_scope = [Paragraph("1. Cualquier otra funcionalidad no especificada en este documento.", cell_body)]
    deliverables = [
        Paragraph("1. Plan de pruebas.", cell_body),
        Paragraph("2. Informe de la ejecución de las pruebas.", cell_body),
        Paragraph("3. Archivo con evidencias de las pruebas realizadas para el proyecto.", cell_body),
        Paragraph("4. Requerimiento (opcional)", cell_body),
    ]

    # Build nested content as one cell to reproduce the client's two-column table.
    desc_cell = Paragraph(pdf_text(description_text), cell_body)
    obj_cell = objectives_flow or [Paragraph("No se identificaron objetivos explícitos en la información procesada.", cell_body)]
    elem_cell = elements_flow
    scope_cell = out_scope
    deliver_cell = deliverables

    table_data = [
        [Paragraph("Descripción del<br/>Software", cell_label), desc_cell],
        [Paragraph("Objetivos de las<br/>pruebas", cell_label), obj_cell],
        [Paragraph("Elementos<br/>requeridos", cell_label), elem_cell],
        [Paragraph("Lista de ítems<br/>que no serán<br/>probados", cell_label), scope_cell],
        [Paragraph("Entregables", cell_label), deliver_cell],
    ]

    plan_table = Table(table_data, colWidths=[105, 435])
    plan_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.65, colors.HexColor("#777777")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(plan_table)
    story.append(Spacer(1, 18))
    story.append(Paragraph("Test plan Ejecución", section))
    story.append(HRFlowable(width="100%", thickness=0.65, color=colors.HexColor("#777777")))
    story.append(Spacer(1, 7))
    story.append(Paragraph("DETALLE DE LOS CASOS DE PRUEBA", section))

    # ========================================================
    # CASOS — MISMA SECUENCIA DE CAMPOS DE LA REFERENCIA
    # ========================================================
    for idx, tc in enumerate(cases, start=1):
        case_id = safe_text(tc.get("ID"), f"CP-{idx:05d}")
        title_value = build_case_title(tc, case_id)

        story.append(
            Paragraph(
                f"Test case {pdf_text(case_id)}: {pdf_text(title_value)}",
                case_head,
            )
        )
        story.append(Paragraph("SUMMARY", summary))
        story.append(Paragraph(
            f"<b>Producto:</b> {pdf_text(safe_text(tc.get('Product'), product_text))}",
            body,
        ))
        story.append(Paragraph(
            f"<b>Módulo:</b> {pdf_text(safe_text(tc.get('Module'), module_text))}",
            body,
        ))
        story.append(Paragraph(
            f"<b>Descripción:</b> {pdf_text(safe_text(tc.get('Description'), 'No definida en la fuente.'))}",
            body,
        ))

        expected_result = safe_text(tc.get("Expected Result"))
        story.append(Paragraph(
            f"<b>Resultado esperado de la prueba:</b> {pdf_text(expected_result or 'No definido en la fuente.')}",
            body,
        ))

        preconditions = safe_text(tc.get("Preconditions"))
        if preconditions:
            story.append(Paragraph("<b>Precondiciones:</b>", body))
            _case_bullets_as_paragraphs(story, preconditions, body)
        else:
            story.append(Paragraph(
                "<b>Precondiciones:</b> No se definieron precondiciones en la fuente.",
                body,
            ))

        related = safe_text(tc.get("Related Use Case"))
        if related:
            story.append(Paragraph("<b>Caso de uso relacionado:</b>", body))
            _case_bullets_as_paragraphs(story, related, body)
        else:
            story.append(Paragraph(
                "<b>Caso de uso relacionado:</b> No se identificó en la fuente.",
                body,
            ))

        # Los Steps se conservan, pero se presentan como texto corrido/numerado,
        # sin crear una tabla o columnas nuevas que no existen en la referencia.
        steps = safe_steps(tc)
        if steps:
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>Secuencia de prueba:</b>", body))
            for step in steps:
                num = safe_text(step.get("Step #"), "")
                action = safe_text(step.get("Action"))
                expected = safe_text(step.get("Expected value"))
                story.append(Paragraph(
                    f"{pdf_text(num)}. {pdf_text(action)}",
                    body,
                ))
                if expected:
                    story.append(Paragraph(
                        f"Resultado esperado: {pdf_text(expected)}",
                        body,
                    ))

        # Alerts are only printed when the case actually has one, avoiding a new
        # permanent section in every case.
        case_alerts = tc.get("Alerts", [])
        if isinstance(case_alerts, list) and case_alerts:
            for alert in case_alerts:
                if not isinstance(alert, dict):
                    continue
                alert_name = safe_text(alert.get("Alert"))
                reason = safe_text(alert.get("Reason"))
                validation = safe_text(alert.get("Validation Required"))
                note_text = " / ".join(x for x in [alert_name, reason, validation] if x)
                if note_text:
                    story.append(Paragraph(
                        f"<i>Alerta: {pdf_text(note_text)}</i>",
                        small_note,
                    ))

        if idx < len(cases):
            story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


# ============================================================
# INTERFAZ
# ============================================================
st.set_page_config(
    page_title=f"Agente QA {APP_VERSION}",
    layout="wide",
)

if "source_content" not in st.session_state:
    st.session_state.source_content = ""
if "source_name" not in st.session_state:
    st.session_state.source_name = ""
if "result_json" not in st.session_state:
    st.session_state.result_json = None
if "excel_data" not in st.session_state:
    st.session_state.excel_data = None
if "pdf_data" not in st.session_state:
    st.session_state.pdf_data = None

st.title(f"🤖 Agente QA {APP_VERSION} — Generador de Casos de Prueba")
st.caption(
    "VERSION PREVIA — DRAFT | PDF / DOCX / TXT / MD → análisis QA → Excel + PDF"
)

with st.sidebar:
    st.header("⚙️ Configuración")

    api_key = st.secrets.get(
        "GEMINI_API_KEY",
        os.getenv("GEMINI_API_KEY", ""),
    )

    if api_key:
        st.success("✅ GEMINI_API_KEY configurada")
    else:
        api_key = st.text_input(
            "🔑 Google Gemini API Key",
            type="password",
        )

    selected_model = st.selectbox(
        "Modelo",
        FALLBACK_MODELS,
        index=0,
    )

    selected_config = st.selectbox(
        "Formato de Excel",
        list(EXCEL_CONFIGS.keys()),
        index=0,
    )

    max_retries = st.number_input(
        "Máximo de reintentos",
        min_value=0,
        max_value=5,
        value=2,
    )

    wait_time = st.number_input(
        "Espera inicial (segundos)",
        min_value=1,
        max_value=60,
        value=10,
    )


st.subheader("📁 Carga de Documento")

st.info(
    "Formatos soportados: TXT, MD, PDF, DOCX. "
    "Para PDF escaneado se requiere OCR; esta versión no inventa "
    "texto que no pueda extraer."
)

uploaded = st.file_uploader(
    "Arrastra o selecciona un documento",
    type=["txt", "md", "pdf", "docx"],
)

source_text = st.session_state.source_content

if uploaded:
    # Procesar solo cuando cambia el archivo.
    if st.session_state.source_name != uploaded.name:
        try:
            with st.spinner(f"Procesando {uploaded.name}..."):
                source_text = extract_source(uploaded)

            st.session_state.source_content = source_text
            st.session_state.source_name = uploaded.name
            st.session_state.result_json = None
            st.session_state.excel_data = None
            st.session_state.pdf_data = None

            st.success(f"✅ {uploaded.name} procesado correctamente.")

        except Exception as exc:
            st.session_state.source_content = ""
            st.session_state.source_name = ""
            st.session_state.result_json = None
            st.session_state.excel_data = None
            st.session_state.pdf_data = None

            st.error(f"❌ No se pudo procesar el archivo: {exc}")

if source_text:
    with st.expander("📄 Vista previa del contenido", expanded=True):
        st.text_area(
            "Contenido",
            source_text[:5000],
            height=250,
            disabled=True,
        )

        c1, c2, c3 = st.columns(3)
        c1.metric("Caracteres", len(source_text))
        c2.metric("Líneas", len(source_text.splitlines()))
        c3.metric("Palabras", len(source_text.split()))

else:
    source_text = st.text_area(
        "✏️ O ingresa el texto manualmente",
        height=220,
        placeholder=(
            "Pega aquí la Historia de Usuario o documentación fuente..."
        ),
    )

    if source_text:
        st.session_state.source_content = source_text


st.divider()
st.subheader("🧪 Generación QA")

if st.button(
    "🚀 Generar casos de prueba",
    type="primary",
    disabled=not bool(source_text.strip()),
):
    try:
        with st.spinner(
            "Analizando documentación y generando casos..."
        ):
            result = generate_qa_data(
                load_prompt(),
                source_text,
                api_key,
                selected_model,
                0.0,
                int(max_retries),
                int(wait_time),
            )

        st.session_state.result_json = result
        st.session_state.excel_data = create_excel(
            result,
            selected_config,
        )
        st.session_state.pdf_data = create_pdf(
            result,
            selected_config,
            st.session_state.get("source_name", ""),
        )

        st.success(
            f"✅ Generación completada: "
            f"{len(result['TEST_CASES'])} casos."
        )

    except Exception as exc:
        st.error(f"❌ Error durante la generación: {exc}")


result = st.session_state.result_json

if result:
    st.divider()
    st.subheader("📊 Resultados")

    c1, c2, c3 = st.columns(3)
    c1.metric("Casos", len(result.get("TEST_CASES", [])))
    c2.metric("Alertas", len(result.get("ALERTS", [])))
    c3.metric("Cobertura", len(result.get("COVERAGE", [])))

    # ========================================================
    # EDITOR DE CASOS DE PRUEBA — REVISIÓN QA
    # ========================================================
    st.subheader("✏️ Editar caso de prueba")
    st.caption(
        "Revisa y ajusta los casos generados antes de descargar el Excel o PDF. "
        "El TestCaseId es inmutable para conservar la trazabilidad."
    )

    case_options = []
    for idx, tc in enumerate(result.get("TEST_CASES", [])):
        case_id = safe_text(tc.get("ID"), f"CASO-{idx + 1:05d}")
        case_title = build_case_title(tc, case_id)
        case_options.append(
            f"{case_id} — {case_title[:100]}"
        )

    selected_case_label = st.selectbox(
        "Selecciona el caso que deseas editar",
        case_options,
        key="qa_editor_selected_case",
    )

    selected_index = case_options.index(selected_case_label)
    selected_case = result["TEST_CASES"][selected_index]
    selected_case_id = safe_text(
        selected_case.get("ID"),
        f"CASO-{selected_index + 1:05d}",
    )

    with st.form(
        f"qa_case_editor_form_{selected_index}",
        clear_on_submit=False,
    ):
        st.markdown(f"### {selected_case_id}")
        st.info(
            "El ID no se puede modificar. Los cambios guardados se utilizarán "
            "para regenerar el Excel y el PDF."
        )

        e1, e2 = st.columns(2)

        with e1:
            edited_title = st.text_input(
                "Title",
                value=build_case_title(selected_case, selected_case_id),
            )
            edited_product = st.text_input(
                "Product",
                value=safe_text(selected_case.get("Product")),
            )
            edited_module = st.text_input(
                "Module",
                value=safe_text(selected_case.get("Module")),
            )
            edited_related = st.text_input(
                "Requirement / Use Case",
                value=safe_text(selected_case.get("Related Use Case")),
            )
            edited_criterion = st.text_input(
                "Criterion",
                value=safe_text(selected_case.get("Criterion")),
            )
            edited_scenario_type = st.text_input(
                "Scenario Type",
                value=safe_text(selected_case.get("Scenario Type")),
            )
            edited_validation = st.text_input(
                "Validation Method",
                value=safe_text(selected_case.get("Validation Method")),
            )

        with e2:
            edited_scenario = st.text_area(
                "Scenario",
                value=safe_text(selected_case.get("Scenario")),
                height=90,
            )
            edited_description = st.text_area(
                "Description",
                value=safe_text(selected_case.get("Description")),
                height=110,
            )
            edited_expected = st.text_area(
                "Expected Result",
                value=safe_text(selected_case.get("Expected Result")),
                height=110,
            )
            edited_preconditions = st.text_area(
                "Preconditions",
                value=safe_text(selected_case.get("Preconditions")),
                height=110,
            )

        e3, e4 = st.columns(2)
        with e3:
            edited_coverage = st.text_input(
                "Coverage",
                value=safe_text(selected_case.get("Coverage")),
            )
        with e4:
            edited_effort = st.text_input(
                "Effort",
                value=safe_text(selected_case.get("Effort")),
            )

        st.markdown("#### 🧪 Steps")
        current_steps = safe_steps(selected_case)
        step_rows = []
        for pos, step in enumerate(current_steps, start=1):
            step_rows.append(
                {
                    "Step #": step.get("Step #", pos),
                    "Action": safe_text(step.get("Action")),
                    "Expected value": safe_text(step.get("Expected value")),
                }
            )

        if not step_rows:
            step_rows = [
                {
                    "Step #": 1,
                    "Action": "",
                    "Expected value": "",
                }
            ]

        edited_steps_df = st.data_editor(
            pd.DataFrame(step_rows),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Step #": st.column_config.NumberColumn(
                    "Step #",
                    min_value=1,
                    step=1,
                ),
                "Action": st.column_config.TextColumn(
                    "Action",
                    width="large",
                ),
                "Expected value": st.column_config.TextColumn(
                    "Expected value",
                    width="large",
                ),
            },
            key=f"qa_steps_editor_{selected_index}",
        )

        st.markdown("#### 🚨 Alertas del caso")
        current_alerts = selected_case.get("Alerts", [])
        if not isinstance(current_alerts, list):
            current_alerts = []

        alert_text = "\n".join(
            (
                f"{safe_text(a.get('Alert'))} | "
                f"{safe_text(a.get('Reason'))} | "
                f"{safe_text(a.get('Validation Required'))}"
            )
            for a in current_alerts
            if isinstance(a, dict)
        )

        edited_alerts = st.text_area(
            "Una alerta por línea: Alerta | Razón | Validación requerida",
            value=alert_text,
            height=100,
            help=(
                "Si no hay alertas, deja este campo vacío. "
                "No se agregan columnas nuevas al Excel."
            ),
        )

        save_case = st.form_submit_button(
            "💾 Guardar cambios del caso",
            type="primary",
        )

    if save_case:
        # Guardar campos editados sin alterar el ID.
        selected_case["Title"] = edited_title.strip()
        selected_case["Product"] = edited_product.strip()
        selected_case["Module"] = edited_module.strip()
        selected_case["Related Use Case"] = edited_related.strip()
        selected_case["Criterion"] = edited_criterion.strip()
        selected_case["Scenario Type"] = edited_scenario_type.strip()
        selected_case["Validation Method"] = edited_validation.strip()
        selected_case["Scenario"] = edited_scenario.strip()
        selected_case["Description"] = edited_description.strip()
        selected_case["Expected Result"] = edited_expected.strip()
        selected_case["Preconditions"] = edited_preconditions.strip()
        selected_case["Coverage"] = edited_coverage.strip()
        selected_case["Effort"] = edited_effort.strip()

        # Normalizar Steps y renumerarlos.
        normalized_steps = []
        for pos, row in edited_steps_df.reset_index(drop=True).iterrows():
            action = safe_text(row.get("Action"))
            expected = safe_text(row.get("Expected value"))
            if not action and not expected:
                continue

            normalized_steps.append(
                {
                    "Step #": pos + 1,
                    "Action": action,
                    "Expected value": expected,
                }
            )

        selected_case["Steps"] = normalized_steps

        # Normalizar alertas manuales.
        normalized_alerts = []
        for line in edited_alerts.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = [part.strip() for part in line.split("|", 2)]
            while len(parts) < 3:
                parts.append("")

            normalized_alerts.append(
                {
                    "Alert": parts[0],
                    "Reason": parts[1],
                    "Validation Required": parts[2],
                }
            )

        selected_case["Alerts"] = normalized_alerts

        # Marcar el caso como revisado manualmente sin agregarlo al Excel.
        selected_case["_edited_by_qa"] = True

        # Las salidas siempre se regeneran desde result, incluyendo los cambios.
        st.session_state.excel_data = create_excel(
            result,
            selected_config,
        )
        st.session_state.pdf_data = create_pdf(
            result,
            selected_config,
            st.session_state.get("source_name", ""),
        )

        st.success(
            f"✅ {selected_case_id} actualizado. "
            "Excel y PDF regenerados con los cambios."
        )
        st.rerun()

    st.download_button(
        "📊 Descargar Excel",
        data=st.session_state.excel_data,
        file_name=(
            f"QA_DRAFT_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        ),
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
    )

    st.download_button(
        "📄 Descargar PDF",
        data=st.session_state.pdf_data,
        file_name=(
            f"QA_DRAFT_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        ),
        mime="application/pdf",
    )

    with st.expander("🔎 Ver JSON generado", expanded=False):
        st.json(result)

    st.subheader("🧪 Casos generados")

    preview_rows = []

    for tc in result["TEST_CASES"]:
        preview_rows.append({
            "ID": safe_text(tc.get("ID")),
            "Title": build_case_title(
                tc,
                normalize_case_id(
                    tc.get("ID"),
                    safe_text(tc.get("Module"), "GENERAL"),
                    len(preview_rows) + 1,
                    EXCEL_CONFIGS[selected_config]["title_prefix"],
                ),
            ),
            "Module": safe_text(tc.get("Module")),
            "Scenario Type": safe_text(tc.get("Scenario Type")),
            "Steps": len(safe_steps(tc)),
        })

    st.dataframe(
        pd.DataFrame(preview_rows),
        use_container_width=True,
    )
