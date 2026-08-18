import streamlit as st
from agente_qa.extraction.document import extract_source

def render_document_section():
    st.subheader("📁 Carga de Documento")
    st.info("Formatos: TXT, MD, PDF, DOCX, XLSX/CSV. PDF escaneado requiere OCR.")
    uploaded = st.file_uploader(
        "Arrastra o selecciona un documento",
        type=["txt", "md", "pdf", "docx", "xlsx", "xls", "csv"],
    )
    if uploaded and st.session_state.source_name != uploaded.name:
        try:
            with st.spinner(f"Procesando {uploaded.name}..."):
                content = extract_source(uploaded)
            st.session_state.source_content = content
            st.session_state.source_name = uploaded.name
            st.session_state.result_json = None
            st.success(f"✅ {uploaded.name} procesado correctamente.")
        except Exception as exc:
            st.error(f"❌ No se pudo procesar el archivo: {exc}")

    if st.session_state.source_content:
        with st.expander("📄 Vista previa", expanded=True):
            st.text_area("Contenido", st.session_state.source_content[:5000], height=250, disabled=True)
    else:
        text = st.text_area("✏️ O ingresa el texto manualmente", height=220)
        if text:
            st.session_state.source_content = text
