import copy
import pandas as pd
import streamlit as st


def safe_text(value, default=""):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value).strip()


def safe_steps(test_case):
    steps = test_case.get("Steps", [])
    return steps if isinstance(steps, list) else []


def _ensure_editor_state(selected_index):
    key = f"qa_editor_draft_{selected_index}"
    if key not in st.session_state:
        st.session_state[key] = None
    return key


def _build_draft(test_case):
    draft = copy.deepcopy(test_case)

    preconditions = safe_text(draft.get("Preconditions"))
    if not preconditions:
        precondition_rows = [""]
    else:
        precondition_rows = [x.strip() for x in preconditions.splitlines() if x.strip()]

    related = safe_text(draft.get("Related Use Case"))
    related_rows = [x.strip() for x in related.splitlines() if x.strip()] or [""]

    steps = []
    for pos, step in enumerate(safe_steps(draft), start=1):
        steps.append({
            "Step #": pos,
            "Action": safe_text(step.get("Action")),
            "Expected": safe_text(step.get("Expected value")),
        })

    if not steps:
        steps = [{"Step #": 1, "Action": "", "Expected": ""}]

    draft["_precondition_rows"] = precondition_rows
    draft["_related_rows"] = related_rows
    draft["_steps_df"] = pd.DataFrame(steps)
    return draft


def _commit_draft(draft):
    draft["Preconditions"] = "\n".join(
        x.strip() for x in draft.pop("_precondition_rows", []) if x.strip()
    )
    draft["Related Use Case"] = "\n".join(
        x.strip() for x in draft.pop("_related_rows", []) if x.strip()
    )

    df = draft.pop("_steps_df")
    normalized = []
    for pos, row in df.reset_index(drop=True).iterrows():
        action = safe_text(row.get("Action"))
        expected = safe_text(row.get("Expected"))
        if not action and not expected:
            continue
        normalized.append({
            "Step #": pos + 1,
            "Action": action,
            "Expected value": expected,
        })
    draft["Steps"] = normalized
    return draft


def render_azure_style_editor(selected_case, selected_index):
    """
    Editor para el Agente QA V1.

    Mantiene el modelo actual del agente y cambia únicamente la experiencia
    de edición para acercarla a Azure DevOps:
      - Description estructurada.
      - Precondiciones como lista editable.
      - Caso de uso relacionado.
      - Steps en tabla Action / Expected.
    """

    state_key = _ensure_editor_state(selected_index)

    if st.session_state[state_key] is None:
        st.session_state[state_key] = _build_draft(selected_case)

    draft = st.session_state[state_key]

    st.markdown("### Description")

    c1, c2 = st.columns(2)
    with c1:
        draft["Product"] = st.text_input(
            "Producto",
            value=safe_text(draft.get("Product")),
            key=f"editor_product_{selected_index}",
        )
    with c2:
        draft["Module"] = st.text_input(
            "Módulo",
            value=safe_text(draft.get("Module")),
            key=f"editor_module_{selected_index}",
        )

    draft["Title"] = st.text_input(
        "Título",
        value=safe_text(draft.get("Title")),
        key=f"editor_title_{selected_index}",
    )

    draft["Description"] = st.text_area(
        "Descripción",
        value=safe_text(draft.get("Description")),
        height=230,
        key=f"editor_description_{selected_index}",
        help="Contenido principal de Description. Se conserva el texto generado por Gemini y puede ser revisado antes de exportar.",
    )

    draft["Expected Result"] = st.text_area(
        "Resultado esperado de la prueba",
        value=safe_text(draft.get("Expected Result")),
        height=130,
        key=f"editor_expected_result_{selected_index}",
    )

    st.markdown("#### Precondiciones")
    preconditions = draft["_precondition_rows"]

    remove_precondition = None
    for i, value in enumerate(preconditions):
        c1, c2 = st.columns([12, 1])
        with c1:
            preconditions[i] = st.text_input(
                f"Precondición {i + 1}",
                value=value,
                key=f"editor_precondition_{selected_index}_{i}",
                label_visibility="collapsed",
            )
        with c2:
            if st.button("×", key=f"remove_precondition_{selected_index}_{i}"):
                remove_precondition = i

    if remove_precondition is not None:
        preconditions.pop(remove_precondition)
        st.session_state[state_key]["_precondition_rows"] = preconditions
        st.rerun()

    if st.button("＋ Agregar precondición", key=f"add_precondition_{selected_index}"):
        preconditions.append("")
        st.session_state[state_key]["_precondition_rows"] = preconditions
        st.rerun()

    st.markdown("#### Caso de uso relacionado")
    related = draft["_related_rows"]

    remove_related = None
    for i, value in enumerate(related):
        c1, c2 = st.columns([12, 1])
        with c1:
            related[i] = st.text_input(
                f"Caso de uso {i + 1}",
                value=value,
                key=f"editor_related_{selected_index}_{i}",
                label_visibility="collapsed",
            )
        with c2:
            if st.button("×", key=f"remove_related_{selected_index}_{i}"):
                remove_related = i

    if remove_related is not None:
        related.pop(remove_related)
        st.session_state[state_key]["_related_rows"] = related
        st.rerun()

    if st.button("＋ Agregar caso de uso", key=f"add_related_{selected_index}"):
        related.append("")
        st.session_state[state_key]["_related_rows"] = related
        st.rerun()

    st.divider()
    st.markdown("### Steps")
    st.caption("La tabla mantiene las dos columnas funcionales que necesitamos para el futuro envío a Azure DevOps: Action y Expected.")

    df = draft["_steps_df"].copy()
    edited_df = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Step #": st.column_config.NumberColumn(
                "Steps",
                min_value=1,
                step=1,
                disabled=True,
            ),
            "Action": st.column_config.TextColumn(
                "Action",
                width="large",
            ),
            "Expected": st.column_config.TextColumn(
                "Expected",
                width="large",
            ),
        },
        key=f"editor_steps_{selected_index}",
    )

    draft["_steps_df"] = edited_df

    st.divider()

    save_col, cancel_col = st.columns([2, 2])

    with save_col:
        save = st.button(
            "Guardar cambios",
            type="primary",
            use_container_width=True,
            key=f"save_editor_{selected_index}",
        )

    with cancel_col:
        cancel = st.button(
            "Cancelar",
            use_container_width=True,
            key=f"cancel_editor_{selected_index}",
        )

    if cancel:
        st.session_state[state_key] = _build_draft(selected_case)
        st.rerun()

    if save:
        final_case = _commit_draft(copy.deepcopy(draft))
        selected_case.clear()
        selected_case.update(final_case)
        selected_case["_edited_by_qa"] = True
        st.session_state[state_key] = _build_draft(selected_case)
        return True

    return False
