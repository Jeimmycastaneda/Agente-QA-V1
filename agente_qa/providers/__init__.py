"""Lazy provider registry (Fase 4).

`_REGISTRY` maps a provider name to a dotted `module:ClassName` string.
`build_provider` only imports that module when the provider is actually
requested, so a future provider with a missing dependency (e.g. `openai`
not installed) never breaks app startup for everyone else.
"""

import importlib

from agente_qa.errors import ConfigError
from agente_qa.providers.base import LLMProvider

_REGISTRY = {
    "gemini": "agente_qa.providers.gemini:GeminiProvider",
}


def list_providers() -> list:
    return sorted(_REGISTRY)


def build_provider(name: str, api_key: str) -> LLMProvider:
    dotted = _REGISTRY.get(name)
    if dotted is None:
        raise ConfigError(
            f"Proveedor de LLM desconocido: '{name}'.",
            detail=f"'{name}' no está en el registro de proveedores: {sorted(_REGISTRY)}",
        )

    module_path, _, class_name = dotted.partition(":")
    try:
        module = importlib.import_module(module_path)
        provider_cls = getattr(module, class_name)
    except ImportError as exc:
        raise ConfigError(
            f"No se pudo cargar el proveedor '{name}'.",
            detail=f"import de '{dotted}' falló: {exc}",
        ) from exc

    return provider_cls(api_key)
