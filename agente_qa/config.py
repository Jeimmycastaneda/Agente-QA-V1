import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEBUG = os.getenv("AGENTE_QA_DEBUG", "") == "1"

APP_VERSION = "V17"

# ============================================================
# COLUMNAS APROBADAS Y PRESETS DE EXPORT — cargados desde config/*.yaml
# vía agente_qa.settings (Fase 3). Si esos archivos faltan, el loader cae a
# los literales de agente_qa/defaults.py, así que un `config/` ausente sigue
# siendo un estado funcional. Los nombres públicos de abajo no cambian:
# export/excel.py, export/pdf.py y ui/sidebar.py siguen importándolos igual
# que antes de la migración.
# ============================================================
from agente_qa.settings import (  # noqa: E402
    load_columns,
    load_default_provider,
    load_excel_presets,
    load_providers,
)

_cols = load_columns()
AZURE_COLUMNS = list(_cols.azure)
MATRIZ_COLUMNS = list(_cols.matriz)
EXCEL_CONFIGS = {k: p.as_dict() for k, p in load_excel_presets().items()}

# ============================================================
# PROVEEDORES DE LLM — cargados desde config/providers.yaml vía
# agente_qa.settings (Fase 4). `FALLBACK_MODELS` se mantiene por
# compatibilidad con el código que ya lo importa (ui/sidebar.py); ahora se
# deriva del proveedor default en vez de ser un literal Gemini-only.
# ============================================================
PROVIDERS = {k: p.as_dict() for k, p in load_providers().items()}
DEFAULT_PROVIDER = load_default_provider()
FALLBACK_MODELS = list(PROVIDERS[DEFAULT_PROVIDER]["fallback_models"])

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
