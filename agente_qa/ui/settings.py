"""Configuración de la aplicación.

Mantiene en una capa de UI los controles que existían en main sin mezclar
credenciales ni configuración con la lógica de generación.
"""
from __future__ import annotations

import os
import streamlit as st


def _secret_or_env(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(name, "")).strip()


def render_settings_section() -> dict:
    """Renderiza la configuración y devuelve la selección actual.

    Los valores se conservan en session_state para que el resto de la UI pueda
    consumirlos sin depender de widgets ni de variables globales.
    """
    st.sidebar.header("⚙️ Configuración")

    api_key = _secret_or_env("GEMINI_API_KEY")
    if api_key:
        st.sidebar.success("✅ GEMINI_API_KEY configurada")
    else:
        api_key = st.sidebar.text_input("🔑 Google Gemini API Key", type="password", key="settings_gemini_key")

    models = ["gemini-3.6-flash", "gemini-3.5-flash-lite"]
    selected_model = st.sidebar.selectbox("Modelo", models, index=0, key="settings_model")
    selected_config = st.sidebar.selectbox(
        "Formato de Excel",
        ["Autos Colectivos", "Siniestros Fasecolda", "General QA"],
        index=0,
        key="settings_excel_config",
    )
    max_retries = st.sidebar.number_input("Máximo de reintentos", min_value=0, max_value=5, value=2, key="settings_retries")
    wait_time = st.sidebar.number_input("Espera inicial (segundos)", min_value=1, max_value=60, value=10, key="settings_wait")

    return {
        "api_key": api_key,
        "model": selected_model,
        "config_key": selected_config,
        "max_retries": int(max_retries),
        "wait_time": int(wait_time),
    }
