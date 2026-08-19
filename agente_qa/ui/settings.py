"""Configuración de la aplicación."""
from __future__ import annotations

import os
import streamlit as st
from agente_qa.integrations.azure_devops import AzureDevOpsConfig, validate_connection


def _secret_or_env(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def _azure_config() -> AzureDevOpsConfig:
    organization = _secret_or_env("AZURE_DEVOPS_ORG") or _secret_or_env("AZDO_ORGANIZATION")
    project = _secret_or_env("AZURE_DEVOPS_PROJECT") or _secret_or_env("AZDO_PROJECT")
    pat = _secret_or_env("AZURE_DEVOPS_PAT") or _secret_or_env("AZDO_PAT")
    enabled = _secret_or_env("AZDO_ENABLED").lower() in {"1", "true", "yes", "si", "sí"} or bool(pat)
    return AzureDevOpsConfig(organization=organization, project=project, pat=pat, enabled=enabled)


def render_settings_section() -> dict:
    st.sidebar.header("⚙️ Configuración")
    api_key = _secret_or_env("GEMINI_API_KEY")
    if api_key:
        st.sidebar.success("✅ GEMINI_API_KEY configurada")
    else:
        api_key = st.sidebar.text_input("🔑 Google Gemini API Key", type="password", key="settings_gemini_key")

    models = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    selected_model = st.sidebar.selectbox("Modelo", models, index=0, key="settings_model")
    selected_config = st.sidebar.selectbox("Formato de Excel", ["Autos Colectivos", "Siniestros Fasecolda", "General QA"], index=0, key="settings_excel_config")
    max_retries = st.sidebar.number_input("Máximo de reintentos", min_value=0, max_value=5, value=2, key="settings_retries")
    wait_time = st.sidebar.number_input("Espera inicial (segundos)", min_value=1, max_value=60, value=10, key="settings_wait")

    st.sidebar.divider()
    st.sidebar.subheader("🔐 Azure DevOps")
    st.sidebar.caption("Prueba de conexión en modo solo lectura. No crea, modifica ni elimina CP.")
    if st.sidebar.button("🔌 Probar conexión con Azure DevOps", key="azure_test_connection"):
        try:
            cfg = _azure_config()
            if not cfg.enabled:
                raise RuntimeError("Azure DevOps no está habilitado. Configura AZDO_ENABLED=true o un PAT.")
            with st.spinner("Verificando conexión con Azure DevOps..."):
                payload = validate_connection(cfg)
            st.sidebar.success("✅ Conexión con Azure DevOps correcta.")
            st.sidebar.caption(f"Organización: {cfg.organization} | Proyecto: {cfg.project}")
            if isinstance(payload, dict) and payload.get("name"):
                st.sidebar.info(f"Proyecto validado: {payload.get('name')}")
        except Exception as exc:
            st.sidebar.error(f"❌ No se pudo conectar con Azure DevOps: {exc}")

    return {"api_key": api_key, "model": selected_model, "config_key": selected_config, "max_retries": int(max_retries), "wait_time": int(wait_time)}
