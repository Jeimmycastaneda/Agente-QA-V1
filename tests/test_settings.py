import copy

import pytest
import yaml

from agente_qa import defaults
from agente_qa.errors import ConfigError
from agente_qa.settings import (
    load_azure_devops_config,
    load_columns,
    load_default_provider,
    load_excel_presets,
    load_providers,
)

_VALID_PRESET = {
    "sheet_name": "Azure Import",
    "base_id": 10001,
    "base_testpoint": 1001,
    "configuration": "Default configuration",
    "tester": "",
    "title_prefix": "CP-AC-",
    "user_default": "Usuario registrado",
    "steps_with_users": True,
}


def _write_presets_yaml(path, preset, key="Autos Colectivos"):
    path.write_text(
        yaml.safe_dump({"version": 1, "presets": {key: preset}}, allow_unicode=True),
        encoding="utf-8",
    )


_VALID_PROVIDER = {
    "enabled": True,
    "secret_name": "GEMINI_API_KEY",
    "default_model": "gemini-3.6-flash",
    "max_source_chars": 28000,
    "fallback_models": [
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
}


def _write_providers_yaml(path, provider, key="gemini", default_provider="gemini"):
    path.write_text(
        yaml.safe_dump(
            {"version": 1, "default_provider": default_provider, "providers": {key: provider}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def _write_columns_yaml(path, azure_columns, matriz_columns, allow_override=False):
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "allow_override": allow_override,
                "azure_columns": azure_columns,
                "matriz_columns": matriz_columns,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Loaders reproduce the literals in defaults.py exactly
# ---------------------------------------------------------------------------


def test_load_excel_presets_matches_defaults():
    loaded = {k: p.as_dict() for k, p in load_excel_presets().items()}
    assert loaded == defaults.EXCEL_CONFIGS


def test_load_columns_matches_defaults():
    spec = load_columns()
    assert list(spec.azure) == defaults.AZURE_COLUMNS
    assert list(spec.matriz) == defaults.MATRIZ_COLUMNS


# ---------------------------------------------------------------------------
# Fallback to defaults.py when the YAML file is missing
# ---------------------------------------------------------------------------


def test_load_columns_falls_back_to_defaults_when_file_missing(tmp_path):
    spec = load_columns(path=tmp_path / "does_not_exist.yaml")
    assert list(spec.azure) == defaults.AZURE_COLUMNS
    assert list(spec.matriz) == defaults.MATRIZ_COLUMNS


def test_load_excel_presets_falls_back_to_defaults_when_file_missing(tmp_path):
    loaded = {
        k: p.as_dict()
        for k, p in load_excel_presets(path=tmp_path / "does_not_exist.yaml").items()
    }
    assert loaded == defaults.EXCEL_CONFIGS


# ---------------------------------------------------------------------------
# columns.yaml validation
# ---------------------------------------------------------------------------


def test_load_columns_hard_fails_when_azure_columns_modified_without_override(tmp_path):
    path = tmp_path / "columns.yaml"
    _write_columns_yaml(path, ["TestCaseId", "Title"], ["TestCaseId", "Title"], allow_override=False)
    with pytest.raises(ConfigError):
        load_columns(path=path)


def test_load_columns_allows_override_when_flag_true(tmp_path):
    path = tmp_path / "columns.yaml"
    _write_columns_yaml(path, ["TestCaseId", "Title"], ["TestCaseId", "Title"], allow_override=True)
    spec = load_columns(path=path)
    assert list(spec.azure) == ["TestCaseId", "Title"]


def test_load_columns_valid_file_roundtrips(tmp_path):
    path = tmp_path / "columns.yaml"
    _write_columns_yaml(path, defaults.AZURE_COLUMNS, defaults.MATRIZ_COLUMNS, allow_override=False)
    spec = load_columns(path=path)
    assert list(spec.azure) == defaults.AZURE_COLUMNS
    assert list(spec.matriz) == defaults.MATRIZ_COLUMNS


# ---------------------------------------------------------------------------
# excel_presets.yaml validation
# ---------------------------------------------------------------------------


def test_load_excel_presets_valid_file_roundtrips(tmp_path):
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, _VALID_PRESET)
    presets = load_excel_presets(path=path)
    assert presets["Autos Colectivos"].as_dict() == defaults.EXCEL_CONFIGS["Autos Colectivos"]


def test_load_excel_presets_missing_key_raises_config_error(tmp_path):
    preset = copy.deepcopy(_VALID_PRESET)
    del preset["tester"]
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


def test_load_excel_presets_unknown_key_raises_config_error(tmp_path):
    preset = copy.deepcopy(_VALID_PRESET)
    preset["extra_field"] = 1
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


def test_load_excel_presets_wrong_type_raises_config_error(tmp_path):
    preset = copy.deepcopy(_VALID_PRESET)
    preset["base_id"] = "10001"
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


def test_load_excel_presets_bool_rejected_for_int_field(tmp_path):
    preset = copy.deepcopy(_VALID_PRESET)
    preset["base_id"] = True
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


@pytest.mark.parametrize(
    "bad_sheet_name",
    ["", "a" * 32, "bad[name]", "bad:name", "bad*name", "bad?name", "bad/name", "bad\\name"],
)
def test_load_excel_presets_invalid_sheet_name_raises(tmp_path, bad_sheet_name):
    preset = copy.deepcopy(_VALID_PRESET)
    preset["sheet_name"] = bad_sheet_name
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


@pytest.mark.parametrize("field", ["base_id", "base_testpoint"])
@pytest.mark.parametrize("bad_value", [0, -1])
def test_load_excel_presets_non_positive_ids_raise(tmp_path, field, bad_value):
    preset = copy.deepcopy(_VALID_PRESET)
    preset[field] = bad_value
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


def test_load_excel_presets_invalid_title_prefix_raises(tmp_path):
    preset = copy.deepcopy(_VALID_PRESET)
    preset["title_prefix"] = "CP AC!"
    path = tmp_path / "excel_presets.yaml"
    _write_presets_yaml(path, preset)
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


def test_load_excel_presets_missing_presets_key_raises(tmp_path):
    path = tmp_path / "excel_presets.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_excel_presets(path=path)


# ---------------------------------------------------------------------------
# providers.yaml: fallback + drift guard against defaults.py
# ---------------------------------------------------------------------------


def test_load_providers_matches_defaults():
    loaded = {k: p.as_dict() for k, p in load_providers().items()}
    assert loaded == defaults.PROVIDERS


def test_load_default_provider_matches_defaults():
    assert load_default_provider() == defaults.DEFAULT_PROVIDER


def test_load_providers_falls_back_to_defaults_when_file_missing(tmp_path):
    loaded = {
        k: p.as_dict() for k, p in load_providers(path=tmp_path / "does_not_exist.yaml").items()
    }
    assert loaded == defaults.PROVIDERS


def test_load_default_provider_falls_back_to_defaults_when_file_missing(tmp_path):
    assert (
        load_default_provider(path=tmp_path / "does_not_exist.yaml") == defaults.DEFAULT_PROVIDER
    )


def test_load_providers_valid_file_roundtrips(tmp_path):
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, _VALID_PROVIDER)
    providers = load_providers(path=path)
    assert providers["gemini"].as_dict() == defaults.PROVIDERS["gemini"]


def test_load_default_provider_valid_file_roundtrips(tmp_path):
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, _VALID_PROVIDER)
    assert load_default_provider(path=path) == "gemini"


def test_load_providers_missing_key_raises_config_error(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    del provider["secret_name"]
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_unknown_key_raises_config_error(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    provider["extra_field"] = 1
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_wrong_type_raises_config_error(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    provider["max_source_chars"] = "28000"
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_bool_rejected_for_int_field(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    provider["max_source_chars"] = True
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_non_positive_max_source_chars_raises(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    provider["max_source_chars"] = 0
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_empty_fallback_models_raises(tmp_path):
    provider = copy.deepcopy(_VALID_PROVIDER)
    provider["fallback_models"] = []
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, provider)
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_providers_missing_providers_key_raises(tmp_path):
    path = tmp_path / "providers.yaml"
    path.write_text("version: 1\ndefault_provider: gemini\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_providers(path=path)


def test_load_default_provider_not_in_providers_raises(tmp_path):
    path = tmp_path / "providers.yaml"
    _write_providers_yaml(path, _VALID_PROVIDER, key="gemini", default_provider="openai")
    with pytest.raises(ConfigError):
        load_default_provider(path=path)


# ---------------------------------------------------------------------------
# azure_devops.yaml: anti-secret guard + organization_url validation (Fase 5)
# ---------------------------------------------------------------------------

_VALID_AZURE_DEVOPS = {
    "version": 1,
    "enabled": True,
    "organization_url": "https://dev.azure.com/my-org",
    "project": "MyProject",
    "area_path": "MyProject\\QA",
    "iteration_path": "MyProject\\Sprint 1",
    "api_version": "7.1",
    "pat_secret_name": "AZURE_DEVOPS_PAT",
    "test_plan_id": 42,
    "test_suite_id": 7,
}


def _write_azure_devops_yaml(path, raw):
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")


def test_load_azure_devops_config_falls_back_to_disabled_default_when_file_missing(tmp_path):
    cfg = load_azure_devops_config(path=tmp_path / "does_not_exist.yaml")
    assert cfg.enabled is False
    assert cfg.pat_secret_name == "AZURE_DEVOPS_PAT"


def test_load_azure_devops_config_valid_file_roundtrips(tmp_path):
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, _VALID_AZURE_DEVOPS)
    cfg = load_azure_devops_config(path=path)
    assert cfg.enabled is True
    assert cfg.organization_url == "https://dev.azure.com/my-org"
    assert cfg.project == "MyProject"
    assert cfg.pat_secret_name == "AZURE_DEVOPS_PAT"
    assert cfg.test_plan_id == 42
    assert cfg.test_suite_id == 7


@pytest.mark.parametrize("forbidden_key", ["pat", "token", "password", "PAT", "Token"])
def test_load_azure_devops_config_rejects_secret_key_in_yaml(tmp_path, forbidden_key):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw[forbidden_key] = "should-never-be-here"
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    with pytest.raises(ConfigError):
        load_azure_devops_config(path=path)


def test_load_azure_devops_config_rejects_nested_secret_key_in_yaml(tmp_path):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["extra"] = {"nested": {"token": "leaked"}}
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    with pytest.raises(ConfigError):
        load_azure_devops_config(path=path)


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://dev.azure.com/my-org",  # not https
        "https://evil.com/dev.azure.com/my-org",  # host mismatch, path trick
        "https://dev.azure.com.evil.com/my-org",  # lookalike host
        "ftp://dev.azure.com/my-org",
        "",
    ],
)
def test_load_azure_devops_config_rejects_invalid_organization_url(tmp_path, bad_url):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["organization_url"] = bad_url
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    with pytest.raises(ConfigError):
        load_azure_devops_config(path=path)


def test_load_azure_devops_config_accepts_visualstudio_com_host(tmp_path):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["organization_url"] = "https://my-org.visualstudio.com"
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    cfg = load_azure_devops_config(path=path)
    assert cfg.organization_url == "https://my-org.visualstudio.com"


def test_load_azure_devops_config_null_test_ids_allowed(tmp_path):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["test_plan_id"] = None
    raw["test_suite_id"] = None
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    cfg = load_azure_devops_config(path=path)
    assert cfg.test_plan_id is None
    assert cfg.test_suite_id is None


def test_load_azure_devops_config_bool_rejected_for_test_plan_id(tmp_path):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["test_plan_id"] = True
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    with pytest.raises(ConfigError):
        load_azure_devops_config(path=path)


def test_load_azure_devops_config_non_bool_enabled_raises(tmp_path):
    raw = copy.deepcopy(_VALID_AZURE_DEVOPS)
    raw["enabled"] = "true"
    path = tmp_path / "azure_devops.yaml"
    _write_azure_devops_yaml(path, raw)
    with pytest.raises(ConfigError):
        load_azure_devops_config(path=path)
