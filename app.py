"""Punto de entrada Streamlit del Agente QA.

Esta versión organiza la aplicación por responsabilidades. Streamlit sigue siendo
la interfaz y este archivo actúa como orquestador, no como almacén de toda la lógica.
"""

import streamlit as st

from agente_qa.ui.settings import render_settings_section
from agente_qa.ui.document import render_document_section
from agente_qa.ui.generation import render_generation_section
from agente_qa.ui.editor import render_editor_section
from agente_qa.ui.azure import render_azure_section
from agente_qa.ui.results import render_results_section
from agente_qa.ui.state import initialize_state

st.set_page_config(page_title="Agente QA", layout="wide")
initialize_state()
settings = render_settings_section()
st.session_state.qa_settings = settings

st.title("🤖 Agente QA — Generador de Casos de Prueba")
st.caption("VERSION PREVIA — DRAFT | Streamlit → Gemini → Excel/PDF → Azure DevOps")

render_document_section()
render_generation_section(settings)
render_results_section()
render_editor_section()
render_azure_section()
