"""Editor de casos de prueba con experiencia tipo Azure DevOps.

Modulo de compatibilidad requerido por app.py. No contiene credenciales ni
realiza llamadas a Azure; solo edita el TEST_CASE en memoria de Streamlit.
"""
from __future__ import annotations

import streamlit as st


def _text(value, default=""):
    if value is None:
        return default
    return str(value)


def _steps(tc):
    value = tc.get("Steps", [])
    return value if isinstance(value, list) else []


def render_azure_style_editor(test_case, selected_index=0):
    """Renderiza el editor y actualiza el diccionario del CP en memoria.

    Retorna 'saved' cuando el usuario guarda y None en cualquier otro caso.
    """
    tc = test_case
    with st.form(key=f"azure_case_editor_{selected_index}", clear_on_submit=False):
        st.markdown("#### Datos del Test Case")
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("Title", value=_text(tc.get("Title")))
            product = st.text_input("Product", value=_text(tc.get("Product")))
            module = st.text_input("Module", value=_text(tc.get("Module")))
            related = st.text_input(
                "Requirement / Use Case",
                value=_text(tc.get("Related Use Case") or tc.get("RelatedUseCase")),
            )
        with c2:
            scenario = st.text_area("Scenario", value=_text(tc.get("Scenario")), height=90)
            description = st.text_area("Description", value=_text(tc.get("Description")), height=150)
            expected = st.text_area(
                "Expected Result",
                value=_text(tc.get("Expected Result") or tc.get("ExpectedResult")),
                height=110,
            )
            preconditions = st.text_area(
                "Preconditions", value=_text(tc.get("Preconditions")), height=100
            )

        c3, c4 = st.columns(2)
        with c3:
            criterion = st.text_input("Criterion", value=_text(tc.get("Criterion")))
            scenario_type = st.text_input(
                "Scenario Type", value=_text(tc.get("Scenario Type"))
            )
        with c4:
            validation = st.text_input(
                "Validation Method", value=_text(tc.get("Validation Method"))
            )
            effort = st.text_input("Effort", value=_text(tc.get("Effort")))

        st.markdown("#### 🧪 Steps")
        steps = _steps(tc)
        edited_steps = []
        for pos, step in enumerate(steps, start=1):
            st.markdown(f"**Paso {pos}**")
            a, b = st.columns(2)
            with a:
                action = st.text_area(
                    f"Action {pos}",
                    value=_text(step.get("Action")),
                    height=90,
                    key=f"azure_action_{selected_index}_{pos}",
                )
            with b:
                expected_step = st.text_area(
                    f"Expected {pos}",
                    value=_text(step.get("Expected value", step.get("Expected"))),
                    height=90,
                    key=f"azure_expected_{selected_index}_{pos}",
                )
            edited_steps.append(
                {
                    "Step #": step.get("Step #", pos),
                    "Action": action,
                    "Expected value": expected_step,
                }
            )

        saved = st.form_submit_button("💾 Guardar cambios", type="primary")

    if saved:
        tc["Title"] = title
        tc["Product"] = product
        tc["Module"] = module
        tc["Related Use Case"] = related
        tc["Scenario"] = scenario
        tc["Description"] = description
        tc["Expected Result"] = expected
        tc["Preconditions"] = preconditions
        tc["Criterion"] = criterion
        tc["Scenario Type"] = scenario_type
        tc["Validation Method"] = validation
        tc["Effort"] = effort
        tc["Steps"] = edited_steps
        return "saved"
    return None


def delete_test_case(result, selected_index):
    """Elimina el CP indicado de TEST_CASES y mantiene COVERAGE coherente."""
    cases = result.get("TEST_CASES", [])
    if not isinstance(cases, list) or selected_index < 0 or selected_index >= len(cases):
        return False

    deleted = cases.pop(selected_index)
    deleted_id = _text(deleted.get("ID")).strip()

    coverage = result.get("COVERAGE")
    if isinstance(coverage, list):
        result["COVERAGE"] = [
            row for row in coverage
            if _text(row.get("Test Case") or row.get("Test Case ID") or row.get("ID")).strip() != deleted_id
        ]

    return True
