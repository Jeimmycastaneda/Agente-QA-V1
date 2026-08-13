"""Jerarquía de excepciones propias de Agente QA.

`user_message` es siempre seguro de mostrar en la UI. `detail` es texto
técnico (trazas, payloads de error del proveedor, etc.) que solo debe
loguearse o mostrarse detrás de un flag de debug, nunca interpolado
directamente en un `st.error`.
"""


class AgenteQAError(Exception):
    """Excepción base de la aplicación."""

    def __init__(self, user_message: str, *, detail: str = "", code: str = ""):
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail
        self.code = code


class SourceError(AgenteQAError):
    """Error al validar o extraer el documento fuente (upload/extraction)."""


class ConfigError(AgenteQAError):
    """Error al cargar o validar configuración (fase 3)."""


class ProviderError(AgenteQAError):
    """Error base de un proveedor de LLM (fase 4)."""


class QuotaError(ProviderError):
    """Cuota del proveedor agotada (429 / resource exhausted)."""


class TransientError(ProviderError):
    """Error transitorio del proveedor: 5xx, timeout, o 429 con retry-after."""


class BadRequestError(ProviderError):
    """Solicitud inválida al proveedor (400): no se reintenta, se prueba otro modelo."""


class IntegrationError(AgenteQAError):
    """Error de una integración externa, p. ej. Azure DevOps (fase 5)."""
