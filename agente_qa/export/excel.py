"""Exportación Excel compatible con el formato Azure DevOps de main."""
from __future__ import annotations

import io
import re
import pandas as pd

AZURE_COLUMNS = ["ID", "Work Item Type", "Title", "Description", "Test Step", "Step Action", "Step Expected", "Area Path", "IDPadre", "Tipo Origen Proyecto", "Tiempo Real", "Assigned To", "State"]
MATRIZ_COLUMNS = ["TestCaseId", "Title", "Requirement / Use Case", "Criterion", "Scenario", "Scenario Type", "Description", "Preconditions", "Validation Method", "Coverage", "Alerts", "Effort"]
EXCEL_CONFIGS = {
    "Autos Colectivos": {"title_prefix": "CP-AC-", "area_path": r"COTIZADORES WEB\DESARROLLO", "assigned_to": "", "state": "Design"},
    "Siniestros Fasecolda": {"title_prefix": "CP-ACSF-", "area_path": r"COTIZADORES WEB\DESARROLLO", "assigned_to": "", "state": "Design"},
    "General QA": {"title_prefix": "CP-AC-", "area_path": r"COTIZADORES WEB\DESARROLLO", "assigned_to": "", "state": "Design"},
}


def _text(*values, default=""):
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = "\n".join(str(x) for x in value if x is not None)
        elif isinstance(value, dict):
            value = str(value)
        value = str(value).strip()
        if value:
            return value.replace("|", "")
    return default


def _module_token(module, title="", scenario=""):
    raw = _text(module, title, scenario, "GENERAL")
    raw = re.sub(r"[^A-Za-z0-9]+", " ", raw).strip().upper()
    words = raw.split()
    if not words:
        return "GENERAL"
    return words[0][:12] if len(words) == 1 else "".join(w[0] for w in words)[:8]


def _case_id(raw_id, module, index, prefix):
    raw = _text(raw_id)
    return raw.upper() if re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}", raw, re.I) else f"{prefix}{_module_token(module)}-{index:05d}"


def _title(tc, case_id):
    title = re.sub(r"\s+", " ", _text(tc.get("Title"))).strip()
    if not title or title.upper() == case_id.upper() or re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}", title, re.I):
        title = re.sub(r"\s+", " ", _text(tc.get("Scenario"), tc.get("Description"), tc.get("Related Use Case"), default=f"Caso de prueba {case_id}")).strip()
    return title if title.upper().startswith(case_id.upper()) else f"{case_id} - {title}"


def _normalize_description(description):
    text = _text(description).replace("\r\n", "\n").replace("\r", "\n")
    if not text:
        return ""
    labels = ["Producto:", "Módulo:", "Descripción:", "Resultado esperado de la prueba:", "Precondiciones:", "Caso de uso relacionado:"]
    for label in labels:
        text = re.sub(rf"\s*{re.escape(label)}\s*", f"\n{label} ", text, count=1, flags=re.I)
    text = re.sub(r"(?m)^\s*[•●▪◦]\s*", "- ", text)
    text = re.sub(r"(?m)^\s*[o]\s+", "- ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    for label in labels:
        text = re.sub(rf"(?m)^{re.escape(label)}\s*", f"**{label}** ", text)
    for label in labels[1:]:
        text = re.sub(rf"\n\*\*{re.escape(label)}\*\*", f"\n\n**{label}**", text)
    return re.sub(r"[ \t]*\|[ \t]*(?=\n|$)", "", text).strip()


def _description(tc, data):
    fields = [
        ("Producto", _text(tc.get("Product"), data.get("PRODUCT"), default="Pendiente")),
        ("Módulo", _text(tc.get("Module"), default="Pendiente")),
        ("Descripción", _text(tc.get("Description"), tc.get("Scenario"), default="Pendiente")),
        ("Resultado esperado de la prueba", _text(tc.get("Expected Result"), tc.get("ExpectedResult"), tc.get("Resultado esperado de la prueba"), default="Pendiente")),
        ("Precondiciones", _text(tc.get("Preconditions"), default="Pendiente")),
        ("Caso de uso relacionado", _text(tc.get("Related Use Case"), tc.get("RelatedUseCase"), tc.get("Caso de uso relacionado"), default="Pendiente")),
    ]
    return _normalize_description("\n\n".join(f"{label}: {value}" for label, value in fields))


def _coverage_for_case(data, tc):
    case_id = _text(tc.get("ID"))
    related = _text(tc.get("Related Use Case"), tc.get("RelatedUseCase"))
    for row in data.get("COVERAGE", []) or []:
        if not isinstance(row, dict):
            continue
        row_case = _text(row.get("Test Case"), row.get("TestCaseId"))
        row_use_case = _text(row.get("Requirement / Use Case"))
        if (case_id and row_case == case_id) or (related and row_use_case == related):
            return row
    return {}


def _case_alerts(data, tc, coverage):
    value = _text(coverage.get("Alerts"), tc.get("Alerts"))
    if value:
        return value
    alerts = []
    for alert in data.get("ALERTS", []) or []:
        if not isinstance(alert, dict):
            continue
        name = _text(alert.get("Alert"), alert.get("Type"))
        reason = _text(alert.get("Reason"), alert.get("Description"))
        if name:
            alerts.append(f"{name}: {reason}" if reason else name)
    return " | ".join(alerts) if alerts else "Sin Alertas"


def create_excel(data, config_key="Autos Colectivos"):
    config = EXCEL_CONFIGS.get(config_key, EXCEL_CONFIGS["Autos Colectivos"])
    azure_rows, matriz_rows = [], []
    for idx, tc in enumerate(data.get("TEST_CASES", []) or [], 1):
        if not isinstance(tc, dict):
            continue
        module = _text(tc.get("Module"), default="GENERAL")
        case_id = _case_id(tc.get("ID"), module, idx, config["title_prefix"])
        title = _title(tc, case_id)
        description = _description(tc, data)
        steps = tc.get("Steps") if isinstance(tc.get("Steps"), list) else []
        coverage = _coverage_for_case(data, tc)
        alerts = _case_alerts(data, tc, coverage)

        # Igual que main: IDPadre queda vacío en el Excel de importación.
        azure_rows.append({
            "ID": "", "Work Item Type": "Test Case", "Title": title, "Description": description,
            "Test Step": "", "Step Action": "", "Step Expected": "", "Area Path": config["area_path"],
            "IDPadre": "", "Tipo Origen Proyecto": "Proyecto", "Tiempo Real": "", "Assigned To": config["assigned_to"], "State": config["state"],
        })

        export_steps = steps or [{"Step #": 1, "Action": "Información insuficiente para definir el paso.", "Expected value": "Validar con el equipo funcional antes de ejecutar."}]
        for n, step in enumerate(export_steps, 1):
            if not isinstance(step, dict):
                continue
            azure_rows.append({
                "ID": "", "Work Item Type": "", "Title": "", "Description": "", "Test Step": step.get("Step #", n),
                "Step Action": _text(step.get("Action"), step.get("action"), default="Acción no definida"),
                "Step Expected": _text(step.get("Expected value"), step.get("Expected"), step.get("expected"), default="Resultado esperado no definido"),
                "Area Path": "", "IDPadre": "", "Tipo Origen Proyecto": "", "Tiempo Real": "", "Assigned To": "", "State": "",
            })

        matriz_rows.append({
            "TestCaseId": case_id,
            "Title": title,
            "Requirement / Use Case": _text(coverage.get("Requirement / Use Case"), tc.get("Related Use Case")),
            "Criterion": _text(coverage.get("Criterion"), tc.get("Criterion")),
            "Scenario": _text(coverage.get("Scenario"), tc.get("Scenario"), tc.get("Description")),
            "Scenario Type": _text(tc.get("Scenario Type"), default="No definido"),
            "Description": description,
            "Preconditions": _text(tc.get("Preconditions")),
            "Validation Method": _text(coverage.get("Validation Method"), tc.get("Validation Method"), default="Pendiente"),
            "Coverage": _text(coverage.get("Coverage"), tc.get("Coverage"), default="Pendiente"),
            "Alerts": alerts,
            "Effort": _text(tc.get("Effort"), default="No definido"),
        })

    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(azure_rows, columns=AZURE_COLUMNS).to_excel(writer, sheet_name="Azure Import", index=False)
        pd.DataFrame(matriz_rows, columns=MATRIZ_COLUMNS).to_excel(writer, sheet_name="Matriz QA", index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for column_cells in ws.columns:
                letter = column_cells[0].column_letter
                max_len = max(len(str(c.value or "")) for c in column_cells)
                ws.column_dimensions[letter].width = min(max(max_len + 2, 12), 60)
    out.seek(0)
    return out.getvalue()
