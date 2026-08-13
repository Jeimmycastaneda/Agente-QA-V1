import io
import json
from pathlib import Path

import pandas as pd
import pytest

from agente_qa.config import AZURE_COLUMNS, MATRIZ_COLUMNS
from agente_qa.export.excel import create_excel

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"

_SLUGS = {
    "Autos Colectivos": "autos_colectivos",
    "Siniestros Fasecolda": "siniestros_fasecolda",
    "General QA": "general_qa",
}


def load_golden(preset, sheet):
    slug = _SLUGS[preset]
    path = GOLDEN_DIR / f"{slug}_{sheet}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_azure_columns_are_frozen():
    """Contract with the approved Azure DevOps import format. If this fails,
    the import breaks silently on upload. The duplicated literal list is
    intentional -- that duplication is the point of the test."""
    assert AZURE_COLUMNS == [
        "TestCaseId", "Title", "TestStep", "StepAction", "StepExpected",
        "TestPointId", "Configuration", "Tester", "Outcome", "Comment",
    ]


def test_matriz_columns_are_frozen():
    assert MATRIZ_COLUMNS == [
        "TestCaseId", "Title", "Requirement / Use Case", "Criterion", "Scenario",
        "Scenario Type", "Description", "Preconditions", "Validation Method",
        "Coverage", "Alerts", "Effort",
    ]


@pytest.mark.parametrize("preset", ["Autos Colectivos", "Siniestros Fasecolda", "General QA"])
def test_excel_matches_golden(sample_result, preset):
    excel_bytes = create_excel(sample_result, preset)
    df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name=0)
    assert list(df.columns) == AZURE_COLUMNS
    assert df.fillna("").astype(str).values.tolist() == load_golden(preset, "azure")


def test_excel_matriz_matches_golden(sample_result):
    excel_bytes = create_excel(sample_result, "Autos Colectivos")
    df = pd.read_excel(io.BytesIO(excel_bytes), sheet_name="Matriz QA")
    assert list(df.columns) == MATRIZ_COLUMNS
    assert df.fillna("").astype(str).values.tolist() == load_golden("Autos Colectivos", "matriz")


def test_excel_sheet_names(sample_result):
    excel_bytes = create_excel(sample_result, "Autos Colectivos")
    xls = pd.ExcelFile(io.BytesIO(excel_bytes))
    assert xls.sheet_names == ["Azure Import", "Matriz QA"]


def test_excel_returns_nonempty_bytes(sample_result):
    excel_bytes = create_excel(sample_result, "General QA")
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0
