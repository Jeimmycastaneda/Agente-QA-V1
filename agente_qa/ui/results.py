import streamlit as st
import pandas as pd


def render_results_section():
    result = st.session_state.get("result_json")
    if not result:
        return

    st.divider()
    st.subheader("📊 Resultados")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Casos", len(result.get("TEST_CASES", []) or []))
    c2.metric("Alertas", len(result.get("ALERTS", []) or []))
    c3.metric("CUs", len(result.get("USE_CASES", []) or []))
    c4.metric("Coberturas", len(result.get("COVERAGE", []) or []))

    alerts = result.get("ALERTS", []) or []
    if alerts:
        with st.expander("⚠️ Alertas", expanded=False):
            for alert in alerts:
                if isinstance(alert, dict):
                    name = str(alert.get("Alert", "Alerta")).strip()
                    reason = str(alert.get("Reason", "")).strip()
                    st.warning(f"{name}: {reason}" if reason else name)
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
