"""UI Azure DevOps.

La red HTTP vive en integrations.azure_devops. Esta capa únicamente consulta,
permite seleccionar Plan/Suite/CP y solicita una confirmación explícita antes
de cualquier escritura.
"""
from __future__ import annotations

import streamlit as st
from agente_qa.integrations.azure_devops import (
    AzureDevOpsConfig,
    AzureDevOpsApiError,
    list_test_plans,
    list_test_suites,
    create_test_case,
    add_parent_relation_to_work_item,
    add_test_cases_to_suite,
)


def _cfg():
    return AzureDevOpsConfig.from_env()


def render_azure_section():
    st.divider()
    st.subheader("🚀 Cargar CP en Azure DevOps")
    st.caption("La escritura ocurre únicamente después de selección y confirmación explícita.")

    if st.button("🔄 Consultar Test Plans", key="azure_refresh_plans"):
        try:
            st.session_state.azure_plans = list_test_plans(_cfg(), limit=10)
            st.session_state.azure_suites = []
        except Exception as exc:
            st.error(f"No fue posible consultar Test Plans: {exc}")
    elif not st.session_state.get("azure_plans"):
        st.info("Consulta los Test Plans para comenzar. La consulta es solo de lectura.")

    plans = st.session_state.get("azure_plans", [])
    if not plans:
        return

    plan_labels = [f"{p.get('id')} — {p.get('name', 'Sin nombre')}" for p in plans]
    plan_label = st.selectbox("Test Plan destino", plan_labels, key="azure_plan_select")
    plan = plans[plan_labels.index(plan_label)]

    if st.button("📂 Cargar Suites", key="azure_load_suites"):
        try:
            st.session_state.azure_suites = list_test_suites(plan["id"], _cfg())
        except Exception as exc:
            st.error(f"No fue posible consultar las Suites: {exc}")

    suites = st.session_state.get("azure_suites", [])
    if not suites:
        return

    suite_labels = [f"{s.get('id')} — {s.get('name', 'Suite sin nombre')}" for s in suites]
    suite_label = st.selectbox("Suite destino", suite_labels, key="azure_suite_select")
    suite = suites[suite_labels.index(suite_label)]

    cases = st.session_state.get("result_json", {}).get("TEST_CASES", [])
    if not cases:
        st.warning("Primero genera al menos un Test Case.")
        return

    case_labels = [f"{i+1}. {tc.get('ID', 'CP')} — {tc.get('Title', '')}" for i, tc in enumerate(cases)]
    selected = st.multiselect("CP a cargar", case_labels, default=case_labels, key="azure_cases_select")
    selected_cases = [cases[case_labels.index(label)] for label in selected]

    st.caption(f"Se cargarán {len(selected_cases)} CP en la Suite seleccionada.")
    parent_id = st.text_input(
        "ID Parent / IDPadre",
        value=str(st.session_state.get("azure_id_padre", "")),
        help="Se usa únicamente si se informa explícitamente. No se inventa.",
        key="azure_parent_id",
    )
    st.session_state.azure_id_padre = parent_id.strip()

    confirm = st.checkbox(
        "Confirmo que quiero crear los Test Cases seleccionados y asociarlos a esta Suite.",
        key="azure_confirm_upload",
    )
    if st.button(
        "🚀 Crear y asociar CP",
        type="primary",
        disabled=not confirm or not selected_cases,
        key="azure_create_cases",
    ):
        try:
            cfg = _cfg()
            created, ids = [], []
            resolved_parent = st.session_state.azure_id_padre.strip()
            for tc in selected_cases:
                case_parent = str(tc.get("IDPadre", "")).strip() or resolved_parent
                wi = create_test_case(
                    tc,
                    cfg,
                    parent_id=case_parent,
                    area_path=plan.get("area_path"),
                )
                wid = wi.get("id")
                if not wid:
                    raise AzureDevOpsApiError("Azure no devolvió el ID del Work Item creado.")

                if case_parent:
                    add_parent_relation_to_work_item(wid, case_parent, cfg)

                created.append({
                    "cp_id": tc.get("ID"),
                    "azure_id": wid,
                    "title": tc.get("Title"),
                    "parent_id": case_parent,
                })
                ids.append(wid)

            add_test_cases_to_suite(plan["id"], suite["id"], ids, cfg)
            st.success(f"✅ {len(created)} CP creados, asociados a la Suite {suite.get('id')} y vinculados al Parent informado.")
            st.session_state.azure_upload_result = created
            st.session_state.azure_confirm_upload = False
        except Exception as exc:
            st.error(f"❌ Error durante la carga a Azure: {exc}")

    if st.session_state.get("azure_upload_result"):
        st.dataframe(st.session_state.azure_upload_result, width="stretch", hide_index=True)
