import sys
import types

from agente_qa.secrets import resolve_secret


def _install_fake_streamlit(monkeypatch, secrets_value):
    """Install a fake `streamlit` module in sys.modules exposing `.secrets.get`."""
    fake_secrets = types.SimpleNamespace(get=lambda name: secrets_value.get(name))
    fake_module = types.SimpleNamespace(secrets=fake_secrets)
    monkeypatch.setitem(sys.modules, "streamlit", fake_module)


def test_resolve_secret_prefers_streamlit_secrets(monkeypatch):
    _install_fake_streamlit(monkeypatch, {"GEMINI_API_KEY": "from-streamlit"})
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert resolve_secret("GEMINI_API_KEY") == "from-streamlit"


def test_resolve_secret_falls_back_to_env_when_not_in_streamlit(monkeypatch):
    _install_fake_streamlit(monkeypatch, {})
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert resolve_secret("GEMINI_API_KEY") == "from-env"


def test_resolve_secret_falls_back_to_default(monkeypatch):
    _install_fake_streamlit(monkeypatch, {})
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert resolve_secret("GEMINI_API_KEY", "default-value") == "default-value"
    assert resolve_secret("GEMINI_API_KEY") == ""


def test_resolve_secret_tolerates_missing_streamlit_module(monkeypatch):
    # sys.modules[name] = None makes `import streamlit` raise ImportError,
    # simulating an environment without Streamlit installed.
    monkeypatch.setitem(sys.modules, "streamlit", None)
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert resolve_secret("GEMINI_API_KEY") == "from-env"


def test_resolve_secret_tolerates_streamlit_secrets_raising(monkeypatch):
    class ExplodingSecrets:
        def get(self, name):
            raise RuntimeError("no secrets.toml found")

    fake_module = types.SimpleNamespace(secrets=ExplodingSecrets())
    monkeypatch.setitem(sys.modules, "streamlit", fake_module)
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert resolve_secret("GEMINI_API_KEY") == "from-env"
