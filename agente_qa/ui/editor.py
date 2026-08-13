import pandas as pd
import streamlit as st

from agente_qa.export.excel import create_excel
from agente_qa.export.pdf import create_pdf
from agente_qa.utils import build_case_title, safe_steps, safe_text

# ============================================================
# EDITOR DE CASOS DE PRUEBA — REVISIÓN QA
# ============================================================


def render_case_editor(result, selected_config):
    st.subheader("✏️ Editar caso de prueba")
    st.caption(
        "Revisa y ajusta los casos generados antes de descargar el Excel o PDF. "
        "El TestCaseId es inmutable para conservar la trazabilidad."
    )

    case_options = []
    for idx, tc in enumerate(result.get("TEST_CASES", [])):
        case_id = safe_text(tc.get("ID"), f"CASO-{idx + 1:05d}")
        case_title = build_case_title(tc, case_id)
        case_options.append(
            f"{case_id} — {case_title[:100]}"
        )

    selected_case_label = st.selectbox(
        "Selecciona el caso que deseas editar",
        case_options,
        key="qa_editor_selected_case",
    )

    selected_index = case_options.index(selected_case_label)
    selected_case = result["TEST_CASES"][selected_index]
    selected_case_id = safe_text(
        selected_case.get("ID"),
        f"CASO-{selected_index + 1:05d}",
    )

    with st.form(
        f"qa_case_editor_form_{selected_index}",
        clear_on_submit=False,
    ):
        st.markdown(f"### {selected_case_id}")
        st.info(
            "El ID no se puede modificar. Los cambios guardados se utilizarán "
            "para regenerar el Excel y el PDF."
        )

        e1, e2 = st.columns(2)

        with e1:
            edited_title = st.text_input(
                "Title",
                value=build_case_title(selected_case, selected_case_id),
            )
            edited_product = st.text_input(
                "Product",
                value=safe_text(selected_case.get("Product")),
            )
            edited_module = st.text_input(
                "Module",
                value=safe_text(selected_case.get("Module")),
            )
            edited_related = st.text_input(
                "Requirement / Use Case",
                value=safe_text(selected_case.get("Related Use Case")),
            )
            edited_criterion = st.text_input(
                "Criterion",
                value=safe_text(selected_case.get("Criterion")),
            )
            edited_scenario_type = st.text_input(
                "Scenario Type",
                value=safe_text(selected_case.get("Scenario Type")),
            )
            edited_validation = st.text_input(
                "Validation Method",
                value=safe_text(selected_case.get("Validation Method")),
            )

        with e2:
            edited_scenario = st.text_area(
                "Scenario",
                value=safe_text(selected_case.get("Scenario")),
                height=90,
            )
            edited_description = st.text_area(
                "Description",
                value=safe_text(selected_case.get("Description")),
                height=110,
            )
            edited_expected = st.text_area(
                "Expected Result",
                value=safe_text(selected_case.get("Expected Result")),
                height=110,
            )
            edited_preconditions = st.text_area(
                "Preconditions",
                value=safe_text(selected_case.get("Preconditions")),
                height=110,
            )

        e3, e4 = st.columns(2)
        with e3:
            edited_coverage = st.text_input(
                "Coverage",
                value=safe_text(selected_case.get("Coverage")),
            )
        with e4:
            edited_effort = st.text_input(
                "Effort",
                value=safe_text(selected_case.get("Effort")),
            )

        st.markdown("#### 🧪 Steps")
        current_steps = safe_steps(selected_case)
        step_rows = []
        for pos, step in enumerate(current_steps, start=1):
            step_rows.append(
                {
                    "Step #": step.get("Step #", pos),
                    "Action": safe_text(step.get("Action")),
                    "Expected value": safe_text(step.get("Expected value")),
                }
            )

        if not step_rows:
            step_rows = [
                {
                    "Step #": 1,
                    "Action": "",
                    "Expected value": "",
                }
            ]

        edited_steps_df = st.data_editor(
            pd.DataFrame(step_rows),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Step #": st.column_config.NumberColumn(
                    "Step #",
                    min_value=1,
                    step=1,
                ),
                "Action": st.column_config.TextColumn(
                    "Action",
                    width="large",
                ),
                "Expected value": st.column_config.TextColumn(
                    "Expected value",
                    width="large",
                ),
            },
            key=f"qa_steps_editor_{selected_index}",
        )

        st.markdown("#### 🚨 Alertas del caso")
        current_alerts = selected_case.get("Alerts", [])
        if not isinstance(current_alerts, list):
            current_alerts = []

        alert_text = "\n".join(
            (
                f"{safe_text(a.get('Alert'))} | "
                f"{safe_text(a.get('Reason'))} | "
                f"{safe_text(a.get('Validation Required'))}"
            )
            for a in current_alerts
            if isinstance(a, dict)
        )

        edited_alerts = st.text_area(
            "Una alerta por línea: Alerta | Razón | Validación requerida",
            value=alert_text,
            height=100,
            help=(
                "Si no hay alertas, deja este campo vacío. "
                "No se agregan columnas nuevas al Excel."
            ),
        )

        save_case = st.form_submit_button(
            "💾 Guardar cambios del caso",
            type="primary",
        )

    if save_case:
        # Guardar campos editados sin alterar el ID.
        selected_case["Title"] = edited_title.strip()
        selected_case["Product"] = edited_product.strip()
        selected_case["Module"] = edited_module.strip()
        selected_case["Related Use Case"] = edited_related.strip()
        selected_case["Criterion"] = edited_criterion.strip()
        selected_case["Scenario Type"] = edited_scenario_type.strip()
        selected_case["Validation Method"] = edited_validation.strip()
        selected_case["Scenario"] = edited_scenario.strip()
        selected_case["Description"] = edited_description.strip()
        selected_case["Expected Result"] = edited_expected.strip()
        selected_case["Preconditions"] = edited_preconditions.strip()
        selected_case["Coverage"] = edited_coverage.strip()
        selected_case["Effort"] = edited_effort.strip()

        # Normalizar Steps y renumerarlos.
        normalized_steps = []
        for pos, row in edited_steps_df.reset_index(drop=True).iterrows():
            action = safe_text(row.get("Action"))
            expected = safe_text(row.get("Expected value"))
            if not action and not expected:
                continue

            normalized_steps.append(
                {
                    "Step #": pos + 1,
                    "Action": action,
                    "Expected value": expected,
                }
            )

        selected_case["Steps"] = normalized_steps

        # Normalizar alertas manuales.
        normalized_alerts = []
        for line in edited_alerts.splitlines():
            line = line.strip()
            if not line:
                continue

            parts = [part.strip() for part in line.split("|", 2)]
            while len(parts) < 3:
                parts.append("")

            normalized_alerts.append(
                {
                    "Alert": parts[0],
                    "Reason": parts[1],
                    "Validation Required": parts[2],
                }
            )

        selected_case["Alerts"] = normalized_alerts

        # Marcar el caso como revisado manualmente sin agregarlo al Excel.
        selected_case["_edited_by_qa"] = True

        # Las salidas siempre se regeneran desde result, incluyendo los cambios.
        st.session_state.excel_data = create_excel(
            result,
            selected_config,
        )
        st.session_state.pdf_data = create_pdf(
            result,
            selected_config,
            st.session_state.get("source_name", ""),
        )

        st.success(
            f"✅ {selected_case_id} actualizado. "
            "Excel y PDF regenerados con los cambios."
        )
        st.rerun()
