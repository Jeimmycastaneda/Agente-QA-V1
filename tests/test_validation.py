import pytest

from agente_qa.core.validation import parse_json_response, validate_qa_structure


def _valid_case():
    return {
        "ID": "CP-001",
        "Title": "Validar cotización",
        "Description": "Descripción funcional",
        "Preconditions": "Usuario autenticado",
        "Steps": [{"Step #": 1, "Action": "Ingresar", "Expected value": "Se muestra la pantalla"}],
    }


def test_parse_json_response_accepts_fenced_json():
    result = parse_json_response('```json\n{"ok": true}\n```')
    assert result == {"ok": True}


def test_validate_qa_structure_requires_all_sections():
    with pytest.raises(ValueError, match="Falta la clave requerida: TEST_CASES"):
        validate_qa_structure({"USE_CASES": [], "ALERTS": [], "COVERAGE": []})


def test_validate_qa_structure_requires_main_case_fields():
    with pytest.raises(ValueError, match="campo requerido: Title"):
        validate_qa_structure({
            "USE_CASES": [{"ID": "CU-001"}],
            "TEST_CASES": [{"ID": "CP-001"}],
            "ALERTS": [],
            "COVERAGE": [],
        })


def test_validate_qa_structure_normalizes_non_list_alerts_and_coverage():
    data = {
        "USE_CASES": [{"ID": "CU-001"}],
        "TEST_CASES": [_valid_case()],
        "ALERTS": "sin alertas",
        "COVERAGE": "cubierto",
    }
    result = validate_qa_structure(data)
    assert result["ALERTS"] == []
    assert result["COVERAGE"] == []
