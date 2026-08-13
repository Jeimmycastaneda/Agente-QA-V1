"""Literales por defecto para la configuración de export (columnas y presets).

Estos son los valores originales que vivían como constantes en `config.py`
antes de la Fase 3 (externalización a `config/*.yaml`, ver `settings.py`).
Se conservan aquí tal cual, byte a byte, como fallback: si `config/columns.yaml`
o `config/excel_presets.yaml` faltan, `settings.py` cae a estos literales, así
que un `config/` ausente sigue siendo un estado funcional.
"""

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

# ============================================================
# PROVEEDORES DE LLM — literales pre-Fase-4, fallback de
# `config/providers.yaml` vía `settings.load_providers()`/`load_default_provider()`.
# ============================================================
DEFAULT_PROVIDER = "gemini"

PROVIDERS = {
    "gemini": {
        "enabled": True,
        "secret_name": "GEMINI_API_KEY",
        "default_model": "gemini-3.6-flash",
        "max_source_chars": 28000,
        "fallback_models": [
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ],
    },
}
