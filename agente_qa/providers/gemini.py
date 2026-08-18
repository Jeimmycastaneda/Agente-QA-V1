"""Proveedor Gemini aislado del resto de la aplicación."""

import json
import re

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

from .base import QAProvider

SCHEMA = {
    "type": "object",
    "properties": {
        "USE_CASES": {"type": "array"},
        "TEST_CASES": {"type": "array"},
        "ALERTS": {"type": "array"},
        "COVERAGE": {"type": "array"},
    },
    "required": ["USE_CASES", "TEST_CASES", "ALERTS", "COVERAGE"],
}

class GeminiProvider(QAProvider):
    def __init__(self, api_key, model="gemini-3.6-flash"):
        if genai is None:
            raise RuntimeError("No está instalada la librería google-genai.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, prompt_text, source_content, **kwargs):
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA,
            max_output_tokens=32768,
        )
        full_prompt = (
            prompt_text
            + "\n\n================ FUENTE =================\n"
            + source_content
            + "\n\n================ SALIDA =================\n"
            "Devuelve exclusivamente JSON válido."
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=full_prompt,
            config=config,
        )
        text = (response.text or "").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if not match:
                raise RuntimeError("Gemini no devolvió JSON válido.")
            return json.loads(match.group(1))
