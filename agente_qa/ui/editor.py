import copy
import pandas as pd
import streamlit as st


def _text(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def _prepare_case(test_case):
    draft = copy.deepcopy(test_case)
    pre = _text(draft.get("Preconditions"))
    draft["_preconditions"] = [x.strip() for x in pre.splitlines() if x.strip()] or [""]
    draft["_related_use_case"] = _text(draft.get("Related Use Case"))
    rows = []
    steps = draft.get("Steps", [])
    if isinstance(steps, list):
        for i, step in enumerate(steps, 1):
            if isinstance(step, dict):
                rows.append({
                    "Steps": i,
                    "Action": _text(step.get("Action")),
                    "Expected": _text(step.get("Expected value")),
                })
    draft["_steps_df"] = pd.DataFrame(rows or [{"Steps": 1, "Action": "", "Expected": ""}])
    return draft


def _commit_case(draft):
    draft["Preconditions"] = "\n".join(x.strip() for x in draft.get("_preconditions", []) if x.strip())
    draft["Related Use Case"] = _text(draft.get("_related_use_case"))
    df = draft.get("_steps_df", pd.DataFrame())
    steps = []
    if isinstance(df, pd.DataFrame):
        for i, row in df.reset_index(drop=True).iterrows():
            action = _text(row.get("Action"))
            expected = _text(row.get("Expected"))
            if not action and not expected:
                continue
            steps.append({"Step #": i + 1, "Action": action, "Expected value": expected})
    draft["Steps"] = steps
    draft.pop("_preconditions", None)
    draft.pop("_related_use_case", None)
    draft.pop("_steps_df", None)
    return draft


def render_azure_style_editor(selected_case, selected_index):
    state_key = f"qa_editor_{selected_index}"
    if state_key not in st.session_state:
        st.session_state[state_key] = _prepare_case(selected_case)
    draft = st.session_state[state_key]
    st.markdown("### Description")
    col1, col2 = st.columns(2)
    with col1:
        draft["Product"] = st.text_input("Producto", value=_text(draft.get("Product")), key=f"editor_product_{selected_index}")
    with col2:
        draft["Module"] = st.text_input("Módulo", value=_text(draft.get("Module")), key=f"editor_module_{selected_index}")
    draft["Title"] = st.text_input("Título", value=_text(draft.get("Title")), key=f"editor_title_{selected_index}")
    draft["Description"] = st.text_area("Descripción", value=_text(draft.get("Description")), height=220, key=f"editor_description_{selected_index}")
    draft["Expected Result"] = st.text_area("Resultado esperado de la prueba", value=_text(draft.get("Expected Result")), height=130, key=f"editor_expected_{selected_index}")
    st.markdown("#### Precondiciones")
    preconditions = draft["_preconditions"]
    for i, value in enumerate(preconditions):
        preconditions[i] = st.text_input(f"Precondición {i + 1}", value=value, key=f"editor_pre_{selected_index}_{i}", label_visibility="collapsed")
    if st.button("＋ Agregar precondición", key=f"editor_add_pre_{selected_index}"):
        preconditions.append("")
        st.session_state[state_key]["_preconditions"] = preconditions
        st.rerun()
    st.markdown("#### Caso de uso relacionado")
    st.caption("Cada Test Case debe estar asociado a un único Caso de Uso.")
    draft["_related_use_case"] = st.text_input("Caso de uso", value=draft["_related_use_case"], key=f"editor_related_{selected_index}")
    st.divider()
    st.markdown("### Steps")
    draft["_steps_df"] = st.data_editor(
        draft["_steps_df"], num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Steps": st.column_config.NumberColumn("Steps", min_value=1, step=1, disabled=True),
            "Action": st.column_config.TextColumn("Action", width="large"),
            "Expected": st.column_config.TextColumn("Expected", width="large"),
        }, key=f"editor_steps_{selected_index}")
    st.divider()
    col_save, col_cancel = st.columns(2)
    with col_save:
        save = st.button("Guardar cambios", type="primary", use_container_width=True, key=f"editor_save_{selected_index}")
    with col_cancel:
        cancel = st.button("Cancelar", use_container_width=True, key=f"editor_cancel_{selected_index}")
    if cancel:
        st.session_state[state_key] = _prepare_case(selected_case)
        st.rerun()
    if save:
        selected_case.clear()
        selected_case.update(_commit_case(copy.deepcopy(draft)))
        return "saved"
    return None


def delete_test_case(result, selected_index):
    cases = result.get("TEST_CASES", [])
    if not isinstance(cases, list) or selected_index < 0 or selected_index >= len(cases):
        return False
    case = cases[selected_index]
    case_id = _text(case.get("ID"))
    cases.pop(selected_index)
    coverage = result.get("COVERAGE", [])
    if isinstance(coverage, list) and case_id:
        result["COVERAGE"] = [row for row in coverage if _text(row.get("Test Case")) != case_id]
    for key in list(st.session_state.keys()):
        if key.startswith("qa_editor_"):
            del st.session_state[key]
    return True


def render_editor_section():
    result = st.session_state.get("result_json")
    if not result:
        return
    st.subheader("✏️ Editar caso de prueba")
    cases = result.get("TEST_CASES", [])
    if not cases:
        st.info("No hay Test Cases para editar.")
        return
    labels = [f"{tc.get('ID', 'CP')} — {tc.get('Title', '')[:100]}" for tc in cases]
    label = st.selectbox("Selecciona el caso que deseas editar", labels, key="qa_editor_selected_case")
    index = labels.index(label)
    if render_azure_style_editor(cases[index], index) == "saved":
        st.session_state.excel_data = None
        st.session_state.pdf_data = None
        st.success("✅ Caso actualizado.")
