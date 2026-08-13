"""Carga y valida la configuración externalizada bajo `config/*.yaml`.

Dos archivos, dos responsabilidades:
- `config/columns.yaml`: el contrato de columnas aprobado con Azure DevOps
  (`AZURE_COLUMNS`/`MATRIZ_COLUMNS`). Congelado por defecto (`allow_override: false`).
- `config/excel_presets.yaml`: los presets de export por cliente/proyecto
  (`EXCEL_CONFIGS`), libremente editable.

Si un archivo YAML falta, se cae a los literales de `agente_qa/defaults.py`
(el comportamiento anterior a la Fase 3), así que un `config/` ausente sigue
siendo un estado funcional. Ver `docs/plans/roadmap-implementation-plan.md`
Fase 3 para el detalle de decisión.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from agente_qa import defaults
from agente_qa.errors import ConfigError

# No importar `agente_qa.config` acá: `config.py` importa este módulo para
# derivar AZURE_COLUMNS/MATRIZ_COLUMNS/EXCEL_CONFIGS, así que depender de
# `config.PROJECT_ROOT` crearía un import circular. Se recalcula localmente
# (mismo valor: la raíz del repo, dos niveles arriba de este archivo).
PROJECT_ROOT = Path(__file__).resolve().parent.parent

COLUMNS_PATH = PROJECT_ROOT / "config" / "columns.yaml"
EXCEL_PRESETS_PATH = PROJECT_ROOT / "config" / "excel_presets.yaml"
PROVIDERS_PATH = PROJECT_ROOT / "config" / "providers.yaml"
AZURE_DEVOPS_PATH = PROJECT_ROOT / "config" / "azure_devops.yaml"

_SHEET_NAME_FORBIDDEN_CHARS = set("[]:*?/\\")
_TITLE_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]*$")

# El PAT se manda como header Authorization a esta URL: un host mal
# validado (typo o inyectado) filtraría el PAT a un host arbitrario. Este
# es el chequeo de mayor severidad de la Fase 5 — ver
# docs/plans/roadmap-implementation-plan.md Fase 5.
_AZURE_ORG_URL_RE = re.compile(r"^https://(dev\.azure\.com/|[a-z0-9-]+\.visualstudio\.com)")

# El valor del PAT nunca debe vivir en el YAML de config -- solo el
# *nombre* del secreto (`pat_secret_name`). Cualquiera de estas claves,
# a cualquier profundidad del árbol parseado, es un error de configuración
# grave y hace fallar la carga (hard fail), no un warning.
_AZURE_SECRET_KEY_GUARD = {"pat", "token", "password"}

_PRESET_FIELDS = {
    "sheet_name": str,
    "base_id": int,
    "base_testpoint": int,
    "configuration": str,
    "tester": str,
    "title_prefix": str,
    "user_default": str,
    "steps_with_users": bool,
}

_PROVIDER_FIELDS = {
    "enabled": bool,
    "secret_name": str,
    "default_model": str,
    "max_source_chars": int,
    "fallback_models": list,
}


@dataclass(frozen=True)
class ExcelPreset:
    key: str
    sheet_name: str
    base_id: int
    base_testpoint: int
    configuration: str
    tester: str
    title_prefix: str
    user_default: str
    steps_with_users: bool

    def as_dict(self) -> dict:
        return {
            "sheet_name": self.sheet_name,
            "base_id": self.base_id,
            "base_testpoint": self.base_testpoint,
            "configuration": self.configuration,
            "tester": self.tester,
            "title_prefix": self.title_prefix,
            "user_default": self.user_default,
            "steps_with_users": self.steps_with_users,
        }


@dataclass(frozen=True)
class ColumnSpec:
    azure: tuple
    matriz: tuple


@dataclass(frozen=True)
class AzureDevOpsConfig:
    enabled: bool
    organization_url: str
    project: str
    area_path: str
    iteration_path: str
    api_version: str
    pat_secret_name: str
    test_plan_id: int | None = None
    test_suite_id: int | None = None


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    enabled: bool
    secret_name: str
    default_model: str
    max_source_chars: int
    fallback_models: tuple

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "secret_name": self.secret_name,
            "default_model": self.default_model,
            "max_source_chars": self.max_source_chars,
            "fallback_models": list(self.fallback_models),
        }


def _validate_preset(raw, key) -> ExcelPreset:
    """Valida un preset crudo (dict del YAML) y lo convierte a `ExcelPreset`.

    Lanza `ConfigError` ante: claves faltantes, claves desconocidas, tipos
    incorrectos, `sheet_name` inválido, `base_id`/`base_testpoint` no
    positivos, o `title_prefix` con caracteres no permitidos.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' no es un mapeo: {raw!r}",
        )

    expected_keys = set(_PRESET_FIELDS)
    raw_keys = set(raw.keys())

    missing = expected_keys - raw_keys
    if missing:
        raise ConfigError(
            f"Configuración incompleta para el preset '{key}'.",
            detail=f"preset '{key}' falta claves: {sorted(missing)}",
        )

    unknown = raw_keys - expected_keys
    if unknown:
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' tiene claves desconocidas: {sorted(unknown)}",
        )

    for field, expected_type in _PRESET_FIELDS.items():
        value = raw[field]
        # bool es subclase de int en Python: chequear explícitamente para no
        # aceptar True/False donde se espera un int, ni un int donde se espera bool.
        if expected_type is int and (isinstance(value, bool) or not isinstance(value, int)):
            raise ConfigError(
                f"Configuración inválida para el preset '{key}'.",
                detail=f"preset '{key}' campo '{field}' debe ser int, recibido {type(value).__name__}",
            )
        if expected_type is bool and not isinstance(value, bool):
            raise ConfigError(
                f"Configuración inválida para el preset '{key}'.",
                detail=f"preset '{key}' campo '{field}' debe ser bool, recibido {type(value).__name__}",
            )
        if expected_type is str and not isinstance(value, str):
            raise ConfigError(
                f"Configuración inválida para el preset '{key}'.",
                detail=f"preset '{key}' campo '{field}' debe ser str, recibido {type(value).__name__}",
            )

    sheet_name = raw["sheet_name"]
    if not sheet_name:
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' sheet_name vacío",
        )
    if len(sheet_name) > 31:
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' sheet_name '{sheet_name}' supera 31 caracteres",
        )
    if _SHEET_NAME_FORBIDDEN_CHARS.intersection(sheet_name):
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' sheet_name '{sheet_name}' contiene caracteres no permitidos",
        )

    for field in ("base_id", "base_testpoint"):
        value = raw[field]
        if value <= 0:
            raise ConfigError(
                f"Configuración inválida para el preset '{key}'.",
                detail=f"preset '{key}' campo '{field}' debe ser un entero positivo, recibido {value}",
            )

    title_prefix = raw["title_prefix"]
    if not _TITLE_PREFIX_RE.fullmatch(title_prefix):
        raise ConfigError(
            f"Configuración inválida para el preset '{key}'.",
            detail=f"preset '{key}' title_prefix '{title_prefix}' no matchea ^[A-Za-z0-9_-]*$",
        )

    return ExcelPreset(
        key=key,
        sheet_name=sheet_name,
        base_id=raw["base_id"],
        base_testpoint=raw["base_testpoint"],
        configuration=raw["configuration"],
        tester=raw["tester"],
        title_prefix=title_prefix,
        user_default=raw["user_default"],
        steps_with_users=raw["steps_with_users"],
    )


def load_columns(path=None) -> ColumnSpec:
    """Carga `columns.yaml`. Cae a `defaults.py` si el archivo no existe.

    Si `allow_override` es false (el default) y `azure_columns` difiere del
    contrato congelado en `defaults.AZURE_COLUMNS`, lanza `ConfigError`
    (hard-fail): ese contrato no es negociable salvo override explícito.
    """
    target = path or COLUMNS_PATH
    if not target.exists():
        return ColumnSpec(azure=tuple(defaults.AZURE_COLUMNS), matriz=tuple(defaults.MATRIZ_COLUMNS))

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            "No se pudo leer la configuración de columnas.",
            detail=f"error de parseo YAML en {target}: {exc}",
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            "Configuración de columnas inválida.",
            detail=f"{target} no contiene un mapeo YAML válido",
        )

    azure_columns = raw.get("azure_columns")
    matriz_columns = raw.get("matriz_columns")
    allow_override = raw.get("allow_override", False)

    if not isinstance(azure_columns, list) or not all(isinstance(c, str) for c in azure_columns):
        raise ConfigError(
            "Configuración de columnas inválida.",
            detail=f"{target} azure_columns debe ser una lista de strings",
        )
    if not isinstance(matriz_columns, list) or not all(isinstance(c, str) for c in matriz_columns):
        raise ConfigError(
            "Configuración de columnas inválida.",
            detail=f"{target} matriz_columns debe ser una lista de strings",
        )

    if not allow_override and azure_columns != defaults.AZURE_COLUMNS:
        raise ConfigError(
            "El contrato de columnas de Azure DevOps fue modificado sin autorización.",
            detail=(
                f"{target} azure_columns={azure_columns!r} difiere de "
                f"defaults.AZURE_COLUMNS={defaults.AZURE_COLUMNS!r} y allow_override es false"
            ),
        )

    return ColumnSpec(azure=tuple(azure_columns), matriz=tuple(matriz_columns))


def load_excel_presets(path=None) -> dict:
    """Carga `excel_presets.yaml`. Cae a `defaults.py` si el archivo no existe."""
    target = path or EXCEL_PRESETS_PATH
    if not target.exists():
        return {
            key: _validate_preset(raw, key)
            for key, raw in defaults.EXCEL_CONFIGS.items()
        }

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            "No se pudo leer la configuración de presets de Excel.",
            detail=f"error de parseo YAML en {target}: {exc}",
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            "Configuración de presets de Excel inválida.",
            detail=f"{target} no contiene un mapeo YAML válido",
        )

    presets = raw.get("presets")
    if not isinstance(presets, dict):
        raise ConfigError(
            "Configuración de presets de Excel inválida.",
            detail=f"{target} falta la clave 'presets' o no es un mapeo",
        )

    return {key: _validate_preset(value, key) for key, value in presets.items()}


def _validate_provider(raw, key) -> ProviderConfig:
    """Valida un proveedor crudo (dict del YAML) y lo convierte a `ProviderConfig`.

    Mismo patrón que `_validate_preset`: claves faltantes/desconocidas y tipos
    incorrectos lanzan `ConfigError` en vez de defaultear en silencio.
    """
    if not isinstance(raw, dict):
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=f"proveedor '{key}' no es un mapeo: {raw!r}",
        )

    expected_keys = set(_PROVIDER_FIELDS)
    raw_keys = set(raw.keys())

    missing = expected_keys - raw_keys
    if missing:
        raise ConfigError(
            f"Configuración incompleta para el proveedor '{key}'.",
            detail=f"proveedor '{key}' falta claves: {sorted(missing)}",
        )

    unknown = raw_keys - expected_keys
    if unknown:
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=f"proveedor '{key}' tiene claves desconocidas: {sorted(unknown)}",
        )

    for field, expected_type in _PROVIDER_FIELDS.items():
        value = raw[field]
        # bool es subclase de int en Python: chequear explícitamente para no
        # aceptar True/False donde se espera un int.
        if expected_type is int and (isinstance(value, bool) or not isinstance(value, int)):
            raise ConfigError(
                f"Configuración inválida para el proveedor '{key}'.",
                detail=f"proveedor '{key}' campo '{field}' debe ser int, recibido {type(value).__name__}",
            )
        if expected_type is bool and not isinstance(value, bool):
            raise ConfigError(
                f"Configuración inválida para el proveedor '{key}'.",
                detail=f"proveedor '{key}' campo '{field}' debe ser bool, recibido {type(value).__name__}",
            )
        if expected_type is str and not isinstance(value, str):
            raise ConfigError(
                f"Configuración inválida para el proveedor '{key}'.",
                detail=f"proveedor '{key}' campo '{field}' debe ser str, recibido {type(value).__name__}",
            )
        if expected_type is list and not isinstance(value, list):
            raise ConfigError(
                f"Configuración inválida para el proveedor '{key}'.",
                detail=f"proveedor '{key}' campo '{field}' debe ser una lista, recibido {type(value).__name__}",
            )

    secret_name = raw["secret_name"]
    if not secret_name:
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=f"proveedor '{key}' secret_name vacío",
        )

    default_model = raw["default_model"]
    if not default_model:
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=f"proveedor '{key}' default_model vacío",
        )

    max_source_chars = raw["max_source_chars"]
    if max_source_chars <= 0:
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=(
                f"proveedor '{key}' max_source_chars debe ser un entero "
                f"positivo, recibido {max_source_chars}"
            ),
        )

    fallback_models = raw["fallback_models"]
    if not fallback_models or not all(isinstance(m, str) and m for m in fallback_models):
        raise ConfigError(
            f"Configuración inválida para el proveedor '{key}'.",
            detail=(
                f"proveedor '{key}' fallback_models debe ser una lista no vacía "
                "de strings no vacíos"
            ),
        )

    return ProviderConfig(
        name=key,
        enabled=raw["enabled"],
        secret_name=secret_name,
        default_model=default_model,
        max_source_chars=max_source_chars,
        fallback_models=tuple(fallback_models),
    )


def load_providers(path=None) -> dict:
    """Carga `providers.yaml`. Cae a `defaults.py` si el archivo no existe."""
    target = path or PROVIDERS_PATH
    if not target.exists():
        return {key: _validate_provider(raw, key) for key, raw in defaults.PROVIDERS.items()}

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            "No se pudo leer la configuración de proveedores de LLM.",
            detail=f"error de parseo YAML en {target}: {exc}",
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            "Configuración de proveedores de LLM inválida.",
            detail=f"{target} no contiene un mapeo YAML válido",
        )

    providers = raw.get("providers")
    if not isinstance(providers, dict):
        raise ConfigError(
            "Configuración de proveedores de LLM inválida.",
            detail=f"{target} falta la clave 'providers' o no es un mapeo",
        )

    return {key: _validate_provider(value, key) for key, value in providers.items()}


def load_default_provider(path=None) -> str:
    """Carga el `default_provider` declarado en `providers.yaml`.

    Cae a `defaults.DEFAULT_PROVIDER` si el archivo no existe. Valida que el
    proveedor default declarado exista dentro de `providers`, para no dejar
    que `config.py` arranque apuntando a una clave inexistente.
    """
    target = path or PROVIDERS_PATH
    if not target.exists():
        return defaults.DEFAULT_PROVIDER

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            "No se pudo leer la configuración de proveedores de LLM.",
            detail=f"error de parseo YAML en {target}: {exc}",
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            "Configuración de proveedores de LLM inválida.",
            detail=f"{target} no contiene un mapeo YAML válido",
        )

    default_provider = raw.get("default_provider")
    if not isinstance(default_provider, str) or not default_provider:
        raise ConfigError(
            "Configuración de proveedores de LLM inválida.",
            detail=f"{target} default_provider debe ser un string no vacío",
        )

    providers = raw.get("providers")
    if not isinstance(providers, dict) or default_provider not in providers:
        raise ConfigError(
            "El proveedor default declarado no existe en la configuración.",
            detail=(
                f"{target} default_provider='{default_provider}' no está en "
                f"providers={sorted(providers) if isinstance(providers, dict) else providers!r}"
            ),
        )

    return default_provider


def _find_forbidden_secret_key(node) -> str | None:
    """Escanea recursivamente un valor YAML parseado por claves prohibidas.

    Devuelve la primera clave `pat`/`token`/`password` (case-insensitive)
    encontrada a cualquier profundidad, o None. Usado por
    `load_azure_devops_config` como guardia anti-secreto-en-config: el PAT
    nunca debe vivir en el YAML, solo su nombre de secreto.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key.strip().lower() in _AZURE_SECRET_KEY_GUARD:
                return key
            found = _find_forbidden_secret_key(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_forbidden_secret_key(item)
            if found:
                return found
    return None


def load_azure_devops_config(path=None) -> AzureDevOpsConfig:
    """Carga `config/azure_devops.yaml`. Cae a un default deshabilitado si falta.

    Dos hard-fails, en este orden:
    1. Guardia anti-secreto: el mapeo parseado no puede contener una clave
       literal `pat`, `token` o `password` a ninguna profundidad -- el PAT
       nunca va en YAML, solo su nombre de secreto (`pat_secret_name`).
    2. `organization_url` debe matchear `_AZURE_ORG_URL_RE`. El PAT se envía
       como header Authorization a esa URL: un host mal validado lo filtraría
       a un destino arbitrario. Este es el chequeo de mayor severidad de la
       Fase 5 (ver docs/plans/roadmap-implementation-plan.md).
    """
    target = path or AZURE_DEVOPS_PATH
    if not target.exists():
        return AzureDevOpsConfig(
            enabled=False,
            organization_url="https://dev.azure.com/<org>",
            project="",
            area_path="",
            iteration_path="",
            api_version="7.1",
            pat_secret_name="AZURE_DEVOPS_PAT",
            test_plan_id=None,
            test_suite_id=None,
        )

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            "No se pudo leer la configuración de Azure DevOps.",
            detail=f"error de parseo YAML en {target}: {exc}",
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            "Configuración de Azure DevOps inválida.",
            detail=f"{target} no contiene un mapeo YAML válido",
        )

    offending_key = _find_forbidden_secret_key(raw)
    if offending_key:
        raise ConfigError(
            "El archivo de configuración de Azure DevOps no debe contener secretos.",
            detail=(
                f"{target} contiene la clave prohibida '{offending_key}'. El valor del "
                "PAT nunca va en YAML -- solo su nombre de secreto en pat_secret_name, "
                "resuelto en runtime vía agente_qa.secrets.resolve_secret."
            ),
        )

    organization_url = raw.get("organization_url", "")
    if not isinstance(organization_url, str) or not _AZURE_ORG_URL_RE.match(organization_url):
        raise ConfigError(
            "organization_url de Azure DevOps inválida.",
            detail=(
                f"{target} organization_url={organization_url!r} no matchea "
                f"{_AZURE_ORG_URL_RE.pattern!r}. El PAT se envía como header Authorization "
                "a esta URL, así que un host no validado podría filtrarlo a un destino "
                "arbitrario."
            ),
        )

    for field_name in ("project", "area_path", "iteration_path", "api_version", "pat_secret_name"):
        value = raw.get(field_name, "")
        if not isinstance(value, str):
            raise ConfigError(
                "Configuración de Azure DevOps inválida.",
                detail=(
                    f"{target} campo '{field_name}' debe ser str, "
                    f"recibido {type(value).__name__}"
                ),
            )

    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError(
            "Configuración de Azure DevOps inválida.",
            detail=f"{target} campo 'enabled' debe ser bool, recibido {type(enabled).__name__}",
        )

    for field_name in ("test_plan_id", "test_suite_id"):
        value = raw.get(field_name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise ConfigError(
                "Configuración de Azure DevOps inválida.",
                detail=(
                    f"{target} campo '{field_name}' debe ser int o null, "
                    f"recibido {type(value).__name__}"
                ),
            )

    return AzureDevOpsConfig(
        enabled=enabled,
        organization_url=organization_url,
        project=raw.get("project", ""),
        area_path=raw.get("area_path", ""),
        iteration_path=raw.get("iteration_path", ""),
        api_version=raw.get("api_version") or "7.1",
        pat_secret_name=raw.get("pat_secret_name") or "AZURE_DEVOPS_PAT",
        test_plan_id=raw.get("test_plan_id"),
        test_suite_id=raw.get("test_suite_id"),
    )
