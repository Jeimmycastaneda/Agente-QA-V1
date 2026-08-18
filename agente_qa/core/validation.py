import json

def validate_qa_structure(data):
    if not isinstance(data, dict):
        raise ValueError("La respuesta de Gemini no es un objeto JSON.")
    for key in ("USE_CASES", "TEST_CASES", "ALERTS", "COVERAGE"):
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
    return data

def parse_json_response(text):
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if not m:
            raise
        return json.loads(m.group(1))
