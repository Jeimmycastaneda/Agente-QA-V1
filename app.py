import io
import json
import logging
import os
import re
import time
from datetime import datetime
from html import escape

import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

APP_VERSION = "V12"
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


def create_pdf(data, config_key):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "title", parent=styles["Heading1"], fontSize=16, leading=19
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=11, leading=14
    )
    body = ParagraphStyle(
        "body", parent=styles["BodyText"], fontSize=8, leading=11
    )
    small = ParagraphStyle(
        "small", parent=body, fontSize=7
    )

    story = [
        Paragraph("VERSION PREVIA — DRAFT", small),
        Spacer(1, 12),
        Paragraph("ANÁLISIS DE CASOS DE PRUEBA QA", title),
        Paragraph(f"Formato: {pdf_text(config_key)}", small),
        Paragraph(
            f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            small,
        ),
        Spacer(1, 12),
        HRFlowable(width="100%", thickness=1),
        Spacer(1, 10),
    ]

    cases = data.get("TEST_CASES", [])
    alerts = data.get("ALERTS", [])

    story.extend([
        Paragraph("RESUMEN GENERAL", h2),
        Paragraph(f"Total de Casos de Prueba: {len(cases)}", body),
        Paragraph(f"Total de Alertas Generales: {len(alerts)}", body),
        Spacer(1, 10),
    ])

    if alerts:
        story.append(Paragraph("ALERTAS GENERALES", h2))
        for alert in alerts:
            story.append(
                Paragraph(
                    f"<b>{pdf_text(alert.get('Alert'))}</b>: "
                    f"{pdf_text(alert.get('Reason'))}",
                    body,
                )
            )
            validation = safe_text(alert.get("Validation Required"))
            if validation:
                story.append(
                    Paragraph(
                        f"Validación requerida: {pdf_text(validation)}",
                        small,
                    )
                )
        story.append(Spacer(1, 10))

    story.append(Paragraph("CASOS DE PRUEBA", h2))

    for idx, tc in enumerate(cases, start=1):
        case_id = safe_text(tc.get("ID"), f"CP-{idx:05d}")

        pdf_case_title = build_case_title(tc, case_id)
        story.append(
            Paragraph(
                f"<b>{pdf_text(case_id)}</b> — "
                f"{pdf_text(pdf_case_title)}",
                body,
            )
        )

        story.append(
            Paragraph(
                f"<b>Descripción:</b> {pdf_text(tc.get('Description'))}",
                body,
            )
        )

        story.append(
            Paragraph(
                f"<b>Precondiciones:</b> "
                f"{pdf_text(tc.get('Preconditions'))}",
                body,
            )
        )

        story.append(
            Paragraph(
                f"<b>Escenario:</b> {pdf_text(tc.get('Scenario'))} | "
                f"<b>Tipo:</b> {pdf_text(tc.get('Scenario Type'))} | "
                f"<b>Esfuerzo:</b> {pdf_text(tc.get('Effort'))}",
                body,
            )
        )

        steps = safe_steps(tc)

        if steps:
            rows = [["Step #", "Action", "Expected Value"]]

            for step in steps:
                rows.append([
                    safe_text(step.get("Step #")),
                    Paragraph(pdf_text(step.get("Action")), body),
                    Paragraph(pdf_text(step.get("Expected value")), body),
                ])

            table = Table(
                rows,
                colWidths=[45, 230, 245],
                repeatRows=1,
            )

            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EDF2F7")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))

            story.append(table)
        else:
            story.append(
                Paragraph(
                    "<i>No se definieron steps para este caso.</i>",
                    body,
                )
            )

        case_alerts = tc.get("Alerts", [])

        if isinstance(case_alerts, list) and case_alerts:
            story.append(Paragraph("<b>Alertas del caso:</b>", body))

            for alert in case_alerts:
                story.append(
                    Paragraph(
                        f"• {pdf_text(alert.get('Alert'))}: "
                        f"{pdf_text(alert.get('Reason'))} | "
                        f"{pdf_text(alert.get('Validation Required'))}",
                        small,
                    )
                )

        story.append(Spacer(1, 8))

        if idx < len(cases):
            story.append(HRFlowable(width="100%", thickness=0.5))
            story.append(Spacer(1, 8))

    story.extend([
        Spacer(1, 15),
        HRFlowable(width="100%", thickness=1),
        Paragraph(
            "Documento generado automáticamente. "
            "Requiere revisión y validación por el equipo funcional.",
            small,
        ),
    ])

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
