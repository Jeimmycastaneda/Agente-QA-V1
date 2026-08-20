"""Proveedor Gemini y generación estructurada de datos QA.

Código funcional copiado desde main. No se toma código de mao-dev-branch.
"""

import json
import os
import re
import time
import streamlit as st

from agente_qa.utils import safe_text
from agente_qa.validation import validate_minimum_cu_coverage

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

MODEL = "gemini-3.6-flash"
FALLBACK_MODELS = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]

SCHEMA = {
    "type": "object",
    "properties": {
        "USE_CASES": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "ID": {"type": "string"}, "Name": {"type": "string"}
            }, "required": ["ID", "Name"]}
        },
        "TEST_CASES": {
            "type": "array",
            "items": {"type": "object", "properties": {
                "ID": {"type": "string"}, "Title": {"type": "string"},
                "Description": {"type": "string"}, "Expected Result": {"type": "string"},
                "Preconditions": {"type": "string"}, "Product": {"type": "string"},
                "Module": {"type": "string"}, "Related Use Case": {"type": "string"},
                "Criterion": {"type": "string"}, "Scenario": {"type": "string"},
                "Scenario Type": {"type": "string"}, "Effort": {"type": "string"},
                "Coverage": {"type": "string"}, "Validation Method": {"type": "string"},
                "Steps": {"type": "array", "items": {"type": "object", "properties": {
                    "Step #": {"type": "integer"}, "Action": {"type": "string"},
                    "Expected value": {"type": "string"}
                }, "required": ["Step #", "Action", "Expected value"]}},
                "Alerts": {"type": "array", "items": {"type": "object", "properties": {
                    "Alert": {"type": "string"}, "Reason": {"type": "string"},
                    "Validation Required": {"type": "string"}
                }, "required": ["Alert", "Reason", "Validation Required"]}}
            }, "required": ["ID", "Title", "Description", "Preconditions", "Steps"]}
        },
        "ALERTS": {"type": "array", "items": {"type": "object", "properties": {
            "Alert": {"type": "string"}, "Reason": {"type": "string"},
            "Validation Required": {"type": "string"}
        }, "required": ["Alert", "Reason", "Validation Required"]}},
        "COVERAGE": {"type": "array", "items": {"type": "object", "properties": {
            "Requirement / Use Case": {"type": "string"}, "Criterion": {"type": "string"},
            "Scenario": {"type": "string"}, "Test Case": {"type": "string"},
            "Validation Method": {"type": "string"}, "Coverage": {"type": "string"},
            "Alerts": {"type": "string"}
        }, "required": ["Requirement / Use Case", "Criterion", "Scenario", "Test Case"]}}
    },
    "required": ["USE_CASES", "TEST_CASES", "ALERTS", "COVERAGE"]
}

DETAILED_QA_ADDENDUM = """
REGLAS OBLIGATORIAS DE NIVEL DE DETALLE PARA LOS CASOS DE PRUEBA

El Caso de Prueba debe reflejar con alto nivel de fidelidad el Caso de Uso (CU)
relacionado. NO generes CP básicos, genéricos ni resumidos.

1. TRAZABILIDAD CU -> CP
- Identifica el CU exacto que sustenta cada CP y usa su contenido completo como fuente principal del caso.
- Related Use Case debe indicar el ID y, cuando esté disponible, el nombre del CU.
- Cada CP debe corresponder a EXACTAMENTE un CU.
- Debe existir como mínimo un CP por cada CU identificado.
- Si un CU requiere varios escenarios funcionales realmente distintos, puede tener varios CP.

2. DESCRIPCIÓN SUPER DETALLADA
La Description del CP debe explicar el escenario funcional completo. Incluye, cuando exista en la fuente:
- objetivo y contexto del CU;
- usuario, perfil o rol involucrado;
- módulo, opción, pantalla o funcionalidad;
- condiciones iniciales y precondiciones;
- datos/campos que deben diligenciarse o consultarse;
- reglas de negocio y condiciones;
- estados iniciales/finales;
- restricciones, límites y validaciones;
- comportamiento esperado;
- resultado final.

Si para que el CP sea autónomo y ejecutable es necesario incorporar el contenido completo o casi completo del CU, HAZLO.

2A. ESTRUCTURA OBLIGATORIA DE LA DESCRIPTION PARA AZURE DEVOPS
- La Description del Excel debe contener la descripción funcional completa del CP.
- Debe conservar el detalle funcional necesario para que el Test Case sea autosuficiente.
- Debe presentar en este orden: Producto, Módulo, Descripción, Resultado esperado de la prueba, Precondiciones y Caso de uso relacionado.
- No inventar datos. Si un dato no está definido, indicarlo como pendiente/por validar.

3. PASOS COMPLETOS Y EJECUTABLES
- Los Steps deben cubrir TODO el flujo necesario.
- Cada acción funcional relevante debe aparecer como paso cuando sea necesario.
- Cada paso debe ser concreto y verificable: acción + resultado esperado.
- No conviertas cada paso en un CP.

4. FIDELIDAD Y NO INVENCIÓN
- Usa exclusivamente la documentación proporcionada como fuente de verdad.
- No inventes usuarios, rutas, URLs, botones, mensajes, campos, valores, reglas, permisos o datos.
- Cuando la fuente no defina un dato necesario, conserva la incertidumbre y genera ALERTA.

5. CALIDAD MÍNIMA DEL CP
Un CP es insuficiente si su Description, Preconditions, Expected Result o Steps son tan genéricos que no permiten reconocer qué parte específica del CU se valida.

6. OPCIONES POSIBLES DE NAVEGACIÓN SIN INVENTAR RUTAS
Cuando el CU no indique navegación exacta, puede redactarse una opción posible solo si existe evidencia suficiente en la documentación. No inventar botones, URLs, IDs, pantallas, menús o rutas.

6. EXCEL AZURE
- Un CP debe exportarse como un bloque: cabecera + todas sus filas de Steps.
- Tipo Origen Proyecto = Proyecto.
- Area Path = COTIZADORES WEB\\DESARROLLO.
- No crear un CP por cada Step.
"""


def load_prompt():
    path = "prompt_qa.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            return content
    organized_path = os.path.join("prompts", "prompt_qa.txt")
    if os.path.exists(organized_path):
        with open(organized_path, "r", encoding="utf-8") as f:
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
    for key in ("USE_CASES", "TEST_CASES", "ALERTS", "COVERAGE"):
        if key not in data:
            raise ValueError(f"Falta la clave requerida: {key}")
    if not isinstance(data["USE_CASES"], list) or not data["USE_CASES"]:
        raise ValueError("Gemini no devolvió los Casos de Uso identificados.")
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
    return str(exc)[:1800]


def _generate_once(client, model_name, full_prompt):
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SCHEMA,
        max_output_tokens=32768,
    )
    return client.models.generate_content(model=model_name, contents=full_prompt, config=config)


def generate_qa_data(prompt_text, source_content, api_key, model_name, temperature=0.1, max_retries=2, initial_wait=10):
    if genai is None:
        raise RuntimeError("No está instalada la librería google-genai.")
    if not api_key:
        raise ValueError("API Key no configurada.")
    if not source_content.strip():
        raise ValueError("Fuente de información vacía.")

    max_source_chars = 120000
    if len(source_content) > max_source_chars:
        source_content = source_content[:max_source_chars] + "\n...[DOCUMENTO EXCEDE EL LÍMITE DE SEGURIDAD; PRIORIZAR LOS CU Y SU CONTEXTO FUNCIONAL]"

    full_prompt = (
        prompt_text
        + "\n\n==================== ADDENDUM OBLIGATORIO DE CALIDAD ====================\n"
        + DETAILED_QA_ADDENDUM
        + "\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n"
        + source_content
        + "\n\n==================== REGLA DE PRIORIDAD ====================\n"
        "La HU/documentación actual es la única fuente de verdad funcional. "
        "Usa el CU completo como fuente principal del CP y conserva sus detalles. "
        "Debe existir mínimo un CP por cada CU y cada CP debe corresponder a un solo CU. "
        "No conviertas Steps en CP. "
        "Related Use Case debe conservar el ID del CU. "
        "No inventar un CU ni dejarlo como None si existe un título de CU en la fuente. "
        "Cuando la navegación no esté definida explícitamente, no inventes botones, URLs, menús, pantallas ni rutas.\n"
        "\n\n==================== REGLA DE SALIDA ====================\n"
        "Devuelve exclusivamente JSON válido que cumpla el esquema solicitado. "
        "No agregues explicaciones fuera del JSON."
    )

    client = genai.Client(api_key=api_key)
    candidates = []
    for candidate in [model_name] + FALLBACK_MODELS:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    errors = []
    for candidate in candidates:
        for attempt in range(max_retries + 1):
            try:
                response = _generate_once(client, candidate, full_prompt)
                response_text = (response.text or "").strip()
                if not response_text:
                    raise RuntimeError(f"{candidate}: Gemini devolvió una respuesta vacía.")
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
                    if not match:
                        raise RuntimeError(f"{candidate}: la respuesta no es JSON válido. Respuesta: {response_text[:1200]}")
                    data = json.loads(match.group(1))
                validated = validate_qa_structure(data)
                validate_minimum_cu_coverage(validated)
                st.session_state.quota_exceeded = False
                st.session_state.retry_count = 0
                return validated
            except Exception as exc:
                detail = _extract_error_detail(exc)
                errors.append(f"{candidate} / intento {attempt + 1}: {detail}")
                error_text = detail.lower()
                is_quota = "429" in detail or "quota" in error_text or "rate limit" in error_text or "resource exhausted" in error_text
                is_retryable_internal = "500" in detail or "internal" in error_text or "503" in detail or "unavailable" in error_text or "deadline" in error_text or "timeout" in error_text
                if is_quota:
                    st.session_state.quota_exceeded = True
                    st.session_state.retry_count = attempt + 1
                    break
                is_bad_request = "400" in detail or "invalid argument" in error_text or "invalid_argument" in error_text or "unsupported" in error_text
                if attempt < max_retries and is_retryable_internal:
                    time.sleep(initial_wait * (attempt + 1))
                    continue
                if is_bad_request or is_retryable_internal:
                    break
                break

    raise RuntimeError(
        "Gemini no pudo completar la generación con los modelos probados.\n\nDetalle técnico: "
        + "\n".join(errors[-8:])
    )
