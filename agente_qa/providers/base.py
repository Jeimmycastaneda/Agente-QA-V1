"""Common LLM provider interface (Fase 4).

`LLMProvider` is a `typing.Protocol`: any provider (Gemini today, others
later) implements `generate()` against the same plain, provider-agnostic
request/result shapes below. `generation.py` depends only on this contract,
never on a concrete provider module.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    source: str
    schema: dict
    model: str
    temperature: float = 0.0
    max_output_tokens: int = 32768


@dataclass(frozen=True)
class GenerationResult:
    data: dict
    model: str
    raw_text: str


class LLMProvider(Protocol):
    name: str

    def list_models(self) -> list[str]: ...

    def default_models(self) -> list[str]: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...
