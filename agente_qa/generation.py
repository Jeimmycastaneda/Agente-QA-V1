import time

from agente_qa.config import SCHEMA
from agente_qa.errors import ProviderError, QuotaError, TransientError
from agente_qa.providers.base import GenerationRequest


def validate_qa_structure(data):
    if not isinstance(data, dict):
        raise ValueError("La respuesta del proveedor no es un objeto JSON.")

    for key in ("TEST_CASES", "ALERTS", "COVERAGE"):
        if key not in data:
            raise ValueError(f"Falta la clave requerida: {key}")

    if not isinstance(data["TEST_CASES"], list) or not data["TEST_CASES"]:
        raise ValueError("No se generaron casos de prueba.")

    if not isinstance(data["ALERTS"], list):
        data["ALERTS"] = []

    if not isinstance(data["COVERAGE"], list):
        data["COVERAGE"] = []

    return data


def generate_qa_data(
    prompt_text,
    source_content,
    provider,
    model_name,
    *,
    fallback_models=None,
    temperature=0.0,
    max_retries=2,
    initial_wait=10,
    max_source_chars=28000,
    sleep=time.sleep,
):
    if not source_content.strip():
        raise ValueError("Fuente de información vacía.")

    if len(source_content) > max_source_chars:
        source_content = source_content[:max_source_chars] + (
            "\n...[CONTENIDO TRUNCADO POR LÍMITE DE SEGURIDAD]"
        )

    fallback = provider.default_models() if fallback_models is None else fallback_models

    # Prefer selected model, then use stable/available fallbacks.
    candidates = []
    for candidate in [model_name] + list(fallback):
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    errors = []

    for candidate in candidates:
        for attempt in range(max_retries + 1):
            request = GenerationRequest(
                prompt=prompt_text,
                source=source_content,
                schema=SCHEMA,
                model=candidate,
                temperature=temperature,
            )
            try:
                result = provider.generate(request)
                validated = validate_qa_structure(result.data)
                return validated

            except (QuotaError, TransientError) as exc:
                errors.append(f"{candidate} / intento {attempt + 1}: {exc.detail or exc.user_message}")

                if attempt < max_retries:
                    sleep(initial_wait * (attempt + 1))
                    continue

                break

            except ProviderError as exc:
                # BadRequestError (or any other provider error not covered
                # above): never retried against the same model, move
                # straight to the next candidate.
                errors.append(f"{candidate} / intento {attempt + 1}: {exc.detail or exc.user_message}")
                break

            except ValueError as exc:
                # Validation/JSON errors are meaningful and should be shown,
                # but we still allow another model to try.
                errors.append(f"{candidate} / intento {attempt + 1}: {exc}")
                break

    raise ProviderError(
        user_message="No se pudo generar los casos de prueba.",
        detail="\n\n".join(errors[-8:]),
    )
