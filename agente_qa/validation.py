"""Validaciones de cobertura y reglas QA.

Código copiado desde main. mao-dev-branch solo aporta la estructura de carpetas.
"""

import re
import streamlit as st


def _normalize_cu(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _extract_related_cu(tc):
    """Extrae un único CU desde Related Use Case."""
    value = (
        tc.get("Related Use Case")
        or tc.get("related_use_case")
        or tc.get("use_case")
        or tc.get("Requirement / Use Case")
        or tc.get("Caso de uso relacionado")
        or ""
    )
    if isinstance(value, list):
        raw_parts = [str(x).strip() for x in value if str(x).strip()]
    else:
        raw_parts = [x.strip() for x in re.split(r"[;\n|]", str(value)) if x.strip()]

    results = []
    for part in raw_parts:
        match = re.search(r"\b(CU[-_ ]?\d+)\b", part, flags=re.IGNORECASE)
        if match:
            results.append(match.group(1).upper().replace("_", "-").replace(" ", "-"))
        else:
            results.append(part)
    return results


def calculate_cu_coverage(cases, identified_use_cases):
    """Mínimo 1 CP por cada CU y exactamente 1 CU por CP."""
    cu_map = {}
    for cu in identified_use_cases or []:
        if isinstance(cu, dict):
            cid = str(
                cu.get("ID") or cu.get("id") or
                cu.get("Use Case ID") or cu.get("CU") or ""
            ).strip()
            name = str(
                cu.get("Name") or cu.get("name") or
                cu.get("Title") or cu.get("Description") or ""
            ).strip()
        else:
            cid = str(cu).strip()
            name = cid
        if cid:
            cu_map[_normalize_cu(cid)] = {"id": cid, "name": name or cid}

    covered = {}
    cp_without_cu = []
    cp_multiple_cu = []

    for index, tc in enumerate(cases or [], start=1):
        cp_id = str(tc.get("ID") or f"CP-{index:05d}").strip()
        relations = _extract_related_cu(tc)

        if len(relations) == 0:
            cp_without_cu.append(cp_id)
            continue
        if len(relations) != 1:
            cp_multiple_cu.append(cp_id)
            continue

        rel = _normalize_cu(relations[0])
        matched = None
        for cu_key, cu_info in cu_map.items():
            if rel == cu_key or rel == _normalize_cu(cu_info["name"]):
                matched = cu_key
                break

        if matched is None:
            cp_without_cu.append(cp_id)
        else:
            covered.setdefault(matched, []).append(cp_id)

    missing = [info for key, info in cu_map.items() if key not in covered]
    total_cu = len(cu_map)
    total_cp = len(cases or [])
    covered_count = len(covered)
    percentage = round((covered_count / total_cu) * 100, 1) if total_cu else 0.0

    return {
        "total_cu": total_cu,
        "total_cp": total_cp,
        "covered_cu": covered_count,
        "missing_cu": missing,
        "cp_without_cu": cp_without_cu,
        "cp_multiple_cu": cp_multiple_cu,
        "percentage": percentage,
        "valid": (
            total_cu > 0
            and not missing
            and not cp_without_cu
            and not cp_multiple_cu
        ),
    }


def validate_minimum_cu_coverage(data):
    """Bloquea cualquier resultado que no cubra todos los CU."""
    cases = data.get("TEST_CASES", []) or []
    use_cases = data.get("USE_CASES", []) or []

    if not use_cases:
        raise ValueError(
            "GENERACIÓN BLOQUEADA: Gemini no devolvió la lista completa de Casos de Uso (USE_CASES)."
        )

    metrics = calculate_cu_coverage(cases, use_cases)
    if not metrics["valid"]:
        missing = ", ".join(f'{x["id"]} - {x["name"]}' for x in metrics["missing_cu"])
        details = []
        if missing:
            details.append("CU sin CP: " + missing)
        if metrics["cp_without_cu"]:
            details.append("CP sin CU válido: " + ", ".join(metrics["cp_without_cu"]))
        if metrics["cp_multiple_cu"]:
            details.append("CP con más de un CU: " + ", ".join(metrics["cp_multiple_cu"]))
        raise ValueError(
            f'COBERTURA INCOMPLETA: {metrics["covered_cu"]}/{metrics["total_cu"]} CU cubiertos '
            f'({metrics["percentage"]}%). ' + " | ".join(details)
        )
    return metrics


def render_cu_coverage(metrics):
    st.markdown("### 📊 Cobertura mínima por Caso de Uso")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CU identificados", metrics["total_cu"])
    c2.metric("CP generados", metrics["total_cp"])
    c3.metric("CU cubiertos", metrics["covered_cu"])
    c4.metric("Cobertura", f'{metrics["percentage"]}%')
    if metrics["valid"]:
        st.success("✅ Cobertura completa: cada CU tiene mínimo un CP.")
    else:
        st.error(
            f'🔴 Cobertura incompleta: {metrics["covered_cu"]}/{metrics["total_cu"]} CU cubiertos. '
            f'Faltan {len(metrics["missing_cu"])} CU.'
        )
        if metrics["missing_cu"]:
            with st.expander("Ver CU sin Caso de Prueba", expanded=True):
                for cu in metrics["missing_cu"]:
                    st.write(f'• **{cu["id"]}** — {cu["name"]}')
        if metrics["cp_without_cu"]:
            st.warning("CP sin CU válido: " + ", ".join(metrics["cp_without_cu"]))
        if metrics["cp_multiple_cu"]:
            st.warning(
                "CP relacionados con más de un CU: " + ", ".join(metrics["cp_multiple_cu"])
            )
