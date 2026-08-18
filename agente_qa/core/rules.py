"""Reglas funcionales centrales del Agente QA.

Estas reglas se mantienen fuera de Streamlit para que la interfaz no sea la fuente
de verdad de la lógica QA.
"""

MIN_CP_PER_USE_CASE = 1
DEFAULT_PRODUCT = "Cotizadores Web"
DEFAULT_MODULE = "Cotizador Autos Colectivos"
DEFAULT_AREA_PATH = r"COTIZADORES WEB\DESARROLLO"
DEFAULT_PROJECT_ORIGIN = "Proyecto"

def split_by_quote_type(scenario_types):
    """Devuelve tipos que deben tratarse como escenarios independientes.

    La división solo aplica cuando la documentación evidencia una regla,
    cálculo, fuente, condición, comportamiento o resultado diferente.
    """
    return [str(x).strip() for x in (scenario_types or []) if str(x).strip()]
