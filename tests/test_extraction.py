from pathlib import Path

import pytest

from agente_qa.errors import SourceError
from agente_qa.extraction import extract_source, extract_source_bytes
from tests.conftest import FakeUpload

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_extract_source_bytes_txt():
    content = extract_source_bytes("sample.txt", _read("sample.txt"))
    assert "Historia de Usuario" in content


def test_extract_source_bytes_pdf():
    content = extract_source_bytes("sample.pdf", _read("sample.pdf"))
    assert "Historia de Usuario" in content


def test_extract_source_bytes_docx():
    content = extract_source_bytes("sample.docx", _read("sample.docx"))
    assert "Historia de Usuario" in content
    # Tables are flattened into pipe-joined rows.
    assert "Criterio | Bloquear cuenta tras 5 intentos fallidos" in content


def test_extract_source_bytes_not_a_pdf_raises_source_error():
    with pytest.raises(SourceError):
        extract_source_bytes("not_a_pdf.pdf", _read("not_a_pdf.pdf"))


def test_extract_source_bytes_empty_raises_source_error():
    with pytest.raises(SourceError):
        extract_source_bytes("empty.txt", b"")


def test_extract_source_wraps_fake_upload():
    upload = FakeUpload("sample.txt", _read("sample.txt"))
    content = extract_source(upload)
    assert "Historia de Usuario" in content
