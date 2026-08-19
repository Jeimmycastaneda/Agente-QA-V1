"""UI Azure DevOps.

La red HTTP vive en integrations.azure_devops. Esta capa consulta, permite
seleccionar Plan/Suite/CP y solicita confirmación explícita antes de escribir.
También conserva las funciones de referencia y eliminación local de main.
"""
from __future__ import annotations

import os
import streamlit as st

from agente_qa.integrations.azure_devops import (
    AzureDevOpsConfig,
    AzureDevOpsApiError,
    list_test_plans,
    list_test_suites,
    list_test_cases,
    get_test_case_detail,
    create_test_case,
    add_parent_relation_to_work_item,
    add_test_cases_to_suite,
)
from agente_qa.core.case_management import (
    calculate_cu_coverage,
    delete_generated_case,
    build_reference_preview_case,
)
from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf


def _secret_or_env(secret_name: str, env_name: str | None = None) -> str:
    env_name = env_name or secret_name
    try:
        value = st.secrets.get(secret_name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(env_name, "")).strip()


def _cfg() -> AzureDevOpsConfig:
    organization = _secret_or_env("AZURE_DEVOPS_ORG", "AZDO_ORGANIZATION")
    project = _secret_or_env("AZURE_DEVOPS_PROJECT", "AZDO_PROJECT")
    pat = _secret_or_env("AZURE_DEVOPS_PAT", "AZDO_PAT")
    enabled_value = _secret_or_env("AZDO_ENABLED")
    enabled = enabled_value.lower() in {"1", "true", "yes", "si", "sí"} or bool(pat)
    return AzureDevOpsConfig(organization=organization, project=project, pat=pat, enabled=enabled)


def _render_reference_detail(detail: dict):
    st.markdown("## 📌 Test Case de referencia")
    st.markdown(
        f"**ID:** {detail.get('id', '')}  \n"
        f"**Título:** {detail.get('title', '')}  \n"
        f"**Estado:** {detail.get('state', '')}  \n"
        f"**Area Path:** {detail.get('area_path', '')}"
    )
    st.markdown("### 📝 Description real de Azure")
    st.write(detail.get("description", "") or "Sin Description")
    st.markdown("### 🧪 Steps reales de Azure")
    steps = detail.get("steps", []) or []
    if steps:
        st.dataframe(steps, width="stretch", hide_index=True)
    else:
        st.warning("⚠️ El Test Case de referencia no tiene Steps legibles.")


def render_azure_section():
    st.divider()
    st.subheader("🚀 Cargar CP en Azure DevOps")
    st.caption("La escritura ocurre únicamente después de selección y confirmación explícita.")

    if st.button("🔄 Consultar Test Plans", key="azure_refresh_plans"):
        try:
            st.session_state.azure_plans = list_test_plans(_cfg(), limit=10)
            st.session_state.azure_suites = []
            st.session_state.azure_reference_cases = []
            st.session_state.azure_reference_detail = None
        except Exception as exc:
            st.error(f"No fue posible consultar Test Plans: {exc}")

    plans = st.session_state.get("azure_plans", [])
    if not plans:
        st.info("Consulta los Test Plans para comenzar. La consulta es solo de lectura.")
        return

    plan_labels = [f"{p.get('id')} — {p.get('name', 'Sin nombre')}" for p in plans]
    plan_label = st.selectbox("1️⃣ Test Plan destino", plan_labels, key="azure_plan_select")
    plan = plans[plan_labels.index(plan_label)]

    if st.button("📂 Cargar Suites", key="azure_load_suites"):
        try:
            st.session_state.azure_suites = list_test_suites(plan["id"], _cfg())
            st.session_state.azure_reference_cases = []
            st.session_state.azure_reference_detail = None
        except Exception as exc:
            st.error(f"No fue posible consultar las Suites: {exc}")

    suites = st.session_state.get("azure_suites", [])
    if not suites:
        return

    suite_labels = [f"{s.get('id')} — {s.get('name', 'Suite sin nombre')}" for s in suites]
    suite_label = st.selectbox("2️⃣ Suite destino", suite_labels, key="azure_suite_select")
    suite = suites[suite_labels.index(suite_label)]

    # Referencia Azure: lectura, comparación y preview, sin escritura.
    st.markdown("### 3️⃣ Test Case de referencia")
    if st.button("🔎 Consultar Test Cases de la Suite", key="azure_reference_get_cases"):
        try:
            cases = list_test_cases(plan["id"], suite["id"], _cfg())
            st.session_state.azure_reference_cases = cases
            st.session_state.azure_reference_detail = None
        except Exception as exc:
            st.error(f"No se pudieron consultar los Test Cases: {exc}")

    reference_cases = st.session_state.get("azure_reference_cases", [])
    if reference_cases:
        options = [f"{c.get('id')} — {c.get('title', 'Sin título')}" for c in reference_cases]
        selected_ref = st.selectbox("Test Case real de Azure", options, key="azure_reference_case_select")
        ref_case = reference_cases[options.index(selected_ref)]
        if st.button("🔬 Consultar y comparar", key="azure_reference_compare"):
            try:
                st.session_state.azure_reference_detail = get_test_case_detail(ref_case["id"], _cfg())
            except Exception as exc:
                st.error(f"No se pudo consultar el Test Case de referencia: {exc}")

    reference_detail = st.session_state.get("azure_reference_detail")
    if reference_detail:
        _render_reference_detail(reference_detail)
        current_result = st.session_state.get("result_json")
        if current_result:
            if st.button("🧩 Generar CP nuevo para revisión funcional", key="azure_prepare_new_cp_preview"):
                generated = current_result.get("TEST_CASES", []) or []
                previews = [build_reference_preview_case(reference_detail, tc) for tc in generated]
                preview_result = dict(current_result)
                preview_result["TEST_CASES"] = previews
                st.session_state.azure_reference_preview = previews
                st.session_state.result_json = preview_result
                st.success(f"✅ {len(previews)} CP(s) preparados para revisión funcional.")
                st.rerun()

    # Eliminación local: nunca elimina Work Items de Azure.
    result = st.session_state.get("result_json")
    if result and result.get("TEST_CASES"):
        st.markdown("### 🗑️ Eliminar caso de prueba")
        cases = result.get("TEST_CASES", [])
        options = [f"{i+1}. {tc.get('ID', 'CP')} — {tc.get('Title', '')}" for i, tc in enumerate(cases)]
        selected_delete = st.selectbox("CP a eliminar", options, key="azure_delete_case_select")
        delete_index = options.index(selected_delete)
        confirm_delete = st.checkbox("Confirmo que quiero eliminar este CP de la generación actual.", key="azure_confirm_delete")
        if st.button("🗑️ Eliminar CP seleccionado", disabled=not confirm_delete, key="azure_delete_cp"):
            try:
                st.session_state.result_json = delete_generated_case(result, delete_index)
                st.session_state.excel_data = create_excel(st.session_state.result_json, "Autos Colectivos")
                st.session_state.pdf_data = create_pdf(st.session_state.result_json, "Autos Colectivos", st.session_state.get("source_name", ""))
                st.success("✅ CP eliminado de la generación actual. No se modificó Azure DevOps.")
                st.rerun()
            except Exception as exc:
                st.error(f"🚫 {exc}")

    # Carga real a Azure: conserva la confirmación explícita de main.
    cases = result.get("TEST_CASES", []) if result else []
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
    confirm = st.checkbox("Confirmo que quiero crear los Test Cases seleccionados y asociarlos a esta Suite.", key="azure_confirm_upload")

    if st.button("🚀 Crear y asociar CP", type="primary", disabled=not confirm or not selected_cases, key="azure_create_cases"):
        try:
            cfg = _cfg()
            if not cfg.enabled:
                raise AzureDevOpsApiError("Azure DevOps está deshabilitado. Configura AZDO_ENABLED=true o un PAT válido.")
            created, ids = [], []
            resolved_parent = st.session_state.azure_id_padre.strip()
            for tc in selected_cases:
                case_parent = str(tc.get("IDPadre", "")).strip() or resolved_parent
                wi = create_test_case(tc, cfg, parent_id=case_parent, area_path=plan.get("area_path"))
                wid = wi.get("id")
                if not wid:
                    raise AzureDevOpsApiError("Azure no devolvió el ID del Work Item creado.")
                if case_parent:
                    add_parent_relation_to_work_item(wid, case_parent, cfg)
                created.append({"cp_id": tc.get("ID"), "azure_id": wid, "title": tc.get("Title"), "parent_id": case_parent})
                ids.append(wid)
            add_test_cases_to_suite(plan["id"], suite["id"], ids, cfg)
            st.success(f"✅ {len(created)} CP creados, asociados a la Suite {suite.get('id')} y vinculados al Parent informado.")
            st.session_state.azure_upload_result = created
            st.session_state.azure_confirm_upload = False
        except Exception as exc:
            st.error(f"❌ Error durante la carga a Azure: {exc}")

    if st.session_state.get("azure_upload_result"):
        st.dataframe(st.session_state.azure_upload_result, width="stretch", hide_index=True)
