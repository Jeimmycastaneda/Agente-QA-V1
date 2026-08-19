import streamlit as st
from agente_qa.extraction.document import extract_source


def render_document_section():
    st.subheader("📁 Carga de Documento")
    st.info(
        "Formatos de HU: TXT, MD, PDF, DOCX, XLSX/CSV. "
        "Para PDF escaneado se requiere OCR; esta versión no inventa texto que no pueda extraer."
    )
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
            st.session_state.excel_data = None
            st.session_state.pdf_data = None
            st.session_state.azure_reference_preview = None
            st.session_state.azure_publish_results = None
            st.success(f"✅ {uploaded.name} procesado correctamente.")
        except Exception as exc:
            st.session_state.source_content = ""
            st.session_state.source_name = ""
            st.session_state.result_json = None
            st.session_state.excel_data = None
            st.session_state.pdf_data = None
            st.error(f"❌ No se pudo procesar el archivo: {exc}")

    if st.session_state.source_content:
        with st.expander("📄 Vista previa del contenido", expanded=True):
            content = st.session_state.source_content
            st.text_area("Contenido", content[:5000], height=250, disabled=True)
            c1, c2, c3 = st.columns(3)
            c1.metric("Caracteres", len(content))
            c2.metric("Líneas", len(content.splitlines()))
            c3.metric("Palabras", len(content.split()))
    else:
        text = st.text_area(
            "✏️ O ingresa el texto manualmente",
            height=220,
            placeholder="Pega aquí la Historia de Usuario o documentación fuente...",
            key="qa_manual_source",
        )
        if text:
            st.session_state.source_content = text
            st.session_state.source_name = "Entrada manual"
