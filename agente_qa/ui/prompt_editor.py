import streamlit as st

from agente_qa.prompts import (
    DEFAULT_PROMPT_NAME,
    is_valid_prompt_name,
    list_prompt_versions,
    list_prompts,
    load_prompt,
    restore_prompt_version,
    save_prompt,
)

# ============================================================
# SELECCIÓN Y EDICIÓN DE PROMPTS QA (.md en prompts/)
# ============================================================


def render_prompt_section():
    st.subheader("📝 Prompt QA")

    prompts = list_prompts()

    if not prompts:
        st.error(
            "No hay prompts .md en la carpeta 'prompts/'. "
            "Agrega al menos un archivo .md para poder generar casos."
        )
        return None

    default_index = (
        prompts.index(DEFAULT_PROMPT_NAME) if DEFAULT_PROMPT_NAME in prompts else 0
    )

    selected_prompt = st.selectbox(
        "Prompt activo",
        prompts,
        index=default_index,
        key="qa_selected_prompt",
        help="Define las reglas que sigue el agente para generar los casos de prueba.",
    )

    with st.expander("✏️ Editar prompt (.md)", expanded=False):
        editor_key = f"qa_prompt_editor_{selected_prompt}"

        tab_edit, tab_preview = st.tabs(["Editar", "Vista previa"])

        with tab_edit:
            st.text_area(
                f"Contenido de {selected_prompt}",
                value=load_prompt(selected_prompt),
                height=350,
                key=editor_key,
            )

        with tab_preview:
            st.markdown(st.session_state.get(editor_key, ""))

        c1, c2 = st.columns(2)

        with c1:
            if st.button(
                "💾 Guardar cambios",
                key=f"qa_prompt_save_{selected_prompt}",
                type="primary",
            ):
                save_prompt(
                    selected_prompt,
                    st.session_state[editor_key],
                )
                st.success(f"✅ {selected_prompt} actualizado.")
                st.rerun()

        with c2:
            new_name = st.text_input(
                "Guardar como nuevo prompt",
                placeholder="mi_prompt.md",
                key=f"qa_prompt_new_name_{selected_prompt}",
            )
            if st.button(
                "📄 Guardar como nuevo",
                key=f"qa_prompt_saveas_{selected_prompt}",
            ):
                if not is_valid_prompt_name(new_name.strip()):
                    st.error(
                        "Nombre inválido. Usa solo letras, números, '_'/'-' "
                        "y termina en .md (ej: mi_prompt.md)."
                    )
                else:
                    save_prompt(
                        new_name.strip(),
                        st.session_state[editor_key],
                    )
                    st.success(f"✅ Prompt guardado como {new_name.strip()}.")
                    st.rerun()

        _render_history_section(selected_prompt)

    return selected_prompt


def _render_history_section(selected_prompt):
    versions = list_prompt_versions(selected_prompt)
    if not versions:
        return

    st.markdown("---")
    st.caption("🕘 Historial de versiones")

    selected_version = st.selectbox(
        "Versión guardada",
        versions,
        key=f"qa_prompt_version_{selected_prompt}",
        help="Versiones anteriores de este prompt, más reciente primero.",
    )

    if st.button(
        "↩️ Restaurar esta versión",
        key=f"qa_prompt_restore_{selected_prompt}",
    ):
        restore_prompt_version(selected_prompt, selected_version)
        st.success(f"✅ {selected_prompt} restaurado a la versión {selected_version}.")
        st.rerun()
