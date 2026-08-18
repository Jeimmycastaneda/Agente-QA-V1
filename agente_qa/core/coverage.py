import re

def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()

def extract_related_cu(test_case):
    value = (
        test_case.get("Related Use Case")
        or test_case.get("related_use_case")
        or test_case.get("use_case")
        or test_case.get("Requirement / Use Case")
        or test_case.get("Caso de uso relacionado")
        or ""
    )
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if str(x).strip()]
    else:
        parts = [x.strip() for x in re.split(r"[;\n|]", str(value)) if x.strip()]
    result = []
    for part in parts:
        m = re.search(r"\b(CU[-_ ]?\d+)\b", part, re.I)
        if m:
            result.append(m.group(1).upper().replace("_", "-").replace(" ", "-"))
        else:
            result.append(part)
    return result

def calculate_cu_coverage(cases, use_cases):
    cu_map = {}
    for cu in use_cases or []:
        if isinstance(cu, dict):
            cid = str(cu.get("ID") or cu.get("id") or cu.get("Use Case ID") or cu.get("CU") or "").strip()
            name = str(cu.get("Name") or cu.get("name") or cu.get("Title") or cu.get("Description") or "").strip()
        else:
            cid = str(cu).strip()
            name = cid
        if cid:
            cu_map[_norm(cid)] = {"id": cid, "name": name or cid}

    covered = {}
    without = []
    multiple = []

    for i, tc in enumerate(cases or [], 1):
        cp_id = str(tc.get("ID") or f"CP-{i:05d}").strip()
        rel = extract_related_cu(tc)
        if len(rel) == 0:
            without.append(cp_id)
            continue
        if len(rel) != 1:
            multiple.append(cp_id)
            continue
        key = _norm(rel[0])
        matched = None
        for cu_key, info in cu_map.items():
            if key == cu_key or key == _norm(info["name"]):
                matched = cu_key
                break
        if matched is None:
            without.append(cp_id)
        else:
            covered.setdefault(matched, []).append(cp_id)

    missing = [info for key, info in cu_map.items() if key not in covered]
    total = len(cu_map)
    covered_count = len(covered)
    percentage = round(covered_count / total * 100, 1) if total else 0.0
    return {
        "total_cu": total,
        "total_cp": len(cases or []),
        "covered_cu": covered_count,
        "missing_cu": missing,
        "cp_without_cu": without,
        "cp_multiple_cu": multiple,
        "percentage": percentage,
        "valid": bool(total and not missing and not without and not multiple),
    }

def validate_minimum_cu_coverage(data):
    cases = data.get("TEST_CASES", []) or []
    use_cases = data.get("USE_CASES", []) or []
    if not use_cases:
        raise ValueError("GENERACIÓN BLOQUEADA: no se identificaron Casos de Uso.")
    metrics = calculate_cu_coverage(cases, use_cases)
    if not metrics["valid"]:
        detail = []
        if metrics["missing_cu"]:
            detail.append("CU sin CP: " + ", ".join(x["id"] for x in metrics["missing_cu"]))
        if metrics["cp_without_cu"]:
            detail.append("CP sin CU válido: " + ", ".join(metrics["cp_without_cu"]))
        if metrics["cp_multiple_cu"]:
            detail.append("CP con más de un CU: " + ", ".join(metrics["cp_multiple_cu"]))
        raise ValueError(
            f'COBERTURA INCOMPLETA: {metrics["covered_cu"]}/{metrics["total_cu"]} '
            f'({metrics["percentage"]}%). ' + " | ".join(detail)
        )
    return metrics
