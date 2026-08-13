from pathlib import Path

from agente_qa import config


def test_project_root_is_repo_root():
    assert isinstance(config.PROJECT_ROOT, Path)
    assert (config.PROJECT_ROOT / "agente_qa").is_dir()
    assert (config.PROJECT_ROOT / "prompts").is_dir()


def test_fallback_models_is_nonempty_list_of_strings():
    assert isinstance(config.FALLBACK_MODELS, list)
    assert config.FALLBACK_MODELS
    assert all(isinstance(m, str) and m for m in config.FALLBACK_MODELS)


def test_excel_configs_keys_match_azure_columns_users():
    expected_presets = {"Autos Colectivos", "Siniestros Fasecolda", "General QA"}
    assert set(config.EXCEL_CONFIGS.keys()) == expected_presets


def test_excel_configs_have_required_fields():
    required_fields = {
        "sheet_name", "base_id", "base_testpoint", "configuration",
        "tester", "title_prefix", "user_default", "steps_with_users",
    }
    for preset_name, preset in config.EXCEL_CONFIGS.items():
        assert required_fields.issubset(preset.keys()), preset_name


def test_schema_declares_top_level_contract_keys():
    assert config.SCHEMA["type"] == "object"
    assert set(config.SCHEMA["required"]) == {"TEST_CASES", "ALERTS", "COVERAGE"}
    assert "TEST_CASES" in config.SCHEMA["properties"]
    assert "ALERTS" in config.SCHEMA["properties"]
    assert "COVERAGE" in config.SCHEMA["properties"]


def test_debug_flag_reflects_env_var_at_import_time(monkeypatch):
    import importlib

    monkeypatch.delenv("AGENTE_QA_DEBUG", raising=False)
    reloaded = importlib.reload(config)
    assert reloaded.DEBUG is False

    monkeypatch.setenv("AGENTE_QA_DEBUG", "1")
    reloaded = importlib.reload(config)
    assert reloaded.DEBUG is True

    # Restore module state for any tests that run after this one.
    monkeypatch.delenv("AGENTE_QA_DEBUG", raising=False)
    importlib.reload(config)
