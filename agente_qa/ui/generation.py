import os
import streamlit as st

from agente_qa.core.generation import generate_qa_data
from agente_qa.providers.gemini import GeminiProvider
from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf
from agente_qa.core.rules import DEFAULT_PRODUCT, DEFAULT_MODULE

def render_generation_section():
    st.divider()
    st.subheader("🧪 Generación QA")

    with st.sidebar:
        api_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        if not api_key:
            api_key = st.text_input("🔑 Google Gemini API Key", type="password")
        model = st.selectbox("Modelo", ["gemini-3.6-flash", "gemini-3.5-flash-lite"])
        config_key = st.selectbox("Formato de Excel", ["Autos Colectivos", "Siniestros Fasecolda", "General QA"])

    if st.button("🚀 Generar casos de prueba", type="primary", disabled=not bool(st.session_state.source_content.strip())):
        if not api_key:
            st.error("Configura GEMINI_API_KEY.")
            return
        try:
            with st.spinner("Analizando documentación y generando casos..."):
                prompt = open("prompts/qa_base.md", encoding="utf-8").read()
                provider = GeminiProvider(api_key, model)
                result = generate_qa_data(provider, prompt, st.session_state.source_content)
            st.session_state.result_json = result
            st.session_state.excel_data = create_excel(result, config_key)
            st.session_state.pdf_data = create_pdf(result, config_key, st.session_state.source_name)
            st.success("✅ Generación completada.")
        except Exception as exc:
            st.error(f"❌ Error durante la generación: {exc}")
