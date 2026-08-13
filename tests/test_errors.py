import pytest

from agente_qa.errors import (
    AgenteQAError,
    BadRequestError,
    ConfigError,
    IntegrationError,
    ProviderError,
    QuotaError,
    SourceError,
    TransientError,
)


def test_agente_qa_error_stores_user_message_detail_and_code():
    exc = AgenteQAError("safe message", detail="technical detail", code="E001")
    assert exc.user_message == "safe message"
    assert exc.detail == "technical detail"
    assert exc.code == "E001"
    assert str(exc) == "safe message"


def test_agente_qa_error_defaults():
    exc = AgenteQAError("safe message")
    assert exc.detail == ""
    assert exc.code == ""


@pytest.mark.parametrize(
    "exc_cls",
    [SourceError, ConfigError, ProviderError, IntegrationError],
)
def test_direct_subclasses_are_agente_qa_errors(exc_cls):
    assert issubclass(exc_cls, AgenteQAError)


@pytest.mark.parametrize("exc_cls", [QuotaError, TransientError, BadRequestError])
def test_provider_error_subclasses(exc_cls):
    assert issubclass(exc_cls, ProviderError)
    assert issubclass(exc_cls, AgenteQAError)


def test_errors_are_raisable_and_catchable_by_base_class():
    with pytest.raises(AgenteQAError):
        raise QuotaError("cuota agotada", detail="429")
