"""Sección de UI para pushear casos de prueba generados a Azure DevOps (Fase 5).

Solo debe llamarse desde `app.py` cuando `config/azure_devops.yaml` tiene
`enabled: true` Y el PAT resuelve vía `agente_qa.secrets.resolve_secret`
(ver `app.py`); esta función además re-verifica ambas condiciones por su
cuenta, así que es segura de invocar directamente. `ui/results.py` no se
toca: los botones de descarga de Excel/PDF siguen exactamente donde estaban,
esta sección es puramente aditiva.

Flujo: probar conexión -> vista previa en dry-run (sin llamadas de
escritura) -> push real explícito, detrás de una confirmación separada.
"""

import streamlit as st

from agente_qa.config import EXCEL_CONFIGS
from agente_qa.errors import ConfigError, IntegrationError
from agente_qa.integrations.azure_devops import AzureDevOpsClient
from agente_qa.secrets import resolve_secret
from agente_qa.security import redact
from agente_qa.settings import load_azure_devops_config


def render_azure_section(result_json: dict, preset_key: str) -> None:
    if not result_json or not result_json.get("TEST_CASES"):
        return

    try:
        cfg = load_azure_devops_config()
    except ConfigError as exc:
        st.error(f"❌ Configuración de Azure DevOps inválida: {exc.user_message}")
        return

    if not cfg.enabled:
        return

    pat = resolve_secret(cfg.pat_secret_name)
    if not pat:
        return

    preset = EXCEL_CONFIGS.get(preset_key)
    if preset is None:
        return

    st.divider()
    st.subheader("🔗 Azure DevOps")
    st.caption(f"Organización: {cfg.organization_url} | Proyecto: {cfg.project or '(sin configurar)'}")
    st.caption(
        "⚠️ El matching de casos existentes se hace por título exacto: dos casos distintos "
        "con el mismo título pueden confundirse. Revisa la vista previa antes de confirmar."
    )

    client = AzureDevOpsClient(cfg, pat)

    if st.button("🔌 Probar conexión", key="azure_check_connection"):
        try:
            project_info = client.check_connection()
            st.success(f"✅ Conectado. Proyecto: {project_info.get('name', cfg.project)}")
        except IntegrationError as exc:
            st.error(f"❌ {exc.user_message}")
            if exc.detail:
                with st.expander("Detalle técnico"):
                    st.code(redact(exc.detail))

    st.markdown("**Vista previa (dry-run — sin cambios en Azure DevOps)**")
    preview_rows = []

    def _collect_preview(idx, total, title, action):
        preview_rows.append({"#": idx, "Título": title, "Acción propuesta": action})

    try:
        dry_result = client.push_test_cases(result_json, preset, dry_run=True, on_progress=_collect_preview)
    except IntegrationError as exc:
        st.error(f"❌ {exc.user_message}")
        return

    if preview_rows:
        st.dataframe(preview_rows, use_container_width=True)

    st.caption(
        f"Se crearían {len(dry_result.created)} caso(s) nuevo(s) y se actualizarían "
        f"{len(dry_result.updated)} existente(s) (según `AzureWorkItemId` ya registrado en "
        "esta sesión; una coincidencia por título adicional puede aparecer recién en el push real)."
    )
    if dry_result.skipped:
        st.warning("Casos omitidos: " + "; ".join(dry_result.skipped))

    allow_duplicates = st.checkbox(
        "Crear como nuevos (permitir duplicados)",
        key="azure_allow_duplicates",
        help=(
            "Si se activa, el push real no busca casos existentes por título antes de "
            "crear: cada caso se crea como un Test Case nuevo, incluso si ya existe uno "
            "con el mismo título."
        ),
    )

    confirm_push = st.checkbox(
        "Confirmo que quiero ejecutar el push real a Azure DevOps",
        key="azure_confirm_push",
    )

    if st.button("🚀 Ejecutar push real", key="azure_real_push", disabled=not confirm_push):
        with st.spinner("Enviando casos a Azure DevOps..."):
            try:
                push_result = client.push_test_cases(
                    result_json,
                    preset,
                    dry_run=False,
                    skip_title_match=allow_duplicates,
                )
            except IntegrationError as exc:
                st.error(f"❌ {exc.user_message}")
                if exc.detail:
                    with st.expander("Detalle técnico"):
                        st.code(redact(exc.detail))
                return

        st.success(
            f"Push completo: {len(push_result.created)} creado(s), "
            f"{len(push_result.updated)} actualizado(s), {len(push_result.failed)} fallido(s)."
        )
        for title, reason in push_result.failed:
            st.error(f"❌ {title}: {reason}")
