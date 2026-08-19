"""Proveedor Gemini aislado del resto de la aplicación."""
from __future__ import annotations

import json
import os
import re
import time

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

DEFAULT_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
)


def _json_from_response(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if not match:
            raise RuntimeError("Gemini no devolvió JSON válido.")
        return json.loads(match.group(1))


class GeminiProvider(QAProvider):
    def __init__(self, api_key: str, model: str | None = None, max_retries: int = 1):
        if genai is None:
            raise RuntimeError("No está instalada la librería google-genai.")
        if not api_key:
            raise ValueError("API Key de Gemini no configurada.")
        self.client = genai.Client(api_key=api_key)
        configured = os.getenv("GEMINI_MODELS", "")
        env_models = tuple(x.strip() for x in configured.split(",") if x.strip())
        selected = model or os.getenv("GEMINI_MODEL", "")
        candidates = []
        for candidate in (selected, *env_models, *DEFAULT_MODELS):
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        self.models = tuple(candidates)
        self.model = self.models[0]
        self.max_retries = max(0, int(max_retries))

    def _generate_once(self, model: str, full_prompt: str):
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SCHEMA,
            max_output_tokens=32768,
        )
        return self.client.models.generate_content(
            model=model,
            contents=full_prompt,
            config=config,
        )

    def generate(self, prompt_text, source_content, **kwargs):
        if not source_content or not str(source_content).strip():
            raise ValueError("Fuente de información vacía.")

        full_prompt = (
            str(prompt_text)
            + "\n\n================ FUENTE =================\n"
            + str(source_content)
            + "\n\n================ SALIDA =================\n"
            "Devuelve exclusivamente JSON válido."
        )

        errors = []
        for model in self.models:
            for attempt in range(self.max_retries + 1):
                try:
                    response = self._generate_once(model, full_prompt)
                    text = (response.text or "").strip()
                    if not text:
                        raise RuntimeError(f"{model}: Gemini devolvió una respuesta vacía.")
                    return _json_from_response(text)
                except Exception as exc:
                    detail = str(exc)
                    errors.append(f"{model} / intento {attempt + 1}: {detail[:1200]}")
                    lower = detail.lower()
                    quota = "429" in detail or "quota" in lower or "resource exhausted" in lower
                    retryable = quota or any(x in lower for x in ("500", "503", "internal", "unavailable", "timeout", "deadline"))
                    if retryable and attempt < self.max_retries and not quota:
                        time.sleep(2 * (attempt + 1))
                        continue
                    # Cuota, modelo no disponible, request inválido o error de esquema:
                    # abandonar este modelo y probar el siguiente sin insistir.
                    break

        raise RuntimeError(
            "Gemini no pudo completar la generación con los modelos probados.\n\n"
            + "\n".join(errors[-8:])
        )
