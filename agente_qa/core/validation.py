import json
import re


REQUIRED_TOP_LEVEL = ("USE_CASES", "TEST_CASES", "ALERTS", "COVERAGE")
REQUIRED_CASE_FIELDS = ("ID", "Title", "Description", "Preconditions", "Steps")


def validate_qa_structure(data):
    if not isinstance(data, dict):
        raise ValueError("La respuesta de Gemini no es un objeto JSON.")

    for key in REQUIRED_TOP_LEVEL:
        if key not in data:
            raise ValueError(f"Falta la clave requerida: {key}")

    if not isinstance(data["USE_CASES"], list) or not data["USE_CASES"]:
        raise ValueError("Gemini no devolvió los Casos de Uso identificados.")
    if not isinstance(data["TEST_CASES"], list) or not data["TEST_CASES"]:
        raise ValueError("No se generaron casos de prueba.")
    if not isinstance(data["ALERTS"], list):
        data["ALERTS"] = []
    if not isinstance(data["COVERAGE"], list):
        data["COVERAGE"] = []

    for index, case in enumerate(data["TEST_CASES"], start=1):
        if not isinstance(case, dict):
            raise ValueError(f"El Test Case #{index} no es un objeto JSON.")
        for field in REQUIRED_CASE_FIELDS:
            if field not in case:
                raise ValueError(f"El Test Case #{index} no contiene el campo requerido: {field}")
        if not isinstance(case.get("Steps"), list):
            raise ValueError(f"El Test Case #{index} tiene Steps con formato inválido.")
        for step_index, step in enumerate(case["Steps"], start=1):
            if not isinstance(step, dict):
                raise ValueError(f"El Test Case #{index}, Step #{step_index}, no es un objeto.")
            for field in ("Step #", "Action", "Expected value"):
                if field not in step:
                    raise ValueError(f"El Test Case #{index}, Step #{step_index}, no contiene: {field}")

    return data


def parse_json_response(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if not match:
            raise
        return json.loads(match.group(1))
