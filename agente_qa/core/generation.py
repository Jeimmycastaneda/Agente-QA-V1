"""Orquestación de generación QA.

La implementación del proveedor está en providers/gemini.py. Este módulo no
depende de Streamlit para poder probar el motor de forma aislada.
"""

from .validation import validate_qa_structure
from .coverage import validate_minimum_cu_coverage

def generate_qa_data(provider, prompt_text, source_content, **kwargs):
    if not source_content or not source_content.strip():
        raise ValueError("Fuente de información vacía.")
    data = provider.generate(prompt_text, source_content, **kwargs)
    data = validate_qa_structure(data)
    validate_minimum_cu_coverage(data)
    return data
