"""Compatibility helpers for the gradual migration from app.py.

This module intentionally does not replace or modify the original application.
It provides a small, stable boundary while organized modules are integrated.
"""

from importlib import import_module
from typing import Any


_MISSING = object()


def optional_import(module_name: str, attribute: str, default: Any = _MISSING) -> Any:
    """Return an attribute from an organized module without forcing all modules to load."""
    try:
        module = import_module(module_name)
        return getattr(module, attribute)
    except (ImportError, AttributeError):
        if default is not _MISSING:
            return default
        raise


def get_extraction_function(name: str):
    """Resolve an extraction function from the organized extraction module."""
    return optional_import("agente_qa.extraction", name)


def get_validation_function(name: str):
    """Resolve a validation function from the organized validation module."""
    return optional_import("agente_qa.validation", name)


def get_export_function(kind: str, name: str):
    """Resolve an export function without changing the legacy app entry point."""
    module_name = f"agente_qa.export.{kind}"
    return optional_import(module_name, name)


def get_provider_function(provider: str, name: str):
    """Resolve a provider function from an organized provider module."""
    return optional_import(f"agente_qa.providers.{provider}", name)


def get_integration_function(integration: str, name: str):
    """Resolve an integration function from an organized integration module."""
    return optional_import(f"agente_qa.integrations.{integration}", name)


def get_ui_function(component: str, name: str):
    """Resolve a UI function from an organized UI module."""
    return optional_import(f"agente_qa.ui.{component}", name)
