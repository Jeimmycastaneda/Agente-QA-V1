import streamlit as st
import pandas as pd

def render_results_section():
    result = st.session_state.get("result_json")
    if not result:
        return
    st.divider()
    st.subheader("📊 Resultados")
    c1, c2, c3 = st.columns(3)
    c1.metric("Casos", len(result.get("TEST_CASES", [])))
    c2.metric("Alertas", len(result.get("ALERTS", [])))
    c3.metric("CUs", len(result.get("USE_CASES", [])))

    rows = []
    for tc in result.get("TEST_CASES", []):
        rows.append({
            "ID": tc.get("ID", ""),
            "Title": tc.get("Title", ""),
            "Module": tc.get("Module", ""),
            "Steps": len(tc.get("Steps", []) or []),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
