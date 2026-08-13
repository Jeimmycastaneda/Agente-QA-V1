import hashlib
import logging

import streamlit as st

from agente_qa import config
from agente_qa.errors import SourceError
from agente_qa.extraction import extract_source_bytes
from agente_qa.security import redact

logger = logging.getLogger(__name__)


def render_document_section():
    st.subheader("📁 Carga de Documento")

    st.info(
        "Formatos soportados: TXT, MD, PDF, DOCX. "
        "Para PDF escaneado se requiere OCR; esta versión no inventa "
        "texto que no pueda extraer."
    )

    uploaded = st.file_uploader(
        "Arrastra o selecciona un documento",
        type=["txt", "md", "pdf", "docx"],
    )

    source_text = st.session_state.source_content

    if uploaded:
        data = uploaded.getvalue()
        content_hash = hashlib.sha256(data).hexdigest()

        # Procesar solo cuando cambia el contenido (no solo el nombre).
        if st.session_state.source_hash != content_hash:
            try:
                with st.spinner(f"Procesando {uploaded.name}..."):
                    source_text = extract_source_bytes(uploaded.name, data)

                st.session_state.source_content = source_text
                st.session_state.source_name = uploaded.name
                st.session_state.source_hash = content_hash
                st.session_state.result_json = None
                st.session_state.excel_data = None
                st.session_state.pdf_data = None

                st.success(f"✅ {uploaded.name} procesado correctamente.")

            except SourceError as exc:
                st.session_state.source_content = ""
                st.session_state.source_name = ""
                st.session_state.source_hash = ""
                st.session_state.result_json = None
                st.session_state.excel_data = None
                st.session_state.pdf_data = None

                st.error(f"❌ {exc.user_message}")
                if config.DEBUG:
                    with st.expander("Detalle técnico"):
                        st.code(redact(exc.detail))

            except Exception:
                st.session_state.source_content = ""
                st.session_state.source_name = ""
                st.session_state.source_hash = ""
                st.session_state.result_json = None
                st.session_state.excel_data = None
                st.session_state.pdf_data = None

                logger.exception("extract_source failed")
                st.error(
                    "❌ No se pudo procesar el archivo. Revisa el formato "
                    "e inténtalo de nuevo."
                )

    if source_text:
        with st.expander("📄 Vista previa del contenido", expanded=True):
            st.text_area(
                "Contenido",
                source_text[:5000],
                height=250,
                disabled=True,
            )

            c1, c2, c3 = st.columns(3)
            c1.metric("Caracteres", len(source_text))
            c2.metric("Líneas", len(source_text.splitlines()))
            c3.metric("Palabras", len(source_text.split()))

    else:
        source_text = st.text_area(
            "✏️ O ingresa el texto manualmente",
            height=220,
            placeholder=(
                "Pega aquí la Historia de Usuario o documentación fuente..."
            ),
        )

        if source_text:
            st.session_state.source_content = source_text

    return source_text
