import streamlit as st
import pandas as pd

from agente_qa.core.case_management import calculate_cu_coverage


def render_results_section():
    result = st.session_state.get("result_json")
    if not result:
        return

    st.divider()
    st.subheader("📊 Resultados")
    metrics = calculate_cu_coverage(result.get("TEST_CASES", []), result.get("USE_CASES", []))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos", len(result.get("TEST_CASES", []) or []))
    c2.metric("Alertas", len(result.get("ALERTS", []) or []))
    c3.metric("CUs", len(result.get("USE_CASES", []) or []))
    c4.metric("Cobertura", f"{metrics['percentage']}%")

    if metrics["valid"]:
        st.success("✅ Cobertura completa: cada CU tiene mínimo un CP y cada CP tiene un único CU.")
    else:
        st.error(
            f"🚫 Cobertura incompleta: {metrics['covered_cu']}/{metrics['total_cu']} CU cubiertos. "
            "La exportación y la sincronización deben permanecer bloqueadas hasta corregirla."
        )
        if metrics.get("missing_cu"):
            with st.expander("CU sin Caso de Prueba", expanded=True):
                for cu in metrics["missing_cu"]:
                    st.write(f"• **{cu['id']}** — {cu['name']}")
        if metrics.get("cp_without_cu"):
            st.warning("CP sin CU válido: " + ", ".join(metrics["cp_without_cu"]))
        if metrics.get("cp_multiple_cu"):
            st.warning("CP con más de un CU: " + ", ".join(metrics["cp_multiple_cu"]))

    alerts = result.get("ALERTS", []) or []
    if alerts:
        with st.expander("⚠️ Alertas", expanded=False):
            for alert in alerts:
                if isinstance(alert, dict):
                    name = str(alert.get("Alert", "Alerta")).strip()
                    reason = str(alert.get("Reason", "")).strip()
                    validation = str(alert.get("Validation Required", "")).strip()
                    message = f"{name}: {reason}" if reason else name
                    if validation:
                        message += f" — Validación: {validation}"
                    st.warning(message)
                else:
                    st.warning(str(alert))

    rows = []
    for tc in result.get("TEST_CASES", []) or []:
        rows.append({
            "ID": tc.get("ID", ""),
            "Title": tc.get("Title", ""),
            "Module": tc.get("Module", ""),
            "Related Use Case": tc.get("Related Use Case", ""),
            "Steps": len(tc.get("Steps", []) or []),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
