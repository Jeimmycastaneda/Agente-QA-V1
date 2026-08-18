"""Exportación Excel separada del núcleo QA.

Contrato de columnas aprobado para esta rama experimental.
"""

import io
import pandas as pd

AZURE_COLUMNS = [
    "ID", "Work Item Type", "Title", "Description", "Test Step",
    "Step Action", "Step Expected", "Area Path", "IDPadre",
    "Tipo Origen Proyecto", "Tiempo Real", "Assigned To", "State"
]

MATRIZ_COLUMNS = [
    "TestCaseId", "Title", "Requirement / Use Case", "Criterion", "Scenario",
    "Scenario Type", "Description", "Preconditions", "Validation Method",
    "Coverage", "Alerts", "Effort"
]

def create_excel(data, config_key="Autos Colectivos"):
    rows = []
    matriz = []
    for tc in data.get("TEST_CASES", []):
        rows.append({
            "ID": "",
            "Work Item Type": "Test Case",
            "Title": tc.get("Title", ""),
            "Description": tc.get("Description", ""),
            "Test Step": "",
            "Step Action": "",
            "Step Expected": "",
            "Area Path": r"COTIZADORES WEB\DESARROLLO",
            "IDPadre": "",
            "Tipo Origen Proyecto": "Proyecto",
            "Tiempo Real": "",
            "Assigned To": "",
            "State": "Design",
        })
        for i, step in enumerate(tc.get("Steps", []) or [], 1):
            rows.append({
                "ID": "", "Work Item Type": "", "Title": "", "Description": "",
                "Test Step": step.get("Step #", i),
                "Step Action": step.get("Action", ""),
                "Step Expected": step.get("Expected value", ""),
                "Area Path": "", "IDPadre": "", "Tipo Origen Proyecto": "",
                "Tiempo Real": "", "Assigned To": "", "State": "",
            })
        matriz.append({
            "TestCaseId": tc.get("ID", ""),
            "Title": tc.get("Title", ""),
            "Requirement / Use Case": tc.get("Related Use Case", ""),
            "Criterion": tc.get("Criterion", ""),
            "Scenario": tc.get("Scenario", ""),
            "Scenario Type": tc.get("Scenario Type", ""),
            "Description": tc.get("Description", ""),
            "Preconditions": tc.get("Preconditions", ""),
            "Validation Method": tc.get("Validation Method", ""),
            "Coverage": tc.get("Coverage", ""),
            "Alerts": tc.get("Alerts", ""),
            "Effort": tc.get("Effort", ""),
        })
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        pd.DataFrame(rows, columns=AZURE_COLUMNS).to_excel(writer, sheet_name="Azure Import", index=False)
        pd.DataFrame(matriz, columns=MATRIZ_COLUMNS).to_excel(writer, sheet_name="Matriz QA", index=False)
    out.seek(0)
    return out.getvalue()
