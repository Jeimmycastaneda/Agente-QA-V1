"""Validación de uploads y redacción de información sensible en logs/UI."""

import re
import zipfile
from io import BytesIO

from agente_qa.errors import SourceError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = ("txt", "md", "pdf", "docx")

# Extensión -> tipo de contenido esperado según sniff_kind().
_EXPECTED_KIND = {
    "txt": "text",
    "md": "text",
    "pdf": "pdf",
    "docx": "docx",
}

_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"

_TEXT_ENCODINGS = ("utf-8", "cp1252")


def sniff_kind(data: bytes) -> str | None:
    """Detecta el tipo real de contenido a partir de los bytes, no del nombre."""
    if not data:
        return None

    if data.startswith(_PDF_MAGIC):
        return "pdf"

    if data.startswith(_ZIP_MAGIC):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return "docx"
        except zipfile.BadZipFile:
            return None
        return None

    if b"\x00" in data:
        return None

    for encoding in _TEXT_ENCODINGS:
        try:
            data.decode(encoding)
            return "text"
        except UnicodeDecodeError:
            continue

    return None


def validate_upload(name: str, data: bytes) -> str:
    """Valida un upload y devuelve la extensión normalizada (sin punto).

    Lanza SourceError si el archivo está vacío, excede MAX_UPLOAD_BYTES,
    tiene una extensión no permitida, o el contenido no coincide con la
    extensión declarada.
    """
    if not data:
        raise SourceError(
            "El archivo está vacío.",
            detail=f"empty upload: name={name!r}",
        )

    if len(data) > MAX_UPLOAD_BYTES:
        raise SourceError(
            f"El archivo supera el tamaño máximo permitido "
            f"({MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            detail=f"upload too large: name={name!r} size={len(data)}",
        )

    extension = (name or "").rsplit(".", 1)[-1].lower() if "." in (name or "") else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise SourceError(
            f"Formato no soportado: .{extension or '(sin extensión)'}. "
            f"Formatos permitidos: {', '.join(ALLOWED_EXTENSIONS)}.",
            detail=f"disallowed extension: name={name!r}",
        )

    kind = sniff_kind(data)
    expected = _EXPECTED_KIND[extension]
    if kind != expected:
        raise SourceError(
            "El contenido del archivo no coincide con su extensión "
            f".{extension}. Verifica que el archivo no esté corrupto o "
            "renombrado incorrectamente.",
            detail=f"content/extension mismatch: name={name!r} sniffed={kind!r} expected={expected!r}",
        )

    return extension


# ---------------------------------------------------------------------------
# Redacción de información sensible
# ---------------------------------------------------------------------------

_AUTH_HEADER_RE = re.compile(
    r"(?i)(authorization\s*:\s*)(bearer|basic)\s+\S+"
)
_API_KEY_RE = re.compile(
    r"\b(AIza[0-9A-Za-z_-]{35}|sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{16,}"
    r"|[A-Za-z0-9_-]{32,})\b"
)
_ABS_PATH_RE = re.compile(
    r"(?:/(?:home|Users|root|etc|var|tmp)/[^\s'\"]+)"
    r"|(?:[A-Za-z]:\\[^\s'\"]+)"
)


def redact(text: str) -> str:
    """Enmascara tokens tipo API-key/PAT, paths absolutos y headers Authorization."""
    if not text:
        return text

    redacted = _AUTH_HEADER_RE.sub(r"\1\2 [REDACTED]", text)
    redacted = _ABS_PATH_RE.sub("[REDACTED_PATH]", redacted)
    redacted = _API_KEY_RE.sub("[REDACTED_TOKEN]", redacted)
    return redacted
