import os
from pathlib import Path
import streamlit as st

from agente_qa.core.generation import generate_qa_data
from agente_qa.providers.gemini import GeminiProvider
from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf


def _read_prompt() -> str:
    candidates = [
        Path("prompts/qa_base.md"),
        Path("prompt_qa.txt"),
    ]
    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("No se encontró prompts/qa_base.md ni prompt_qa.txt.")


def render_generation_section():
    st.divider()
    st.subheader("🧪 Generación QA")

    with st.sidebar:
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        if not api_key:
            api_key = st.text_input("🔑 Google Gemini API Key", type="password")
        model = st.selectbox(
            "Modelo",
            ["gemini-3.6-flash", "gemini-3.5-flash-lite"],
        )
        config_key = st.selectbox(
            "Formato de Excel",
            ["Autos Colectivos", "Siniestros Fasecolda", "General QA"],
        )

    source = st.session_state.get("source_content", "")
    disabled = not bool(source.strip())
    if st.button("🚀 Generar casos de prueba", type="primary", disabled=disabled):
        if not api_key:
            st.error("Configura GEMINI_API_KEY.")
            return
        try:
            with st.spinner("Analizando documentación y generando casos..."):
                prompt = _read_prompt()
                provider = GeminiProvider(api_key, model=model)
                result = generate_qa_data(provider, prompt, source)
                st.session_state.result_json = result
                st.session_state.excel_data = create_excel(result, config_key)
                st.session_state.pdf_data = create_pdf(
                    result, config_key, st.session_state.get("source_name", "")
                )
            st.success("✅ Generación completada.")
        except Exception as exc:
            st.error(f"❌ Error durante la generación: {exc}")

    if st.session_state.get("excel_data") or st.session_state.get("pdf_data"):
        st.divider()
        st.markdown("#### 📦 Exportaciones")
        c1, c2 = st.columns(2)
        if st.session_state.get("excel_data"):
            c1.download_button(
                "⬇️ Descargar Excel",
                data=st.session_state.excel_data,
                file_name="Agente_QA_Azure_Import.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch",
                key="download_excel_qa",
            )
        if st.session_state.get("pdf_data"):
            c2.download_button(
                "⬇️ Descargar PDF",
                data=st.session_state.pdf_data,
                file_name="Agente_QA_Test_Plan.pdf",
                mime="application/pdf",
                width="stretch",
                key="download_pdf_qa",
            )
