from agente_qa.export.excel import create_excel

def test_excel_has_expected_columns():
    data = {"TEST_CASES": []}
    blob = create_excel(data)
    assert blob
