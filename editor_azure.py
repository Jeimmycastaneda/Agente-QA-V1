import copy
import sys
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
                rows.append({"Steps": i, "Action": _text(step.get("Action")), "Expected": _text(step.get("Expected value"))})
    draft["_steps_df"] = pd.DataFrame(rows or [{"Steps": 1, "Action": "", "Expected": ""}])
    return draft


def _commit_case(draft):
    draft["Preconditions"] = "\n".join(x.strip() for x in draft.get("_preconditions", []) if x.strip())
    draft["Related Use Case"] = _text(draft.get("_related_use_case"))
    df = draft.get("_steps_df", pd.DataFrame())
    steps = []
    if isinstance(df, pd.DataFrame):
        for i, row in df.reset_index(drop=True).iterrows():
            action = _text(row.get("Action")); expected = _text(row.get("Expected"))
            if not action and not expected:
                continue
            steps.append({"Step #": i + 1, "Action": action, "Expected value": expected})
    draft["Steps"] = steps
    draft.pop("_preconditions", None); draft.pop("_related_use_case", None); draft.pop("_steps_df", None)
    return draft


def _render_sync_form():
    result = st.session_state.get("result_json")
    if not result:
        return
    main = sys.modules.get("__main__")
    list_plans = getattr(main, "list_test_plans", None)
    list_suites = getattr(main, "list_test_suites", None)
    sync_cases = getattr(main, "sync_cases_to_test_suite", None)
    if not (list_plans and list_suites and sync_cases):
        return

    st.divider()
    st.subheader("🔄 Sincronizar CP con Test Plan / Suite")
    st.caption("Selecciona un CP, algunos CP o todos los CP generados y luego el Test Plan y la Suite destino.")

    if st.button("📋 Consultar Test Plans", key="editor_sync_list_plans"):
        try:
            with st.spinner("Consultando Test Plans..."):
                data = list_plans(limit=10)
            st.session_state.azure_reference_plans = data.get("plans", [])
            st.session_state.azure_reference_plan_id = None
            st.session_state.azure_reference_suites = []
            st.session_state.azure_reference_suite_id = None
            st.success(f"✅ {len(st.session_state.azure_reference_plans)} Test Plan(s) encontrados.")
        except Exception as exc:
            st.error(f"❌ No se pudieron consultar los Test Plans: {exc}")

    plans = st.session_state.get("azure_reference_plans", [])
    if not plans:
        st.info("Consulta los Test Plans para habilitar la selección del destino.")
        return

    plan_options = [f"{p.get('id')} — {p.get('name', 'Test Plan sin nombre')}" for p in plans]
    plan_label = st.selectbox("1️⃣ Test Plan destino", plan_options, key="editor_sync_plan")
    plan_id = plans[plan_options.index(plan_label)].get("id")

    if st.button("🔎 Consultar Suites", key="editor_sync_list_suites"):
        try:
            with st.spinner("Consultando Suites..."):
                suites = list_suites(plan_id)
            st.session_state.azure_reference_plan_id = plan_id
            st.session_state.azure_reference_suites = suites
            st.session_state.azure_reference_suite_id = None
            st.success(f"✅ {len(suites)} Suite(s) encontradas.")
        except Exception as exc:
            st.error(f"❌ No se pudieron consultar las Suites: {exc}")

    suites = st.session_state.get("azure_reference_suites", [])
    if st.session_state.get("azure_reference_plan_id") != plan_id:
        st.warning("Selecciona el Test Plan y consulta sus Suites antes de continuar.")
        return
    if not suites:
        st.info("Consulta las Suites del Test Plan seleccionado.")
        return

    suite_options = [f"{s.get('id')} — {s.get('name', 'Suite sin nombre')}" for s in suites]
    suite_label = st.selectbox("2️⃣ Suite destino", suite_options, key="editor_sync_suite")
    suite_id = suites[suite_options.index(suite_label)].get("id")

    cases = result.get("TEST_CASES", []) or []
    if not cases:
        st.warning("No hay CP generados para sincronizar.")
        return

    labels = [f"{_text(tc.get('ID'), f'CP-{i+1:05d}')} — {_text(tc.get('Title'), 'Sin título')}" for i, tc in enumerate(cases)]
    mode = st.radio("3️⃣ ¿Qué CP deseas sincronizar?", ["Un solo CP", "Algunos CP", "Todos los CP"], horizontal=True, key="editor_sync_mode")

    if mode == "Un solo CP":
        selected = st.selectbox("Selecciona el CP", labels, key="editor_sync_one")
        indexes = [labels.index(selected)]
    elif mode == "Algunos CP":
        selected = st.multiselect("Selecciona los CP", labels, key="editor_sync_some")
        indexes = [labels.index(x) for x in selected]
    else:
        indexes = list(range(len(cases)))
        st.info(f"Se sincronizarán los {len(indexes)} CP generados.")

    st.caption(f"Parent ID: {suite_id} | Related Work: CU relacionado de cada CP")
    confirm = st.checkbox("Confirmo que deseo crear estos CP en Azure DevOps y asociarlos a la Suite seleccionada.", key="editor_sync_confirm")

    if st.button("🚀 Sincronizar CP con Test Plan / Suite", type="primary", disabled=(not confirm or not indexes), key="editor_sync_execute"):
        try:
            with st.spinner("Sincronizando CP con Azure DevOps..."):
                synced = sync_cases(result, plan_id, suite_id, indexes)
            st.success(f"✅ {len(synced)} CP sincronizados correctamente.")
            st.dataframe(pd.DataFrame(synced), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"❌ No se pudieron sincronizar los CP: {exc}")


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
        preconditions.append(""); st.session_state[state_key]["_preconditions"] = preconditions; st.rerun()

    st.markdown("#### Caso de uso relacionado")
    st.caption("Cada Test Case debe estar asociado a un único Caso de Uso.")
    draft["_related_use_case"] = st.text_input("Caso de uso", value=draft["_related_use_case"], key=f"editor_related_{selected_index}")

    st.divider(); st.markdown("### Steps")
    draft["_steps_df"] = st.data_editor(
        draft["_steps_df"], num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "Steps": st.column_config.NumberColumn("Steps", min_value=1, step=1, disabled=True),
            "Action": st.column_config.TextColumn("Action", width="large"),
            "Expected": st.column_config.TextColumn("Expected", width="large"),
        }, key=f"editor_steps_{selected_index}")

    st.divider(); col_save, col_cancel = st.columns(2)
    with col_save:
        save = st.button("Guardar cambios", type="primary", use_container_width=True, key=f"editor_save_{selected_index}")
    with col_cancel:
        cancel = st.button("Cancelar", use_container_width=True, key=f"editor_cancel_{selected_index}")
    if cancel:
        st.session_state[state_key] = _prepare_case(selected_case); st.rerun()
    if save:
        selected_case.clear(); selected_case.update(_commit_case(copy.deepcopy(draft))); return "saved"

    _render_sync_form()
    return None


def delete_test_case(result, selected_index):
    cases = result.get("TEST_CASES", [])
    if not isinstance(cases, list) or selected_index < 0 or selected_index >= len(cases):
        return False
    case_id = _text(cases[selected_index].get("ID")); cases.pop(selected_index)
    coverage = result.get("COVERAGE", [])
    if isinstance(coverage, list) and case_id:
        result["COVERAGE"] = [row for row in coverage if _text(row.get("Test Case")) != case_id]
    for key in list(st.session_state.keys()):
        if key.startswith("qa_editor_"): del st.session_state[key]
    return True
