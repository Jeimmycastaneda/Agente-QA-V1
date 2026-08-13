import re
from datetime import datetime, timedelta, timezone

from agente_qa.config import PROJECT_ROOT

# ============================================================
# PROMPTS QA — ARCHIVOS .md EDITABLES EN prompts/
# ============================================================

PROMPTS_DIR = PROJECT_ROOT / "prompts"
DEFAULT_PROMPT_NAME = "qa_base.md"

# Historial de versiones (snapshots tomados por save_prompt antes de
# sobrescribir). Documentado como constante de nivel de módulo por
# claridad, pero todas las funciones de abajo recalculan la ruta a
# partir del valor *actual* de PROMPTS_DIR (ver _history_dir) en vez de
# leer esta constante directamente — así siguen respetando el
# monkeypatch de PROMPTS_DIR que usan los tests (tests/test_prompts.py).
HISTORY_DIR = PROMPTS_DIR / ".history"
MAX_VERSIONS = 20

_VALID_NAME = re.compile(r"^[A-Za-z0-9_\-]+\.md$")
_VALID_VERSION = re.compile(r"^\d{8}T\d{6}$")

_CACHE: dict[str, str] = {}

_FALLBACK_PROMPT = (
    "Eres un agente QA especializado en análisis de documentación. "
    "Analiza exclusivamente la fuente proporcionada, no inventes información "
    "y genera TEST_CASES, ALERTS y COVERAGE en JSON."
)


def _history_dir():
    return PROMPTS_DIR / ".history"


def is_valid_prompt_name(name):
    return bool(_VALID_NAME.fullmatch(name or ""))


def _require_valid_name(name):
    if not is_valid_prompt_name(name):
        raise ValueError(
            "Nombre de prompt inválido: solo letras, números, '_'/'-' y "
            "extensión .md."
        )


def _require_valid_version(version):
    if not _VALID_VERSION.fullmatch(version or ""):
        raise ValueError(
            "Versión de prompt inválida: se esperaba el formato "
            "YYYYMMDDTHHMMSS."
        )


def list_prompts():
    if not PROMPTS_DIR.exists():
        return []
    return sorted(p.name for p in PROMPTS_DIR.glob("*.md"))


def prompt_path(name):
    _require_valid_name(name)
    return PROMPTS_DIR / name


def load_prompt(name=DEFAULT_PROMPT_NAME):
    if name in _CACHE:
        return _CACHE[name]

    path = prompt_path(name)
    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            _CACHE[name] = content
            return content

    return _FALLBACK_PROMPT


def clear_prompt_cache():
    _CACHE.clear()


def _next_version_id(name):
    """Genera un id de versión único (YYYYMMDDTHHMMSS) para `name`,
    avanzando de a un segundo si ya existe un snapshot con ese id
    (posible con guardados rápidos consecutivos, p. ej. en tests)."""
    stem = name[:-3]
    history_dir = _history_dir()
    ts = datetime.now(timezone.utc)
    while True:
        version = ts.strftime("%Y%m%dT%H%M%S")
        if not (history_dir / f"{stem}.{version}.md").exists():
            return version
        ts += timedelta(seconds=1)


def save_prompt(name, content):
    path = prompt_path(name)
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    if path.exists():
        history_dir = _history_dir()
        history_dir.mkdir(parents=True, exist_ok=True)
        version = _next_version_id(name)
        snapshot_path = history_dir / f"{name[:-3]}.{version}.md"
        snapshot_path.write_text(
            path.read_text(encoding="utf-8"), encoding="utf-8"
        )
        _prune_history(name)

    path.write_text(content, encoding="utf-8")
    clear_prompt_cache()


def list_prompt_versions(name):
    """Devuelve los ids de versión existentes para `name`, más nuevo
    primero. Lanza ValueError si `name` no es un nombre de prompt válido."""
    _require_valid_name(name)

    history_dir = _history_dir()
    if not history_dir.exists():
        return []

    stem = name[:-3]
    prefix = f"{stem}."
    versions = []
    for p in history_dir.glob(f"{stem}.*.md"):
        candidate = p.name[len(prefix):-3]
        if _VALID_VERSION.fullmatch(candidate):
            versions.append(candidate)

    versions.sort(reverse=True)
    return versions


def read_prompt_version(name, version):
    """Lee el contenido de una versión histórica de `name`.

    `name` y `version` se validan por separado, cada uno contra su propio
    regex (_VALID_NAME / _VALID_VERSION), ANTES de construir cualquier
    ruta de filesystem. Nunca se concatena el `version` crudo del usuario
    en un path sin haber pasado esa validación — es lo que impide un path
    traversal vía el parámetro de versión (ver tests/test_prompt_history.py).
    """
    _require_valid_name(name)
    _require_valid_version(version)

    path = _history_dir() / f"{name[:-3]}.{version}.md"
    if not path.exists():
        raise ValueError(f"Versión no encontrada: {version}")
    return path.read_text(encoding="utf-8")


def restore_prompt_version(name, version):
    """Restaura `version` como el contenido activo de `name`.

    Reusa save_prompt, que automáticamente snapshotea la versión activa
    que se está reemplazando antes de sobrescribirla — el historial no
    se pierde al restaurar.
    """
    content = read_prompt_version(name, version)
    save_prompt(name, content)


def _prune_history(name):
    """Conserva solo las MAX_VERSIONS versiones más nuevas de `name` en
    el historial; borra el resto."""
    versions = list_prompt_versions(name)
    if len(versions) <= MAX_VERSIONS:
        return

    history_dir = _history_dir()
    stem = name[:-3]
    for version in versions[MAX_VERSIONS:]:
        (history_dir / f"{stem}.{version}.md").unlink(missing_ok=True)
