import streamlit as st

_DEFAULTS = {
    "source_content": "",
    "source_name": "",
    "source_hash": "",
    "result_json": None,
    "excel_data": None,
    "pdf_data": None,
}


def init_session_state():
    for key, value in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
