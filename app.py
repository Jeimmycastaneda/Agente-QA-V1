import streamlit as st

from agente_qa.config import APP_VERSION
from agente_qa.errors import ConfigError
from agente_qa.secrets import resolve_secret
from agente_qa.settings import load_azure_devops_config
from agente_qa.ui.azure_section import render_azure_section
from agente_qa.ui.document import render_document_section
from agente_qa.ui.generation_section import render_generation_section
from agente_qa.ui.prompt_editor import render_prompt_section
from agente_qa.ui.results import render_results_section
from agente_qa.ui.sidebar import render_sidebar
from agente_qa.ui.state import init_session_state

# ============================================================
# INTERFAZ
# ============================================================
st.set_page_config(
    page_title=f"Agente QA {APP_VERSION}",
    layout="wide",
)

init_session_state()

st.title(f"🤖 Agente QA {APP_VERSION} — Generador de Casos de Prueba")
st.caption(
    "VERSION PREVIA — DRAFT | PDF / DOCX / TXT / MD → análisis QA → Excel + PDF"
)

sidebar_config = render_sidebar()
source_text = render_document_section()
selected_prompt = render_prompt_section()
render_generation_section(source_text, sidebar_config, selected_prompt)
render_results_section(sidebar_config["selected_config"])

# Sección de Azure DevOps (fase 5): puramente aditiva, no toca los botones
# de descarga Excel/PDF de ui/results.py. Solo se renderiza si
# config/azure_devops.yaml tiene enabled: true Y el PAT configurado resuelve.
try:
    _azure_config = load_azure_devops_config()
except ConfigError:
    _azure_config = None

if _azure_config is not None and _azure_config.enabled and resolve_secret(_azure_config.pat_secret_name):
    render_azure_section(st.session_state.result_json, sidebar_config["selected_config"])
