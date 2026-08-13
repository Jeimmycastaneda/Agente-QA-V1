import pytest

from agente_qa.errors import ConfigError
from agente_qa.providers import build_provider, list_providers
from agente_qa.providers.gemini import GeminiProvider


def test_list_providers_includes_gemini():
    assert "gemini" in list_providers()


def test_build_provider_gemini_returns_gemini_provider_instance():
    provider = build_provider("gemini", "some-key")
    assert isinstance(provider, GeminiProvider)
    assert provider.name == "gemini"
    assert provider.api_key == "some-key"


def test_build_provider_unknown_name_raises_config_error():
    with pytest.raises(ConfigError):
        build_provider("does-not-exist", "key")
