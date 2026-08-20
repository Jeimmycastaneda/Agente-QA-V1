"""Utilidades de texto, títulos, IDs y trazabilidad QA.

Código copiado desde main. mao-dev-branch solo aporta la estructura.
"""

import json
import re


def _ui_text(value, default=""):
    """Texto seguro para UI: nunca muestra el literal None."""
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def safe_text(value, default="", *fallbacks):
    """Convierte valores a texto y permite valores de respaldo."""
    candidates = (value, default, *fallbacks)
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, (dict, list)):
            text = json.dumps(candidate, ensure_ascii=False).strip()
        else:
            text = str(candidate).strip()
        if text:
            return text
    return ""


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


def _remove_trailing_pipe(value):
    """Elimina únicamente un pipe sobrante al final."""
    text = safe_text(value)
    return re.sub(r"\s*\|\s*$", "", text).rstrip()


def build_azure_description(product, module, description, expected, preconditions, related_use_case):
    """Construye la estructura aprobada de Description para Azure sin inventar datos."""
    product = _remove_trailing_pipe(product)
    module = _remove_trailing_pipe(module)
    desc = _remove_trailing_pipe(description)
    expected = _remove_trailing_pipe(expected)
    preconditions = _remove_trailing_pipe(preconditions)
    related_use_case = _remove_trailing_pipe(related_use_case)

    desc = re.sub(r"(?mi)^\s*Descripción:\s*", "", desc, count=1).strip()
    return (
        f"Producto: {product or 'Pendiente'}\n\n"
        f"Módulo: {module or 'Pendiente'}\n\n"
        f"Descripción: {desc or 'Pendiente'}\n\n"
        f"Resultado esperado de la prueba: {expected or 'Pendiente'}\n\n"
        f"Precondiciones: {preconditions or 'Pendiente'}\n\n"
        f"Caso de uso relacionado: {related_use_case or 'Pendiente'}"
    )


def format_description_for_azure(description):
    """Formatea Description para Azure DevOps sin cambiar su contenido funcional."""
    text = safe_text(description).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""

    text = re.sub(r"[ \t]+", " ", text)
    labels = [
        "Producto:",
        "Módulo:",
        "Descripción:",
        "Resultado esperado de la prueba:",
        "Precondiciones:",
        "Caso de uso relacionado:",
    ]
    for label in labels:
        text = re.sub(rf"\s*{re.escape(label)}\s*", f"\n{label} ", text, count=1)

    text = re.sub(r"(?m)^\s*[•●▪◦]\s*", "- ", text)
    text = re.sub(r"(?m)^\s*[o]\s+", "- ", text)
    text = re.sub(r"\n\s*[-–—]\s*", "\n- ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    for label in labels:
        text = re.sub(rf"(?m)^{re.escape(label)}\s*", f"**{label}** ", text)
    for label in labels[1:]:
        text = re.sub(rf"\n\*\*{re.escape(label)}\*\*", f"\n\n**{label}**", text)
    text = re.sub(r"^\*\*Producto:\*\*", "**Producto:**", text)
    return text.strip()


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
    """Garantiza que Title sea funcional y no solamente el ID del CP."""
    raw_title = safe_text(tc.get("Title"))
    normalized_title = re.sub(r"\s+", " ", raw_title).strip()
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
