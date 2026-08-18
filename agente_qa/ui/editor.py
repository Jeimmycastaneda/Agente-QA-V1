"""Editor Streamlit separado.

La lógica visual del editor se conserva como módulo independiente para que app.py
no contenga el formulario completo.
"""

from editor_azure import render_azure_style_editor, delete_test_case

def render_editor_section():
    import streamlit as st
    result = st.session_state.get("result_json")
    if not result:
        return
    st.subheader("✏️ Editar caso de prueba")
    cases = result.get("TEST_CASES", [])
    if not cases:
        st.info("No hay Test Cases para editar.")
        return
    labels = [f"{tc.get('ID', 'CP')} — {tc.get('Title', '')[:100]}" for tc in cases]
    label = st.selectbox("Selecciona el caso que deseas editar", labels, key="qa_editor_selected_case")
    index = labels.index(label)
    if render_azure_style_editor(cases[index], index) == "saved":
        st.session_state.excel_data = None
        st.session_state.pdf_data = None
        st.success("✅ Caso actualizado.")
