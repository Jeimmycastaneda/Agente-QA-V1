import streamlit as st

from agente_qa.config import DEFAULT_PROVIDER, EXCEL_CONFIGS, FALLBACK_MODELS, PROVIDERS
from agente_qa.secrets import resolve_secret


def render_sidebar():
    with st.sidebar:
        st.header("⚙️ Configuración")

        provider_name = DEFAULT_PROVIDER
        secret_name = PROVIDERS[provider_name]["secret_name"]

        api_key = resolve_secret(secret_name)

        if api_key:
            st.success(f"✅ {secret_name} configurada")
        else:
            api_key = st.text_input(
                "🔑 Google Gemini API Key",
                type="password",
            )

        selected_model = st.selectbox(
            "Modelo",
            FALLBACK_MODELS,
            index=0,
        )

        selected_config = st.selectbox(
            "Formato de Excel",
            list(EXCEL_CONFIGS.keys()),
            index=0,
        )

        max_retries = st.number_input(
            "Máximo de reintentos",
            min_value=0,
            max_value=5,
            value=2,
        )

        wait_time = st.number_input(
            "Espera inicial (segundos)",
            min_value=1,
            max_value=60,
            value=10,
        )

    return {
        "provider": provider_name,
        "api_key": api_key,
        "selected_model": selected_model,
        "selected_config": selected_config,
        "max_retries": max_retries,
        "wait_time": wait_time,
    }
