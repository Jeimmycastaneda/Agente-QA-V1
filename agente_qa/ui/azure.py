"""Interfaz Azure DevOps equivalente a main, separada de la capa HTTP."""
from __future__ import annotations

import os
import re
import pandas as pd
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
from agente_qa.core.case_management import delete_generated_case, build_reference_preview_case
from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf


def _secret(name: str, env_name: str | None = None) -> str:
    env_name = env_name or name
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or os.getenv(env_name, "")).strip()


def _cfg() -> AzureDevOpsConfig:
    org = _secret("AZURE_DEVOPS_ORG", "AZDO_ORGANIZATION")
    project = _secret("AZURE_DEVOPS_PROJECT", "AZDO_PROJECT")
    pat = _secret("AZURE_DEVOPS_PAT", "AZDO_PAT")
    enabled = _secret("AZDO_ENABLED").lower() in {"1", "true", "yes", "si", "sí"} or bool(pat)
    return AzureDevOpsConfig(organization=org, project=project, pat=pat, enabled=enabled)


def _text(value, default=""):
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def _case_title(tc, case_id=""):
    title = re.sub(r"\s+", " ", _text(tc.get("Title"))).strip()
    if not title or title.casefold() == _text(case_id).casefold() or re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}", title, re.I):
        for candidate in (tc.get("Scenario"), tc.get("Description"), tc.get("Related Use Case")):
            candidate = re.sub(r"\s+", " ", _text(candidate)).strip()
            if candidate and candidate.casefold() != _text(case_id).casefold():
                return candidate
    return title or f"Caso de prueba {_text(case_id, 'CP')}"


def _config_key():
    return st.session_state.get("qa_settings", {}).get("config_key", "Autos Colectivos")


def _rebuild_exports(result):
    st.session_state.excel_data = create_excel(result, _config_key())
    st.session_state.pdf_data = create_pdf(result, _config_key(), st.session_state.get("source_name", ""))


def _render_reference_detail(detail):
    st.markdown("## 📌 Test Case de referencia")
    st.markdown(
        f"**ID:** {_text(detail.get('id'))}  \n"
        f"**Título:** {_text(detail.get('title'))}  \n"
        f"**Estado:** {_text(detail.get('state'))}  \n"
        f"**Area Path:** {_text(detail.get('area_path'))}"
    )
    st.markdown("### 📝 Description real de Azure")
    st.write(detail.get("description", "") or "Sin Description")
    st.markdown("### 🧪 Steps reales de Azure")
    steps = detail.get("steps", []) or []
    if steps:
        st.dataframe(pd.DataFrame(steps), width="stretch", hide_index=True)
    else:
        st.warning("⚠️ El Test Case de referencia no tiene Steps legibles.")


def _reference_checks(detail):
    description = _text(detail.get("description")).lower()
    steps = detail.get("steps", []) or []
    return {
        "Producto dentro de Description": "producto:" in description,
        "Módulo dentro de Description": "módulo:" in description or "modulo:" in description,
        "Descripción dentro de Description": "descripción:" in description or "descripcion:" in description,
        "Resultado esperado dentro de Description": "resultado esperado de la prueba:" in description,
        "Precondiciones dentro de Description": "precondiciones:" in description,
        "Caso de uso relacionado dentro de Description": "caso de uso relacionado:" in description,
        "Steps con Action + Expected": bool(steps) and all(_text(s.get("Action")) and _text(s.get("Expected value")) for s in steps),
    }


def render_azure_section():
    st.divider()
    st.subheader("🚀 Azure DevOps")
    st.caption("Las consultas son de solo lectura. La escritura ocurre únicamente después de selección y confirmación explícita.")
    cfg = _cfg()

    # ---------------- Referencia: Plan -> Suite -> CP ----------------
    if st.button("📋 Consultar 10 Test Plans", key="azure_list_test_plans"):
        try:
            with st.spinner("Consultando los 10 Test Plans más recientes..."):
                st.session_state.azure_reference_plans = list_test_plans(cfg, limit=10)
            st.session_state.azure_reference_suites = []
            st.session_state.azure_reference_cases = []
            st.session_state.azure_reference_detail = None
            st.session_state.azure_reference_plan_id = None
            st.session_state.azure_reference_suite_id = None
            st.success(f"✅ {len(st.session_state.azure_reference_plans)} Test Plan(s) consultados.")
        except Exception as exc:
            st.error(f"❌ No se pudieron consultar los Test Plans: {exc}")

    plans = st.session_state.get("azure_reference_plans", []) or []
    if plans:
        plan_labels = [f"{_text(p.get('id'), 'SIN ID')} — {_text(p.get('name'), 'Test Plan sin nombre')}" for p in plans]
        plan_label = st.selectbox("1️⃣ Test Plan", plan_labels, key="azure_reference_plan_select")
        plan = plans[plan_labels.index(plan_label)]
        if st.button("🔎 Consultar Suites", key="azure_reference_get_suites"):
            try:
                st.session_state.azure_reference_suites = list_test_suites(plan["id"], cfg)
                st.session_state.azure_reference_plan_id = plan["id"]
                st.session_state.azure_reference_cases = []
                st.session_state.azure_reference_detail = None
                st.success(f"✅ {len(st.session_state.azure_reference_suites)} Suite(s) encontradas.")
            except Exception as exc:
                st.error(f"❌ No se pudieron consultar las Suites: {exc}")

    suites = st.session_state.get("azure_reference_suites", []) or []
    if suites:
        suite_labels = [f"{_text(s.get('id'), 'SIN ID')} — {_text(s.get('name'), 'Suite sin nombre')}" for s in suites]
        suite_label = st.selectbox("2️⃣ Suite", suite_labels, key="azure_reference_suite_select")
        suite = suites[suite_labels.index(suite_label)]
        if st.button("🔎 Consultar Test Cases", key="azure_reference_get_cases"):
            try:
                st.session_state.azure_reference_cases = list_test_cases(plan["id"], suite["id"], cfg)
                st.session_state.azure_reference_suite_id = suite["id"]
                st.session_state.azure_reference_detail = None
                st.success(f"✅ {len(st.session_state.azure_reference_cases)} Test Case(s) encontrados.")
            except Exception as exc:
                st.error(f"❌ No se pudieron consultar los Test Cases: {exc}")

    reference_cases = st.session_state.get("azure_reference_cases", []) or []
    if reference_cases:
        valid = [c for c in reference_cases if _text(c.get("id"))]
        options = [f"{_text(c.get('id'))} — {_text(c.get('title'), 'Test Case sin título')}" for c in valid]
        selected_ref = st.selectbox("3️⃣ Test Case de referencia", options, key="azure_reference_case_select")
        ref = valid[options.index(selected_ref)]
        if st.button("🔬 Consultar y comparar", key="azure_reference_compare"):
            try:
                st.session_state.azure_reference_detail = get_test_case_detail(ref["id"], cfg)
            except Exception as exc:
                st.error(f"❌ No se pudo consultar el Test Case: {exc}")

    detail = st.session_state.get("azure_reference_detail")
    if detail:
        _render_reference_detail(detail)
        checks = _reference_checks(detail)
        st.markdown("### 🔎 Comparación contra estructura aprobada")
        st.dataframe(pd.DataFrame([{"Elemento": k, "Cumple": "✅" if v else "⚠️"} for k, v in checks.items()]), width="stretch", hide_index=True)
        if all(checks.values()):
            st.success("✅ La referencia contiene la estructura aprobada.")
        else:
            st.warning("⚠️ La referencia no contiene todos los elementos esperados. Se conserva como referencia y no se inventan datos.")

        result = st.session_state.get("result_json")
        if result and st.button("🧩 Generar CP nuevo para revisión funcional", key="azure_prepare_new_cp_preview"):
            try:
                cases = result.get("TEST_CASES", []) or []
                if not cases:
                    raise ValueError("No hay Test Cases generados a partir de la HU.")
                previews = [build_reference_preview_case(detail, tc) for tc in cases]
                new_result = dict(result)
                new_result["TEST_CASES"] = previews
                st.session_state.azure_reference_preview = previews
                st.session_state.azure_preview_edit_mode = True
                st.session_state.result_json = new_result
                st.success(f"✅ {len(previews)} CP(s) preparados para revisión funcional. No se escribió en Azure.")
                st.rerun()
            except Exception as exc:
                st.error(f"❌ No se pudo preparar el preview: {exc}")

    # ---------------- Eliminación local ----------------
    result = st.session_state.get("result_json")
    if result and result.get("TEST_CASES"):
        st.markdown("### 🗑️ Eliminar caso de prueba")
        cases = result.get("TEST_CASES", []) or []
        options = [f"{_text(tc.get('ID'), f'CASO-{i+1:05d}')} — {_case_title(tc, _text(tc.get('ID')))}" for i, tc in enumerate(cases)]
        label = st.selectbox("Selecciona el CP que deseas eliminar", options, key="azure_delete_case_select")
        index = options.index(label)
        confirm = st.checkbox("Confirmo que quiero eliminar este CP de la generación actual.", key="azure_confirm_delete")
        if st.button("🗑️ Eliminar CP seleccionado", disabled=not confirm, key="azure_delete_cp"):
            try:
                st.session_state.result_json = delete_generated_case(result, index)
                _rebuild_exports(st.session_state.result_json)
                st.success("✅ CP eliminado de la generación actual. Azure no fue modificado.")
                st.rerun()
            except Exception as exc:
                st.error(f"🚫 {exc}")

    # ---------------- Carga real ----------------
    if not result or not result.get("TEST_CASES"):
        return

    st.markdown("### 🚀 Cargar CP en Azure DevOps")
    case_map = {_text(tc.get("ID")): tc for tc in result.get("TEST_CASES", []) if _text(tc.get("ID"))}
    selection_mode = st.radio("Casos a cargar", ["Un solo CP", "Seleccionar varios CP", "Todos los CP"], horizontal=True, key="azure_publish_selection")
    ids = list(case_map)
    if selection_mode == "Un solo CP":
        chosen = st.selectbox("CP a cargar", ids, format_func=lambda x: f"{x} — {_case_title(case_map[x], x)[:100]}", key="azure_publish_single_case") if ids else None
        selected_ids = [chosen] if chosen else []
    elif selection_mode == "Seleccionar varios CP":
        selected_ids = st.multiselect("Selecciona los CP que deseas cargar", ids, format_func=lambda x: f"{x} — {_case_title(case_map[x], x)[:100]}", key="azure_publish_multi_cases")
    else:
        selected_ids = ids
        st.info(f"Se cargarán los {len(selected_ids)} CP generados actualmente.")

    target_plan = None
    target_suite = None
    if plans:
        plan_labels = [f"{_text(p.get('id'))} — {_text(p.get('name'), 'Sin nombre')}" for p in plans]
        target_plan_label = st.selectbox("Test Plan destino", plan_labels, key="azure_publish_target_plan")
        target_plan = plans[plan_labels.index(target_plan_label)]
        target_plan_id = target_plan.get("id")
        if st.session_state.get("azure_target_plan_id") != str(target_plan_id):
            st.session_state.azure_target_plan_id = str(target_plan_id)
            try:
                st.session_state.azure_target_suites = list_test_suites(target_plan_id, cfg)
            except Exception as exc:
                st.session_state.azure_target_suites = []
                st.error(f"❌ No se pudieron consultar las Suites del destino: {exc}")
        target_suites = st.session_state.get("azure_target_suites", []) or []
        if target_suites:
            suite_labels = [f"{_text(s.get('id'))} — {_text(s.get('name'), 'Suite sin nombre')}" for s in target_suites]
            target_suite_label = st.selectbox("Suite destino", suite_labels, key="azure_publish_target_suite")
            target_suite = target_suites[suite_labels.index(target_suite_label)]

    if not target_plan or not target_suite or not selected_ids:
        if not plans:
            st.warning("⚠️ Primero consulta los 10 Test Plans más recientes.")
        return

    st.markdown("### Datos obligatorios del proyecto")
    st.caption("IDPadre es el Work Item padre/HU. Related Work → Parent se configura con el ID de la Suite destino, igual que en main.")
    first = case_map[selected_ids[0]]
    inferred = _text(first.get("IDPadre"), first.get("ID Padre"), first.get("Parent ID"))
    parent_field = st.text_input("IDPadre (Work Item padre / HU)", value=_text(st.session_state.get("azure_id_padre"), inferred), key="azure_id_padre_input")
    st.session_state.azure_id_padre = parent_field.strip()
    tipo_origen = st.text_input("Tipo Origen Proyecto", value=_text(st.session_state.get("azure_tipo_origen_proyecto"), "Proyecto"), key="azure_tipo_origen_input")
    st.session_state.azure_tipo_origen_proyecto = tipo_origen.strip() or "Proyecto"

    duplicate_ids = []
    try:
        existing = list_test_cases(target_plan["id"], target_suite["id"], cfg)
        existing_titles = {re.sub(r"\s+", " ", _text(x.get("title"))).strip().casefold() for x in existing}
        for cp_id in selected_ids:
            if re.sub(r"\s+", " ", _case_title(case_map[cp_id], cp_id)).strip().casefold() in existing_titles:
                duplicate_ids.append(cp_id)
    except Exception as exc:
        st.warning(f"⚠️ No fue posible validar duplicados antes de la creación: {exc}")

    if duplicate_ids:
        st.error("🚫 Se detectaron títulos existentes en la Suite destino: " + ", ".join(duplicate_ids) + ". La creación queda bloqueada.")

    can_sync = bool(selected_ids and target_plan and target_suite and not duplicate_ids and st.session_state.get("azure_id_padre"))
    if can_sync:
        st.success(f"Destino listo: Test Plan {target_plan.get('id')} — {target_plan.get('name')} | Suite {target_suite.get('id')} — {target_suite.get('name')} | CP: {len(selected_ids)}")
    else:
        st.warning("Completa CP, Test Plan, Suite, IDPadre y corrige duplicados antes de sincronizar.")

    review_rows = [{"CP": cp_id, "Título": _case_title(case_map[cp_id], cp_id), "Caso de Uso": _text(case_map[cp_id].get("Related Use Case"), "Pendiente"), "Steps": len(case_map[cp_id].get("Steps", []) or [])} for cp_id in selected_ids]
    st.dataframe(pd.DataFrame(review_rows), width="stretch", hide_index=True)
    confirm = st.checkbox("Confirmo CP, Test Plan, Suite, IDPadre y Tipo Origen Proyecto y autorizo la creación en Azure.", key="azure_publish_confirm")
    if st.button("🔄 Sincronizar con Azure DevOps", type="primary", disabled=not (can_sync and confirm), key="azure_publish_execute"):
        created, errors, work_ids = [], [], []
        for cp_id in selected_ids:
            tc = dict(case_map[cp_id])
            tc["IDPadre"] = st.session_state.azure_id_padre
            tc["Tipo Origen Proyecto"] = st.session_state.azure_tipo_origen_proyecto
            try:
                wi = create_test_case(tc, cfg, parent_id=st.session_state.azure_id_padre, area_path=target_plan.get("area_path"))
                wid = wi.get("id")
                if not wid:
                    raise AzureDevOpsApiError("Azure no devolvió el ID del Work Item creado.")
                # Igual que main: IDPadre es el campo del Work Item; Parent relation usa la Suite destino.
                add_parent_relation_to_work_item(wid, target_suite["id"], cfg)
                work_ids.append(int(wid))
                created.append({"cp_id": cp_id, "azure_id": wid, "parent_id": target_suite["id"], "status": "Work Item creado y Parent configurado"})
            except Exception as exc:
                errors.append({"cp_id": cp_id, "error": str(exc)})
        if work_ids:
            try:
                add_test_cases_to_suite(target_plan["id"], target_suite["id"], work_ids, cfg)
                for row in created:
                    row["status"] = "Creado, Parent configurado y asociado a la Suite"
            except Exception as exc:
                errors.append({"cp_id": "LOTE", "error": str(exc)})
        st.session_state.azure_publish_results = {"created": created, "errors": errors}
        st.rerun()

    publish_result = st.session_state.get("azure_publish_results")
    if publish_result:
        st.markdown("### 📌 Resultado de la creación en Azure")
        if publish_result.get("created"):
            st.dataframe(pd.DataFrame(publish_result["created"]), width="stretch", hide_index=True)
            st.success(f"✅ {len(publish_result['created'])} CP procesados en Azure.")
        for err in publish_result.get("errors", []):
            st.error(f"❌ {_text(err.get('cp_id'))}: {_text(err.get('error'))}")
