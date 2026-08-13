from agente_qa.utils import (
    aggregate_case_alerts,
    build_case_title,
    find_coverage,
    normalize_case_id,
    normalize_coverage,
    normalize_validation_method,
    safe_steps,
    safe_text,
)


# ---------------------------------------------------------------------------
# safe_text
# ---------------------------------------------------------------------------


def test_safe_text_none_returns_default():
    assert safe_text(None) == ""
    assert safe_text(None, "fallback") == "fallback"


def test_safe_text_strips_strings():
    assert safe_text("  hola  ") == "hola"


def test_safe_text_dict_and_list_become_json():
    assert safe_text({"a": 1}) == '{"a": 1}'
    assert safe_text([1, 2]) == "[1, 2]"


def test_safe_text_number_becomes_string():
    assert safe_text(5) == "5"


# ---------------------------------------------------------------------------
# safe_steps
# ---------------------------------------------------------------------------


def test_safe_steps_returns_list_when_present():
    tc = {"Steps": [{"Step #": 1, "Action": "a", "Expected value": "b"}]}
    assert safe_steps(tc) == tc["Steps"]


def test_safe_steps_missing_key_returns_empty_list():
    assert safe_steps({}) == []


def test_safe_steps_non_list_returns_empty_list():
    assert safe_steps({"Steps": "not a list"}) == []


# ---------------------------------------------------------------------------
# normalize_coverage
# ---------------------------------------------------------------------------


def test_normalize_coverage_known_values_case_insensitive():
    assert normalize_coverage("completa") == "Completa"
    assert normalize_coverage("PARCIAL") == "Parcial"
    assert normalize_coverage("No Cubierta") == "No cubierta"
    assert normalize_coverage("fuera de alcance") == "Fuera de alcance"


def test_normalize_coverage_unknown_value_passthrough():
    assert normalize_coverage("Algo raro") == "Algo raro"


def test_normalize_coverage_none_defaults_to_pendiente():
    # safe_text's default only kicks in for None -- an empty string stays empty.
    assert normalize_coverage(None) == "Pendiente"
    assert normalize_coverage("") == ""


# ---------------------------------------------------------------------------
# normalize_validation_method
# ---------------------------------------------------------------------------


def test_normalize_validation_method_known_values():
    assert normalize_validation_method("ui") == "UI"
    assert normalize_validation_method("Interfaz de Usuario") == "UI"
    assert normalize_validation_method("bd") == "BD"
    assert normalize_validation_method("base de datos") == "BD"
    assert normalize_validation_method("API") == "API"
    assert normalize_validation_method("web services") == "API"
    assert normalize_validation_method("mixto") == "Mixta"


def test_normalize_validation_method_unknown_passthrough():
    assert normalize_validation_method("Manual") == "Manual"


def test_normalize_validation_method_empty_defaults_to_pendiente():
    assert normalize_validation_method(None) == "Pendiente"


# ---------------------------------------------------------------------------
# build_case_title
# ---------------------------------------------------------------------------


def test_build_case_title_uses_model_title_when_functional():
    tc = {"Title": "Login exitoso con credenciales validas"}
    assert build_case_title(tc, "CP-AC-LOGIN-00001") == "Login exitoso con credenciales validas"


def test_build_case_title_falls_back_when_title_equals_id():
    tc = {"Title": "CP-AC-LOGIN-00001", "Scenario": "Login exitoso"}
    assert build_case_title(tc, "CP-AC-LOGIN-00001") == "Login exitoso"


def test_build_case_title_falls_back_when_title_looks_like_an_id_pattern():
    # Even a different CP-*-##### id-shaped string is treated as non-functional.
    tc = {"Title": "CP-XYZ-00042", "Description": "Descripcion util"}
    assert build_case_title(tc, "CP-AC-LOGIN-00001") == "Descripcion util"


def test_build_case_title_falls_back_through_priority_chain():
    tc = {"Related Use Case": "Autenticacion de usuario"}
    assert build_case_title(tc, "CP-AC-LOGIN-00001") == "Autenticacion de usuario"


def test_build_case_title_final_fallback_is_generated():
    assert build_case_title({}, "CP-AC-LOGIN-00001") == "Caso de prueba CP-AC-LOGIN-00001"


# ---------------------------------------------------------------------------
# normalize_case_id
# ---------------------------------------------------------------------------


def test_normalize_case_id_preserves_valid_cp_ac_id():
    candidate = "CP-AC-LOGIN-00007"
    assert normalize_case_id(candidate, "Login", 7, prefix="CP-AC-") == candidate


def test_normalize_case_id_regenerates_when_malformed():
    assert normalize_case_id("not-an-id", "Login", 3, prefix="CP-AC-") == "CP-AC-LOGIN-00003"


def test_normalize_case_id_other_prefixes_are_preserved():
    # Fase 3 fix (roadmap): the regex used to hardcode "CP-AC-" regardless of
    # the `prefix` argument, so a model-provided id matching a *different*
    # preset's own prefix format (e.g. "CP-" for General QA, "CP-ACSF-" for
    # Siniestros Fasecolda) was always discarded and regenerated. The regex is
    # now parametrized on `prefix`, so a well-formed id for that preset's own
    # prefix is preserved instead of being needlessly regenerated.
    candidate = "CP-CUSTOM-00007"
    result = normalize_case_id(candidate, "Login", 7, prefix="CP-")
    assert result == candidate


def test_normalize_case_id_mismatched_prefix_is_still_regenerated():
    candidate = "CP-ACSF-CUSTOM-00007"
    result = normalize_case_id(candidate, "Login", 7, prefix="CP-AC-")
    assert result != candidate
    assert result == "CP-AC-LOGIN-00007"


def test_normalize_case_id_default_prefix_is_cp_ac():
    candidate = "CP-AC-GENERAL-00001"
    assert normalize_case_id(candidate, "General", 1) == candidate


# ---------------------------------------------------------------------------
# find_coverage
# ---------------------------------------------------------------------------


def test_find_coverage_matches_by_test_case_id():
    data = {
        "COVERAGE": [
            {"Test Case": "CP-AC-LOGIN-00001", "Coverage": "Completa"},
            {"Test Case": "CP-AC-LOGIN-00002", "Coverage": "Parcial"},
        ]
    }
    tc = {"ID": "CP-AC-LOGIN-00002"}
    assert find_coverage(data, tc) == {"Test Case": "CP-AC-LOGIN-00002", "Coverage": "Parcial"}


def test_find_coverage_no_match_returns_empty_dict():
    data = {"COVERAGE": [{"Test Case": "CP-AC-LOGIN-00001"}]}
    tc = {"ID": "CP-AC-LOGIN-99999"}
    assert find_coverage(data, tc) == {}


def test_find_coverage_missing_or_non_list_coverage():
    assert find_coverage({}, {"ID": "x"}) == {}
    assert find_coverage({"COVERAGE": "not a list"}, {"ID": "x"}) == {}


# ---------------------------------------------------------------------------
# aggregate_case_alerts
# ---------------------------------------------------------------------------


def test_aggregate_case_alerts_no_alerts_returns_sin_alertas():
    assert aggregate_case_alerts({}, {"Alerts": []}) == "Sin Alertas"
    assert aggregate_case_alerts({}, {}) == "Sin Alertas"


def test_aggregate_case_alerts_formats_reason_and_validation():
    tc = {
        "Alerts": [
            {
                "Alert": "Dato faltante",
                "Reason": "No se especifica en la fuente",
                "Validation Required": "Confirmar con negocio",
            }
        ]
    }
    result = aggregate_case_alerts({}, tc)
    assert result == "Dato faltante: No se especifica en la fuente | Validación: Confirmar con negocio"


def test_aggregate_case_alerts_multiple_alerts_joined_with_pipe():
    tc = {
        "Alerts": [
            {"Alert": "A1", "Reason": "", "Validation Required": ""},
            {"Alert": "A2", "Reason": "R2", "Validation Required": ""},
        ]
    }
    assert aggregate_case_alerts({}, tc) == "A1 | A2: R2"
