import zipfile
from io import BytesIO

import pytest

from agente_qa import security
from agente_qa.errors import SourceError
from agente_qa.security import redact, sniff_kind, validate_upload

PDF_BYTES = b"%PDF-1.4\n%fake pdf body\n%%EOF"
TEXT_BYTES = "Historia de usuario en texto plano.".encode("utf-8")


def _docx_bytes():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<xml>contenido</xml>")
        zf.writestr("[Content_Types].xml", "<Types/>")
    return buf.getvalue()


def _zip_without_docx_marker():
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "not a docx")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# sniff_kind
# ---------------------------------------------------------------------------


def test_sniff_kind_pdf():
    assert sniff_kind(PDF_BYTES) == "pdf"


def test_sniff_kind_docx():
    assert sniff_kind(_docx_bytes()) == "docx"


def test_sniff_kind_text():
    assert sniff_kind(TEXT_BYTES) == "text"


def test_sniff_kind_zip_without_docx_marker_is_none():
    assert sniff_kind(_zip_without_docx_marker()) is None


def test_sniff_kind_bad_zip_is_none():
    assert sniff_kind(b"PK\x03\x04not a real zip") is None


def test_sniff_kind_binary_garbage_is_none():
    assert sniff_kind(b"\x00\x01\x02\xff\xfe\x00binary") is None


def test_sniff_kind_empty_is_none():
    assert sniff_kind(b"") is None


# ---------------------------------------------------------------------------
# validate_upload
# ---------------------------------------------------------------------------


def test_validate_upload_empty_raises():
    with pytest.raises(SourceError):
        validate_upload("sample.txt", b"")


def test_validate_upload_oversized_raises(monkeypatch):
    monkeypatch.setattr(security, "MAX_UPLOAD_BYTES", 10)
    with pytest.raises(SourceError):
        validate_upload("sample.txt", TEXT_BYTES)


def test_validate_upload_disallowed_extension_raises():
    with pytest.raises(SourceError):
        validate_upload("sample.exe", TEXT_BYTES)


def test_validate_upload_extension_content_mismatch_raises():
    # .txt extension but PDF magic bytes inside.
    with pytest.raises(SourceError):
        validate_upload("sample.txt", PDF_BYTES)


def test_validate_upload_accepts_matching_pdf():
    assert validate_upload("sample.pdf", PDF_BYTES) == "pdf"


def test_validate_upload_accepts_matching_text():
    assert validate_upload("sample.txt", TEXT_BYTES) == "txt"


def test_validate_upload_accepts_matching_docx():
    assert validate_upload("sample.docx", _docx_bytes()) == "docx"


# ---------------------------------------------------------------------------
# redact
# ---------------------------------------------------------------------------


def test_redact_masks_authorization_header():
    text = "Authorization: Bearer sk-abcdefghij1234567890"
    result = redact(text)
    assert "sk-abcdefghij1234567890" not in result
    assert "[REDACTED]" in result


def test_redact_masks_gemini_style_api_key():
    text = "Using key AIzaSyD-abcdefghijklmnopqrstuvwxyz012345 for the call."
    result = redact(text)
    assert "AIzaSyD-abcdefghijklmnopqrstuvwxyz012345" not in result
    assert "[REDACTED_TOKEN]" in result


def test_redact_masks_absolute_path():
    text = "Failed to read /home/maosuarez/secrets/config.toml"
    result = redact(text)
    assert "/home/maosuarez/secrets/config.toml" not in result
    assert "[REDACTED_PATH]" in result


def test_redact_empty_string_passthrough():
    assert redact("") == ""


def test_redact_plain_text_unaffected():
    text = "No se pudo generar los casos de prueba."
    assert redact(text) == text
