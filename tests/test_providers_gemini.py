import pytest

from agente_qa.config import FALLBACK_MODELS
from agente_qa.errors import BadRequestError, QuotaError, TransientError
from agente_qa.providers import gemini
from agente_qa.providers.base import GenerationRequest


class _FakeModel:
    def __init__(self, name):
        self.name = name


class _FakeModelsAPI:
    def __init__(self, names):
        self._names = names

    def list(self):
        return [_FakeModel(n) for n in self._names]


class _FakeClient:
    def __init__(self, names):
        self.models = _FakeModelsAPI(names)


def test_get_valid_models_returns_fallback_when_genai_missing(monkeypatch):
    monkeypatch.setattr(gemini, "genai", None)
    assert gemini.get_valid_models("any-key") == FALLBACK_MODELS


def test_get_valid_models_returns_fallback_on_exception(monkeypatch):
    class BoomGenai:
        @staticmethod
        def Client(api_key):
            raise RuntimeError("network down")

    monkeypatch.setattr(gemini, "genai", BoomGenai)
    assert gemini.get_valid_models("any-key") == FALLBACK_MODELS


def test_get_valid_models_filters_and_sorts_gemini_models(monkeypatch):
    names = ["models/gemini-2.5-pro", "models/gemini-2.5-flash", "models/text-bison"]

    class FakeGenai:
        @staticmethod
        def Client(api_key):
            return _FakeClient(names)

    monkeypatch.setattr(gemini, "genai", FakeGenai)
    result = gemini.get_valid_models("any-key")
    assert result == ["gemini-2.5-flash", "gemini-2.5-pro"]


def test_extract_error_detail_truncates_long_messages():
    detail = gemini.extract_error_detail(RuntimeError("x" * 5000))
    assert len(detail) == 1800


def test_extract_error_detail_short_message_passthrough():
    assert gemini.extract_error_detail(RuntimeError("boom")) == "boom"


def test_build_client_delegates_to_genai_client(monkeypatch):
    calls = {}

    class FakeGenai:
        @staticmethod
        def Client(api_key):
            calls["api_key"] = api_key
            return "the-client"

    monkeypatch.setattr(gemini, "genai", FakeGenai)
    client = gemini.build_client("secret-key")
    assert client == "the-client"
    assert calls["api_key"] == "secret-key"


def test_generate_once_forwards_model_prompt_and_schema_config():
    captured = {}

    class FakeModelsAPI:
        def generate_content(self, model, contents, config):
            captured["model"] = model
            captured["contents"] = contents
            captured["config"] = config
            return "response-object"

    class FakeClient:
        models = FakeModelsAPI()

    result = gemini.generate_once(FakeClient(), "gemini-x", "full prompt text")

    assert result == "response-object"
    assert captured["model"] == "gemini-x"
    assert captured["contents"] == "full prompt text"
    assert captured["config"].response_mime_type == "application/json"
    assert captured["config"].max_output_tokens == 32768


# ---------------------------------------------------------------------------
# GeminiProvider._classify -- same substrings, same check order as the
# pre-Fase-4 sniffing that used to live directly in generation.py.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "message,expected_type",
    [
        ("429 Too Many Requests", QuotaError),
        ("Quota exceeded for this project", QuotaError),
        ("rate limit exceeded, slow down", QuotaError),
        ("Resource Exhausted: try again later", QuotaError),
        ("500 Internal Server Error", TransientError),
        ("503 Service Unavailable", TransientError),
        ("Deadline Exceeded talking to upstream", TransientError),
        ("Connection timeout after 30s", TransientError),
        ("400 Bad Request", BadRequestError),
        ("Invalid Argument: bad schema", BadRequestError),
        ("INVALID_ARGUMENT: bad schema", BadRequestError),
        ("unsupported operation for this model", BadRequestError),
        ("something totally unexpected happened", BadRequestError),  # unmatched -> no retry, next model
    ],
)
def test_classify_maps_substrings_to_typed_errors_same_as_before(message, expected_type):
    provider = gemini.GeminiProvider(api_key="k")
    classified = provider._classify(RuntimeError(message))
    assert isinstance(classified, expected_type)
    assert classified.detail == message


def test_classify_checks_quota_before_transient_and_bad_request():
    # "429" would also make this look bad-request-ish if order were wrong;
    # quota must win because it's checked first.
    provider = gemini.GeminiProvider(api_key="k")
    classified = provider._classify(RuntimeError("429: quota resource exhausted"))
    assert isinstance(classified, QuotaError)


# ---------------------------------------------------------------------------
# GeminiProvider.generate
# ---------------------------------------------------------------------------


def test_generate_provider_raises_typed_error_when_api_key_missing():
    from agente_qa.errors import ProviderError

    provider = gemini.GeminiProvider(api_key="")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    with pytest.raises(ProviderError):
        provider.generate(request)


def test_generate_classifies_sdk_exceptions_via_classify(monkeypatch):
    def boom(api_key):
        raise RuntimeError("503 Service Unavailable")

    monkeypatch.setattr(gemini, "build_client", boom)

    provider = gemini.GeminiProvider(api_key="k")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    with pytest.raises(TransientError):
        provider.generate(request)


def test_generate_returns_generation_result_on_valid_json(monkeypatch):
    class FakeResponse:
        text = '{"TEST_CASES": [], "ALERTS": [], "COVERAGE": []}'

    monkeypatch.setattr(gemini, "build_client", lambda api_key: "fake-client")
    monkeypatch.setattr(
        gemini, "generate_once", lambda client, model, prompt, **kwargs: FakeResponse()
    )

    provider = gemini.GeminiProvider(api_key="k")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    result = provider.generate(request)

    assert result.data == {"TEST_CASES": [], "ALERTS": [], "COVERAGE": []}
    assert result.model == "gemini-x"


def test_generate_extracts_json_from_fenced_code_block(monkeypatch):
    class FakeResponse:
        text = '```json\n{"TEST_CASES": [], "ALERTS": [], "COVERAGE": []}\n```'

    monkeypatch.setattr(gemini, "build_client", lambda api_key: "fake-client")
    monkeypatch.setattr(
        gemini, "generate_once", lambda client, model, prompt, **kwargs: FakeResponse()
    )

    provider = gemini.GeminiProvider(api_key="k")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    result = provider.generate(request)

    assert result.data == {"TEST_CASES": [], "ALERTS": [], "COVERAGE": []}


def test_generate_raises_bad_request_error_on_unparseable_response(monkeypatch):
    class FakeResponse:
        text = "not json at all"

    monkeypatch.setattr(gemini, "build_client", lambda api_key: "fake-client")
    monkeypatch.setattr(
        gemini, "generate_once", lambda client, model, prompt, **kwargs: FakeResponse()
    )

    provider = gemini.GeminiProvider(api_key="k")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    with pytest.raises(BadRequestError):
        provider.generate(request)


def test_generate_raises_bad_request_error_on_empty_response(monkeypatch):
    class FakeResponse:
        text = "   "

    monkeypatch.setattr(gemini, "build_client", lambda api_key: "fake-client")
    monkeypatch.setattr(
        gemini, "generate_once", lambda client, model, prompt, **kwargs: FakeResponse()
    )

    provider = gemini.GeminiProvider(api_key="k")
    request = GenerationRequest(prompt="p", source="s", schema={}, model="gemini-x")

    with pytest.raises(BadRequestError):
        provider.generate(request)
