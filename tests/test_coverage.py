from agente_qa.core.coverage import calculate_cu_coverage
from agente_qa.core.case_management import delete_generated_case


def test_one_cp_per_cu():
    data = calculate_cu_coverage(
        [{"ID": "CP-1", "Related Use Case": "CU-001"}],
        [{"ID": "CU-001", "Name": "Cotizar"}],
    )
    assert data["valid"] is True


def test_missing_cu_is_invalid():
    data = calculate_cu_coverage(
        [{"ID": "CP-1", "Related Use Case": "CU-001"}],
        [{"ID": "CU-001", "Name": "Cotizar"}, {"ID": "CU-002", "Name": "Emitir"}],
    )
    assert data["valid"] is False
    assert data["missing_cu"][0]["id"] == "CU-002"


def test_cp_with_multiple_cu_is_invalid():
    data = calculate_cu_coverage(
        [{"ID": "CP-1", "Related Use Case": "CU-001 y CU-002"}],
        [{"ID": "CU-001", "Name": "Cotizar"}, {"ID": "CU-002", "Name": "Emitir"}],
    )
    assert data["valid"] is False
    assert data["cp_multiple_cu"] == ["CP-1"]


def test_delete_cannot_remove_last_cp_for_a_cu():
    result = {
        "USE_CASES": [{"ID": "CU-001", "Name": "Cotizar"}],
        "TEST_CASES": [{"ID": "CP-1", "Related Use Case": "CU-001"}],
    }
    try:
        delete_generated_case(result, 0)
        assert False, "La eliminación debió ser bloqueada"
    except ValueError as exc:
        assert "dejaría un CU sin cobertura" in str(exc)
