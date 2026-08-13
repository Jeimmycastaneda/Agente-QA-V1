import pytest

from agente_qa.errors import IntegrationError, TransientError
from agente_qa.integrations.azure_devops import AzureDevOpsClient, PushResult, _steps_to_xml
from agente_qa.settings import AzureDevOpsConfig

_CONFIG = AzureDevOpsConfig(
    enabled=True,
    organization_url="https://dev.azure.com/my-org",
    project="MyProject",
    area_path="MyProject\\QA",
    iteration_path="MyProject\\Sprint 1",
    api_version="7.1",
    pat_secret_name="AZURE_DEVOPS_PAT",
    test_plan_id=42,
    test_suite_id=7,
)

_PRESET = {
    "sheet_name": "Azure Import",
    "base_id": 10001,
    "base_testpoint": 1001,
    "configuration": "Default configuration",
    "tester": "",
    "title_prefix": "CP-AC-",
    "user_default": "Usuario registrado",
    "steps_with_users": True,
}


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data if json_data is not None else {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._json_data


class _FakeSession:
    """Stand-in for requests.Session: records calls, returns canned responses."""

    def __init__(self):
        self.auth = None
        self.calls = []
        self.get_response = _FakeResponse(200, {"id": 1, "name": "MyProject"})
        self.post_response = _FakeResponse(200, {"id": 100})
        self.patch_response = _FakeResponse(200, {"id": 100})

    def get(self, url, timeout=None):
        self.calls.append(("GET", url, None, None))
        return self.get_response

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        return self.post_response

    def patch(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("PATCH", url, json, headers))
        return self.patch_response


def _sample_case(**overrides):
    case = {
        "ID": "CP-AC-LOGIN-00001",
        "Title": "Inicio de sesion exitoso",
        "Module": "Login",
        "Scenario": "Login exitoso",
        "Description": "Validar login",
        "Steps": [
            {"Step #": 1, "Action": "Ingresar credenciales", "Expected value": "Acceso concedido"},
        ],
    }
    case.update(overrides)
    return case


# ---------------------------------------------------------------------------
# _steps_to_xml -- no network, pure string fixtures
# ---------------------------------------------------------------------------


def test_steps_to_xml_basic_structure():
    xml = _steps_to_xml(
        [{"Action": "Do thing", "Expected value": "Thing happens"}]
    )
    assert xml.startswith('<steps id="0" last="1">')
    assert xml.endswith("</steps>")
    assert '<step id="1" type="ActionStep">' in xml
    assert xml.count("<parameterizedString") == 2
    assert "<description/>" in xml


def test_steps_to_xml_escapes_html_special_characters():
    xml = _steps_to_xml(
        [{"Action": "Click <Login> & 'Submit'", "Expected value": 'Shows "OK"'}]
    )
    assert "<Login>" not in xml
    assert "&lt;Login&gt;" in xml
    assert "&amp;" in xml
    assert "&#x27;" in xml or "&#39;" in xml
    assert "&quot;" in xml


def test_steps_to_xml_multiple_steps_has_matching_last_attribute():
    xml = _steps_to_xml(
        [
            {"Action": "Step one", "Expected value": "Result one"},
            {"Action": "Step two", "Expected value": "Result two"},
            {"Action": "Step three", "Expected value": "Result three"},
        ]
    )
    assert xml.startswith('<steps id="0" last="3">')
    assert xml.count('type="ActionStep"') == 3


def test_steps_to_xml_empty_steps_produces_placeholder_step():
    xml = _steps_to_xml([])
    assert xml.startswith('<steps id="0" last="1">')
    assert "Informaci" in xml  # "Información insuficiente..." (accent-safe substring)


# ---------------------------------------------------------------------------
# check_connection
# ---------------------------------------------------------------------------


def test_check_connection_success_returns_json():
    session = _FakeSession()
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    result = client.check_connection()
    assert result == {"id": 1, "name": "MyProject"}
    assert session.calls[0][0] == "GET"
    assert "MyProject" in session.calls[0][1]
    assert "api-version=7.1" in session.calls[0][1]


def test_check_connection_failure_raises_integration_error_without_leaking_pat():
    session = _FakeSession()
    session.get_response = _FakeResponse(401, text="Unauthorized: pat=super-secret-value")
    client = AzureDevOpsClient(_CONFIG, "super-secret-value", session=session)
    with pytest.raises(IntegrationError) as excinfo:
        client.check_connection()
    assert "super-secret-value" not in excinfo.value.user_message


def test_client_sets_basic_auth_with_empty_username():
    session = _FakeSession()
    AzureDevOpsClient(_CONFIG, "my-pat-value", session=session)
    assert session.auth == ("", "my-pat-value")


# ---------------------------------------------------------------------------
# create_test_case / update_test_case -- assert the JSON-Patch body sent
# ---------------------------------------------------------------------------


def test_create_test_case_sends_json_patch_body_with_title_and_steps():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"id": 555})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    work_item_id = client.create_test_case(_sample_case(), _PRESET)

    assert work_item_id == 555
    method, url, body, headers = session.calls[-1]
    assert method == "POST"
    assert "$Test%20Case" in url
    assert headers["Content-Type"] == "application/json-patch+json"

    ops_by_path = {op["path"]: op for op in body}
    assert ops_by_path["/fields/System.Title"]["op"] == "add"
    assert ops_by_path["/fields/System.Title"]["value"]
    assert ops_by_path["/fields/Microsoft.VSTS.TCM.Steps"]["op"] == "add"
    assert "<steps" in ops_by_path["/fields/Microsoft.VSTS.TCM.Steps"]["value"]
    assert ops_by_path["/fields/System.AreaPath"]["value"] == "MyProject\\QA"
    assert ops_by_path["/fields/System.IterationPath"]["value"] == "MyProject\\Sprint 1"


def test_update_test_case_sends_replace_operations():
    session = _FakeSession()
    session.patch_response = _FakeResponse(200, {"id": 555})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    work_item_id = client.update_test_case(555, _sample_case())

    assert work_item_id == 555
    method, url, body, headers = session.calls[-1]
    assert method == "PATCH"
    assert url.endswith("/_apis/wit/workitems/555?api-version=7.1")
    assert headers["Content-Type"] == "application/json-patch+json"
    assert all(op["op"] == "replace" for op in body)
    paths = {op["path"] for op in body}
    assert "/fields/System.Title" in paths
    assert "/fields/Microsoft.VSTS.TCM.Steps" in paths


# ---------------------------------------------------------------------------
# find_test_case_by_title -- parses a fake WIQL response
# ---------------------------------------------------------------------------


def test_find_test_case_by_title_returns_first_match():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"workItems": [{"id": 321}, {"id": 322}]})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    found = client.find_test_case_by_title("Inicio de sesion exitoso")

    assert found == 321
    method, url, body, headers = session.calls[-1]
    assert method == "POST"
    assert "_apis/wit/wiql" in url
    assert "Test Case" in body["query"]
    assert "Inicio de sesion exitoso" in body["query"]


def test_find_test_case_by_title_returns_none_when_no_matches():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"workItems": []})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    assert client.find_test_case_by_title("Does not exist") is None


def test_find_test_case_by_title_escapes_single_quotes():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"workItems": []})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    client.find_test_case_by_title("Case with 'quotes'")
    _, _, body, _ = session.calls[-1]
    assert "''quotes''" in body["query"]


# ---------------------------------------------------------------------------
# push_test_cases -- dry_run makes zero network calls
# ---------------------------------------------------------------------------


def test_push_test_cases_dry_run_makes_no_network_calls():
    session = _FakeSession()
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    result_json = {"TEST_CASES": [_sample_case(), _sample_case(ID="CP-AC-LOGIN-00002")]}

    result = client.push_test_cases(result_json, _PRESET, dry_run=True)

    assert session.calls == []
    assert isinstance(result, PushResult)
    assert len(result.created) == 2
    assert result.updated == []
    assert result.failed == []


def test_push_test_cases_dry_run_classifies_existing_azure_id_as_update():
    session = _FakeSession()
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    result_json = {
        "TEST_CASES": [
            _sample_case(AzureWorkItemId=999),
            _sample_case(ID="CP-AC-LOGIN-00002"),
        ]
    }

    result = client.push_test_cases(result_json, _PRESET, dry_run=True)

    assert session.calls == []
    assert result.updated == [999]
    assert result.created == [0]


def test_push_test_cases_dry_run_reports_actions_via_on_progress():
    session = _FakeSession()
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)
    result_json = {"TEST_CASES": [_sample_case(AzureWorkItemId=999), _sample_case()]}

    rows = []
    client.push_test_cases(result_json, _PRESET, dry_run=True, on_progress=lambda *args: rows.append(args))

    assert len(rows) == 2
    assert rows[0][3] == "update"
    assert rows[1][3] == "create"


# ---------------------------------------------------------------------------
# push_test_cases -- real push (dry_run=False)
# ---------------------------------------------------------------------------


def test_push_test_cases_real_push_creates_when_not_found():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"workItems": []})  # first call: WIQL, no match
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    # Second POST call (create) must return a different fixed body; swap responses per-call.
    responses = iter(
        [
            _FakeResponse(200, {"workItems": []}),  # WIQL
            _FakeResponse(200, {"id": 777}),  # create
        ]
    )

    def post(url, json=None, headers=None, timeout=None):
        session.calls.append(("POST", url, json, headers))
        return next(responses)

    session.post = post

    result_json = {"TEST_CASES": [_sample_case()]}
    result = client.push_test_cases(result_json, _PRESET, dry_run=False)

    assert result.created == [777]
    assert result.updated == []
    assert result_json["TEST_CASES"][0]["AzureWorkItemId"] == 777


def test_push_test_cases_real_push_updates_when_azure_work_item_id_present():
    session = _FakeSession()
    session.patch_response = _FakeResponse(200, {"id": 42})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    result_json = {"TEST_CASES": [_sample_case(AzureWorkItemId=42)]}
    result = client.push_test_cases(result_json, _PRESET, dry_run=False)

    assert result.updated == [42]
    assert result.created == []
    # No WIQL lookup needed: AzureWorkItemId was already present.
    assert all(call[0] != "POST" for call in session.calls)


def test_push_test_cases_real_push_updates_when_wiql_finds_match():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"workItems": [{"id": 501}]})
    session.patch_response = _FakeResponse(200, {"id": 501})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    result_json = {"TEST_CASES": [_sample_case()]}
    result = client.push_test_cases(result_json, _PRESET, dry_run=False)

    assert result.updated == [501]
    assert result.created == []


def test_push_test_cases_skip_title_match_always_creates():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {"id": 900})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    result_json = {"TEST_CASES": [_sample_case()]}
    result = client.push_test_cases(result_json, _PRESET, dry_run=False, skip_title_match=True)

    assert result.created == [900]
    # Only one POST call: the create. No WIQL lookup was made.
    assert len([c for c in session.calls if c[0] == "POST"]) == 1


def test_push_test_cases_collects_failures_without_raising():
    session = _FakeSession()
    session.post_response = _FakeResponse(500, text="Internal Server Error")
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    result_json = {"TEST_CASES": [_sample_case()]}
    result = client.push_test_cases(result_json, _PRESET, dry_run=False)

    assert result.created == []
    assert result.updated == []
    assert len(result.failed) == 1
    title, reason = result.failed[0]
    assert title
    assert reason


# ---------------------------------------------------------------------------
# 429 rate limiting -> TransientError, Retry-After respected
# ---------------------------------------------------------------------------


def test_429_response_raises_transient_error_with_retry_after():
    session = _FakeSession()
    session.get_response = _FakeResponse(429, text="Too Many Requests", headers={"Retry-After": "5"})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    with pytest.raises(TransientError) as excinfo:
        client.check_connection()
    assert "5" in excinfo.value.detail


# ---------------------------------------------------------------------------
# add_to_test_suite (Fase 5b)
# ---------------------------------------------------------------------------


def test_add_to_test_suite_posts_to_testplan_endpoint():
    session = _FakeSession()
    session.post_response = _FakeResponse(200, {})
    client = AzureDevOpsClient(_CONFIG, "fake-pat", session=session)

    client.add_to_test_suite(555)

    method, url, body, headers = session.calls[-1]
    assert method == "POST"
    assert "/testplan/Plans/42/Suites/7/TestCase" in url
    assert body == [{"workItem": {"id": 555}}]


def test_add_to_test_suite_raises_when_plan_or_suite_not_configured():
    config = AzureDevOpsConfig(
        enabled=True,
        organization_url="https://dev.azure.com/my-org",
        project="MyProject",
        area_path="",
        iteration_path="",
        api_version="7.1",
        pat_secret_name="AZURE_DEVOPS_PAT",
        test_plan_id=None,
        test_suite_id=None,
    )
    session = _FakeSession()
    client = AzureDevOpsClient(config, "fake-pat", session=session)

    with pytest.raises(IntegrationError):
        client.add_to_test_suite(555)
    assert session.calls == []
