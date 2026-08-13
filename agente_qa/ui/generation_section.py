import logging

import streamlit as st

from agente_qa import config
from agente_qa.errors import AgenteQAError, QuotaError
from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf
from agente_qa.generation import generate_qa_data
from agente_qa.prompts import load_prompt
from agente_qa.providers import build_provider
from agente_qa.security import redact

logger = logging.getLogger(__name__)


def render_generation_section(source_text, sidebar_config, selected_prompt):
    st.divider()
    st.subheader("🧪 Generación QA")

    if st.button(
        "🚀 Generar casos de prueba",
        type="primary",
        disabled=not bool(source_text.strip()) or not selected_prompt,
    ):
        try:
            with st.spinner(
                "Analizando documentación y generando casos..."
            ):
                provider = build_provider(
                    sidebar_config["provider"],
                    sidebar_config["api_key"],
                )
                result = generate_qa_data(
                    load_prompt(selected_prompt),
                    source_text,
                    provider,
                    sidebar_config["selected_model"],
                    max_retries=int(sidebar_config["max_retries"]),
                    initial_wait=int(sidebar_config["wait_time"]),
                )

            st.session_state.result_json = result
            st.session_state.excel_data = create_excel(
                result,
                sidebar_config["selected_config"],
            )
            st.session_state.pdf_data = create_pdf(
                result,
                sidebar_config["selected_config"],
                st.session_state.get("source_name", ""),
            )

            st.success(
                f"✅ Generación completada: "
                f"{len(result['TEST_CASES'])} casos."
            )

        except QuotaError:
            st.warning(
                "⚠️ Cuota del proveedor agotada. Espera unos minutos o "
                "cambia de modelo."
            )

        except AgenteQAError as exc:
            st.error(f"❌ {exc.user_message}")
            if config.DEBUG:
                with st.expander("Detalle técnico"):
                    st.code(redact(exc.detail))

        except Exception:
            logger.exception("generate_qa_data failed")
            st.error(
                "❌ Ocurrió un error durante la generación. Inténtalo de "
                "nuevo o revisa la configuración."
            )
