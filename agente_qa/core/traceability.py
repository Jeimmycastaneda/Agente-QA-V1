"""Utilidades de trazabilidad CU → CP → cobertura."""

def build_traceability_row(test_case, coverage=None):
    coverage = coverage or {}
    return {
        "TestCaseId": test_case.get("ID", ""),
        "Requirement / Use Case": coverage.get(
            "Requirement / Use Case",
            test_case.get("Related Use Case", ""),
        ),
        "Criterion": coverage.get("Criterion", test_case.get("Criterion", "")),
        "Scenario": coverage.get("Scenario", test_case.get("Scenario", "")),
        "Validation Method": coverage.get(
            "Validation Method",
            test_case.get("Validation Method", ""),
        ),
        "Coverage": coverage.get("Coverage", test_case.get("Coverage", "")),
        "Alerts": coverage.get("Alerts", ""),
    }
