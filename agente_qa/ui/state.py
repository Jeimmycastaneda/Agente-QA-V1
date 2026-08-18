import streamlit as st

def initialize_state():
    defaults = {
        "source_content": "",
        "source_name": "",
        "result_json": None,
        "excel_data": None,
        "pdf_data": None,
        "azure_reference_plans": [],
        "azure_reference_plan_id": None,
        "azure_reference_suites": [],
        "azure_reference_suite_id": None,
        "azure_reference_cases": [],
        "azure_reference_case_id": None,
        "azure_reference_detail": None,
        "azure_reference_preview": None,
        "azure_preview_edit_mode": False,
        "azure_target_plan_id": None,
        "azure_target_suite_id": None,
        "azure_target_suites": [],
        "azure_publish_results": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
