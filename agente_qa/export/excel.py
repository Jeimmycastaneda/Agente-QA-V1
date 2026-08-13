import io

import pandas as pd

from agente_qa.config import AZURE_COLUMNS, EXCEL_CONFIGS, MATRIZ_COLUMNS
from agente_qa.utils import (
    aggregate_case_alerts,
    build_case_title,
    find_coverage,
    normalize_case_id,
    normalize_coverage,
    normalize_validation_method,
    safe_steps,
    safe_text,
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
