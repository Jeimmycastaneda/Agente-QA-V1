"""Operaciones funcionales sobre los CP generados.

Estas operaciones no escriben en Azure. Mantienen en memoria la generación actual
para conservar el comportamiento de main sin mezclar estado de UI con integración.
"""
from __future__ import annotations

from copy import deepcopy


def safe_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text.replace("|", "")
    return ""


def calculate_cu_coverage(test_cases, use_cases):
    """Comprueba que cada CU conserve al menos un CP después de una eliminación."""
    cases = test_cases or []
    cus = use_cases or []
    covered = {safe_text(tc.get("Related Use Case")) for tc in cases if isinstance(tc, dict)}
    covered.discard("")
    missing = []
    for cu in cus:
        if not isinstance(cu, dict):
            continue
        cu_id = safe_text(cu.get("ID"), cu.get("id"))
        cu_name = safe_text(cu.get("Name"), cu.get("name"))
        if cu_id and not any(cu_id == value or cu_id in value for value in covered):
            missing.append(cu_id)
        elif not cu_id and cu_name and not any(cu_name in value for value in covered):
            missing.append(cu_name)
    return {"valid": not missing, "missing": missing}


def delete_generated_case(result: dict, index: int) -> dict:
    """Elimina un CP únicamente de la generación en memoria y devuelve una copia."""
    data = deepcopy(result or {})
    cases = data.get("TEST_CASES", []) or []
    if index < 0 or index >= len(cases):
        raise IndexError("Índice de CP fuera de rango.")
    candidate = cases[:index] + cases[index + 1:]
    coverage = calculate_cu_coverage(candidate, data.get("USE_CASES", []))
    if not coverage["valid"]:
        raise ValueError("No se puede eliminar este CP porque dejaría un CU sin cobertura.")
    data["TEST_CASES"] = candidate
    return data


def build_reference_preview_case(reference: dict, generated_case: dict) -> dict:
    """Adapta un CP generado a la estructura observada en un Test Case real.

    Los datos funcionales siguen viniendo de la HU; la referencia solo aporta
    estructura/orden de campos. Nunca copia contenido funcional de Azure.
    """
    case = deepcopy(generated_case or {})
    ref = reference or {}
    case.setdefault("Product", "Cotizadores Web")
    case.setdefault("Module", "Cotizador Autos Colectivos")
    case.setdefault("Preconditions", "Pendiente")
    case.setdefault("Expected Result", "Pendiente")
    case.setdefault("Related Use Case", "Pendiente")
    case.setdefault("Steps", [])
    case["Reference Azure ID"] = safe_text(ref.get("id"))
    case["Reference Azure Title"] = safe_text(ref.get("title"))
    return case
