"""Operaciones funcionales sobre los CP generados.

No escribe en Azure. Mantiene la lógica de cobertura/eliminación/preview que
existía en main, pero sin depender de Streamlit ni del módulo de integración.
"""
from __future__ import annotations

from copy import deepcopy
import re


def safe_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            text = "\n".join(str(x) for x in value if x is not None).strip()
        else:
            text = str(value).strip()
        if text:
            return text.replace("|", "")
    return ""


def _normalize_cu(value: str) -> str:
    return re.sub(r"\s+", " ", safe_text(value)).strip().casefold()


def _extract_related_cus(test_case: dict) -> list[str]:
    value = (
        test_case.get("Related Use Case")
        or test_case.get("related_use_case")
        or test_case.get("use_case")
        or test_case.get("Requirement / Use Case")
        or test_case.get("Caso de uso relacionado")
        or ""
    )
    if isinstance(value, list):
        parts = [safe_text(x) for x in value if safe_text(x)]
    else:
        parts = [x.strip() for x in re.split(r"[;|,]", str(value)) if x.strip()]

    result = []
    for part in parts:
        match = re.search(r"\b(CU[-_ ]?\d+)\b", part, flags=re.I)
        if match:
            result.append(match.group(1).upper().replace("_", "-").replace(" ", "-"))
        else:
            result.append(part)
    return result


def calculate_cu_coverage(test_cases, use_cases):
    """Mínimo 1 CP por CU y exactamente 1 CU por CP."""
    cu_map = {}
    for cu in use_cases or []:
        if isinstance(cu, dict):
            cid = safe_text(cu.get("ID"), cu.get("id"), cu.get("Use Case ID"), cu.get("CU"))
            name = safe_text(cu.get("Name"), cu.get("name"), cu.get("Title"), cu.get("Description"))
        else:
            cid = safe_text(cu)
            name = cid
        if cid:
            cu_map[_normalize_cu(cid)] = {"id": cid, "name": name or cid}

    covered = {}
    cp_without_cu = []
    cp_multiple_cu = []
    for index, tc in enumerate(test_cases or [], start=1):
        if not isinstance(tc, dict):
            continue
        cp_id = safe_text(tc.get("ID"), f"CP-{index:05d}")
        relations = _extract_related_cus(tc)
        if not relations:
            cp_without_cu.append(cp_id)
            continue
        if len(relations) != 1:
            cp_multiple_cu.append(cp_id)
            continue
        relation = _normalize_cu(relations[0])
        matched = None
        for key, info in cu_map.items():
            if relation == key or relation == _normalize_cu(info["name"]):
                matched = key
                break
        if matched is None:
            cp_without_cu.append(cp_id)
        else:
            covered.setdefault(matched, []).append(cp_id)

    missing = [info for key, info in cu_map.items() if key not in covered]
    total_cu = len(cu_map)
    covered_count = len(covered)
    percentage = round((covered_count / total_cu) * 100, 1) if total_cu else 0.0
    return {
        "total_cu": total_cu,
        "total_cp": len(test_cases or []),
        "covered_cu": covered_count,
        "missing_cu": missing,
        "cp_without_cu": cp_without_cu,
        "cp_multiple_cu": cp_multiple_cu,
        "percentage": percentage,
        "missing": [x["id"] for x in missing],
        "valid": bool(total_cu) and not missing and not cp_without_cu and not cp_multiple_cu,
    }


def delete_generated_case(result: dict, index: int) -> dict:
    """Elimina un CP de la generación actual; nunca toca Azure."""
    data = deepcopy(result or {})
    cases = data.get("TEST_CASES", []) or []
    if index < 0 or index >= len(cases):
        raise IndexError("Índice de CP fuera de rango.")
    candidate = cases[:index] + cases[index + 1:]
    coverage = calculate_cu_coverage(candidate, data.get("USE_CASES", []))
    if not coverage["valid"]:
        raise ValueError("No se puede eliminar este CP porque dejaría un CU sin cobertura.")
    removed_id = safe_text(cases[index].get("ID")) if isinstance(cases[index], dict) else ""
    data["TEST_CASES"] = candidate
    if removed_id and isinstance(data.get("COVERAGE"), list):
        data["COVERAGE"] = [
            row for row in data["COVERAGE"]
            if safe_text(row.get("Test Case")) != removed_id
        ]
    return data


def _reference_sections(description: str) -> dict[str, str]:
    text = safe_text(description)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</?(?:p|div|li|ul|blockquote|strong|b)[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    labels = [
        "Producto:", "Módulo:", "Descripción:",
        "Resultado esperado de la prueba:", "Precondiciones:",
        "Caso de uso relacionado:",
    ]
    result = {}
    for idx, label in enumerate(labels):
        match = re.search(re.escape(label), text, flags=re.I)
        if not match:
            continue
        end = len(text)
        for next_label in labels[idx + 1:]:
            nxt = re.search(re.escape(next_label), text[match.end():], flags=re.I)
            if nxt:
                end = min(end, match.end() + nxt.start())
        result[label] = text[match.end():end].strip(" \n:-")
    return result


def build_reference_preview_case(reference: dict, generated_case: dict) -> dict:
    """Prepara un CP para revisión funcional usando Azure solo como referencia estructural."""
    case = deepcopy(generated_case or {})
    ref = reference or {}
    sections = _reference_sections(ref.get("description", ""))
    case["Product"] = safe_text(case.get("Product"), sections.get("Producto:", ""), "Pendiente")
    case["Module"] = safe_text(case.get("Module"), sections.get("Módulo:", ""), "Pendiente")
    case["Description"] = safe_text(case.get("Description"), case.get("Scenario"), "Pendiente")
    case["Expected Result"] = safe_text(case.get("Expected Result"), sections.get("Resultado esperado de la prueba:", ""), "Pendiente")
    case["Preconditions"] = safe_text(case.get("Preconditions"), sections.get("Precondiciones:", ""), "Pendiente")
    case["Related Use Case"] = safe_text(case.get("Related Use Case"), sections.get("Caso de uso relacionado:", ""), "Pendiente")
    case["Reference Azure ID"] = safe_text(ref.get("id"))
    case["Reference Azure Title"] = safe_text(ref.get("title"))
    return case
