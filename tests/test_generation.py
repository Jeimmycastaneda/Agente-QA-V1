import pytest

from agente_qa import generation
from agente_qa.errors import BadRequestError, ProviderError, QuotaError, TransientError
from agente_qa.providers.base import GenerationResult

VALID_PAYLOAD = {
    "TEST_CASES": [{"ID": "CP-AC-X-00001", "Title": "t", "Steps": []}],
    "ALERTS": [],
    "COVERAGE": [],
}


class FakeProvider:
    """Minimal `LLMProvider` stand-in: `generate_fn(request)` decides what
    happens on each call (return a `GenerationResult` or raise a typed
    provider error), and every call's model name is recorded in `.calls`."""

    name = "fake"

    def __init__(self, generate_fn, default_models=None):
        self._generate_fn = generate_fn
        self._default_models = default_models or []
        self.calls = []

    def list_models(self):
        return self._default_models

    def default_models(self):
        return self._default_models

    def generate(self, request):
        self.calls.append(request.model)
        return self._generate_fn(request)


def test_fallback_order_tries_selected_model_then_fallbacks():
    def generate_fn(request):
        raise BadRequestError(user_message="bad", detail=f"{request.model}: 400 invalid argument")

    provider = FakeProvider(generate_fn)

    with pytest.raises(ProviderError):
        generation.generate_qa_data(
            "prompt",
            "source",
            provider,
            "primary",
            fallback_models=["fb1", "fb2"],
            max_retries=0,
            initial_wait=0,
            sleep=lambda seconds: None,
        )

    assert provider.calls == ["primary", "fb1", "fb2"]


def test_uses_provider_default_models_when_fallback_models_not_given():
    def generate_fn(request):
        raise BadRequestError(user_message="bad", detail="400 invalid argument")

    provider = FakeProvider(generate_fn, default_models=["fb1"])

    with pytest.raises(ProviderError):
        generation.generate_qa_data(
            "prompt", "source", provider, "primary", max_retries=0, sleep=lambda seconds: None
        )

    assert provider.calls == ["primary", "fb1"]


def test_bad_request_moves_to_next_model_without_retry():
    sleep_calls = []

    def generate_fn(request):
        raise BadRequestError(
            user_message="bad", detail="400 Invalid Argument: bad schema"
        )

    provider = FakeProvider(generate_fn)

    with pytest.raises(ProviderError):
        generation.generate_qa_data(
            "prompt",
            "source",
            provider,
            "primary",
            fallback_models=["fb1"],
            max_retries=2,
            initial_wait=5,
            sleep=lambda seconds: sleep_calls.append(seconds),
        )

    # Each model is tried exactly once -- a bad request never retries the same model.
    assert provider.calls == ["primary", "fb1"]
    assert sleep_calls == []


def test_quota_error_backs_off_and_retries_same_model():
    sleep_calls = []
    attempts = {"count": 0}

    def generate_fn(request):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise QuotaError(user_message="quota", detail="429 Resource exhausted: quota")
        return GenerationResult(data=VALID_PAYLOAD, model=request.model, raw_text="{}")

    provider = FakeProvider(generate_fn)

    result = generation.generate_qa_data(
        "prompt",
        "source",
        provider,
        "primary",
        fallback_models=[],
        max_retries=2,
        initial_wait=10,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    assert result == VALID_PAYLOAD
    assert attempts["count"] == 2  # first attempt failed, second succeeded
    assert sleep_calls == [10]  # backoff = initial_wait * (attempt(0) + 1)


def test_transient_error_backs_off_and_retries_same_model():
    sleep_calls = []
    attempts = {"count": 0}

    def generate_fn(request):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TransientError(user_message="transient", detail="503 Service Unavailable")
        return GenerationResult(data=VALID_PAYLOAD, model=request.model, raw_text="{}")

    provider = FakeProvider(generate_fn)

    result = generation.generate_qa_data(
        "prompt",
        "source",
        provider,
        "primary",
        fallback_models=[],
        max_retries=2,
        initial_wait=3,
        sleep=lambda seconds: sleep_calls.append(seconds),
    )

    assert result == VALID_PAYLOAD
    assert sleep_calls == [3]


def test_value_error_from_validation_moves_to_next_model_without_retry():
    sleep_calls = []

    def generate_fn(request):
        return GenerationResult(data={"not": "the expected shape"}, model=request.model, raw_text="{}")

    provider = FakeProvider(generate_fn)

    with pytest.raises(ProviderError):
        generation.generate_qa_data(
            "prompt",
            "source",
            provider,
            "primary",
            fallback_models=["fb1"],
            max_retries=2,
            sleep=lambda seconds: sleep_calls.append(seconds),
        )

    assert provider.calls == ["primary", "fb1"]
    assert sleep_calls == []


def test_terminal_failure_raises_provider_error_with_user_message():
    def generate_fn(request):
        raise TransientError(user_message="transient", detail="500 internal error, always fails")

    provider = FakeProvider(generate_fn)

    with pytest.raises(ProviderError) as exc_info:
        generation.generate_qa_data(
            "prompt",
            "source",
            provider,
            "primary",
            fallback_models=["fb1"],
            max_retries=1,
            initial_wait=0,
            sleep=lambda seconds: None,
        )

    assert exc_info.value.user_message
    assert exc_info.value.detail


def test_empty_source_raises_value_error_immediately():
    provider = FakeProvider(lambda request: None)

    with pytest.raises(ValueError):
        generation.generate_qa_data("prompt", "   ", provider, "primary")

    assert provider.calls == []


def test_validate_qa_structure_message_does_not_mention_a_specific_provider():
    with pytest.raises(ValueError, match="proveedor"):
        generation.validate_qa_structure([])
