"""Configuración QA extraída de main. No altera la lógica de la aplicación original."""

AZURE_COLUMNS = [
    "ID", "Work Item Type", "Title", "Description", "Test Step", "Step Action",
    "Step Expected", "Area Path", "IDPadre", "Tipo Origen Proyecto",
    "Tiempo Real", "Assigned To", "State"
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
        "area_path": "COTIZADORES WEB\\DESARROLLO",
        "assigned_to": "",
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
        "area_path": "COTIZADORES WEB\\DESARROLLO",
        "assigned_to": "",
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
        "area_path": "COTIZADORES WEB\\DESARROLLO",
        "assigned_to": "",
    },
}
