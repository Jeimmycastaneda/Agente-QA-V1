from agente_qa.core.coverage import calculate_cu_coverage

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
