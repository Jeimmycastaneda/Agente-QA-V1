"""Punto de entrada de la UI Azure.

La integración HTTP vive exclusivamente en integrations/azure_devops.py.
Esta capa debe contener botones, selección de Plan/Suite/CP y confirmaciones.
"""

def render_azure_section():
    import streamlit as st
    st.divider()
    st.subheader("🚀 Cargar CP en Azure DevOps")
    st.caption("La escritura debe ocurrir únicamente después de selección y confirmación explícita.")
    st.info("Integración Azure aislada en agente_qa.integrations.azure_devops.")
