"""Gemini provider.

Module-level functions (`get_valid_models`, `build_client`, `generate_once`,
`extract_error_detail`) are the thin, direct wrapper around `google-genai`
and stay importable/monkeypatchable on their own, as tests already rely on.
`GeminiProvider` is the `LLMProvider` (see `providers/base.py`) built on top
of them: it owns full-prompt assembly, JSON parsing, and error
classification, so `generation.py` never has to know Gemini exists.
"""

import json
import re

from agente_qa.config import FALLBACK_MODELS, SCHEMA
from agente_qa.errors import BadRequestError, ProviderError, QuotaError, TransientError
from agente_qa.providers.base import GenerationResult

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def get_valid_models(api_key):
    if genai is None:
        return FALLBACK_MODELS

    try:
        client = genai.Client(api_key=api_key)
        names = []
        for model in client.models.list():
            name = model.name.split("/")[-1]
            if "gemini" in name.lower():
                names.append(name)
        return sorted(set(names)) or FALLBACK_MODELS
    except Exception:
        return FALLBACK_MODELS


def extract_error_detail(exc):
    raw = str(exc)
    # Keep the useful API message but avoid dumping huge exception payloads.
    return raw[:1800]


def build_client(api_key):
    return genai.Client(api_key=api_key)


def generate_once(client, model_name, full_prompt, *, schema=None, max_output_tokens=32768):
    """
    V10:
    - Gemini 3.x: no temperature/top_p/top_k.
    - Uses structured JSON output.
    - Limits output tokens for stability (default 32K).
    """
    # google-genai actual Python SDK format:
    # response_mime_type + response_schema.
    # Do NOT use response_format here; that shape is rejected by
    # GenerateContentConfig in the installed SDK.
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=SCHEMA if schema is None else schema,
        max_output_tokens=max_output_tokens,
    )

    return client.models.generate_content(
        model=model_name,
        contents=full_prompt,
        config=config,
    )


class GeminiProvider:
    """LLMProvider implementation wrapping `google-genai`."""

    name = "gemini"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def list_models(self) -> list:
        return get_valid_models(self.api_key)

    def default_models(self) -> list:
        return list(FALLBACK_MODELS)

    def generate(self, request) -> GenerationResult:
        if genai is None:
            raise ProviderError(
                user_message="No está instalada la librería google-genai.",
                detail="google-genai not installed",
            )

        if not self.api_key:
            raise ProviderError(
                user_message="API Key no configurada.",
                detail="GeminiProvider.generate called with an empty api_key",
            )

        full_prompt = (
            request.prompt
            + "\n\n==================== FUENTE PROPORCIONADA POR EL USUARIO ====================\n"
            + request.source
            + "\n\n==================== REGLA DE SALIDA ====================\n"
            "Devuelve exclusivamente JSON válido que cumpla el esquema solicitado. "
            "No agregues explicaciones fuera del JSON."
        )

        try:
            client = build_client(self.api_key)
            response = generate_once(
                client,
                request.model,
                full_prompt,
                schema=self._to_provider_schema(request.schema),
                max_output_tokens=request.max_output_tokens,
            )
        except Exception as exc:
            raise self._classify(exc) from exc

        response_text = (response.text or "").strip()
        if not response_text:
            raise BadRequestError(
                user_message="El proveedor devolvió una respuesta vacía.",
                detail=f"{request.model}: Gemini devolvió una respuesta vacía.",
            )

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", response_text)
            if not match:
                raise BadRequestError(
                    user_message="La respuesta del proveedor no es JSON válido.",
                    detail=(
                        f"{request.model}: la respuesta no es JSON válido. "
                        f"Respuesta: {response_text[:1200]}"
                    ),
                )
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                raise BadRequestError(
                    user_message="La respuesta del proveedor no es JSON válido.",
                    detail=f"{request.model}: bloque ```json``` tampoco es JSON válido: {exc}",
                ) from exc

        return GenerationResult(data=data, model=request.model, raw_text=response_text)

    def _classify(self, exc: Exception) -> ProviderError:
        """Maps a raw SDK/network exception to a typed `ProviderError`.

        Same substrings, same check order as the pre-Fase-4 sniffing that
        used to live in `generation.py` -- only relocated, not changed.
        Anything that matches none of them falls back to `BadRequestError`,
        which preserves the old catch-all behavior: no retry, try the next
        candidate model.
        """
        detail = extract_error_detail(exc)
        error_text = detail.lower()

        is_quota = (
            "429" in detail
            or "quota" in error_text
            or "rate limit" in error_text
            or "resource exhausted" in error_text
        )
        if is_quota:
            return QuotaError(user_message="Cuota del proveedor agotada.", detail=detail)

        is_retryable_internal = (
            "500" in detail
            or "internal" in error_text
            or "503" in detail
            or "unavailable" in error_text
            or "deadline" in error_text
            or "timeout" in error_text
        )
        if is_retryable_internal:
            return TransientError(user_message="Error transitorio del proveedor.", detail=detail)

        is_bad_request = (
            "400" in detail
            or "invalid argument" in error_text
            or "invalid_argument" in error_text
            or "unsupported" in error_text
        )
        if is_bad_request:
            return BadRequestError(user_message="Solicitud inválida al proveedor.", detail=detail)

        return BadRequestError(user_message="Error del proveedor.", detail=detail)

    def _to_provider_schema(self, schema: dict) -> dict:
        # Gemini accepts the canonical JSON Schema as-is; this is the
        # extension point future, stricter providers (e.g. OpenAI) would use.
        return schema
