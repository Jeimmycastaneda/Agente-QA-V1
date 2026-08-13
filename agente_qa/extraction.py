import io

from agente_qa.errors import SourceError
from agente_qa.security import sniff_kind, validate_upload

# ============================================================
# EXTRACCIÓN ROBUSTA DE DOCUMENTOS
# ============================================================


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SourceError(
        "No fue posible decodificar el archivo de texto.",
        detail="text decode failed for all attempted encodings",
    )


def _extract_pdf_bytes(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise SourceError(
            "El servicio no puede procesar PDF en este momento. Contacta al administrador.",
            detail=f"pypdf import failed: {exc}",
        ) from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(f"[Página {page_number}]\n{text}")
    except Exception as exc:
        raise SourceError(
            "No se pudo leer el PDF. Verifica que el archivo no esté dañado o protegido.",
            detail=f"pypdf parse failed: {exc}",
        ) from exc

    content = "\n\n".join(pages).strip()
    if not content:
        raise SourceError(
            "El PDF se abrió correctamente, pero no contiene texto extraíble. "
            "Si es un PDF escaneado, esta versión requiere OCR.",
            detail="pdf extraction produced empty content",
        )
    return content


def _extract_docx_bytes(data: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise SourceError(
            "El servicio no puede procesar DOCX en este momento. Contacta al administrador.",
            detail=f"python-docx import failed: {exc}",
        ) from exc

    try:
        doc = Document(io.BytesIO(data))
        blocks = [p.text for p in doc.paragraphs if p.text.strip()]

        for table in doc.tables:
            for row in table.rows:
                blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
    except Exception as exc:
        raise SourceError(
            "No se pudo leer el DOCX. Verifica que el archivo no esté dañado.",
            detail=f"python-docx parse failed: {exc}",
        ) from exc

    content = "\n".join(blocks).strip()
    if not content:
        raise SourceError(
            "El DOCX se abrió correctamente, pero no contiene texto.",
            detail="docx extraction produced empty content",
        )
    return content


def extract_source_bytes(name: str, data: bytes) -> str:
    """Núcleo puro de extracción: valida el upload y despacha según el
    tipo de contenido *sniffeado* (no según la extensión del nombre)."""
    validate_upload(name, data)

    kind = sniff_kind(data)
    if kind == "pdf":
        content = _extract_pdf_bytes(data)
    elif kind == "docx":
        content = _extract_docx_bytes(data)
    elif kind == "text":
        content = _decode_text(data)
    else:
        raise SourceError(
            "No se pudo determinar el tipo de contenido del archivo.",
            detail=f"sniff_kind returned {kind!r} for name={name!r}",
        )

    if not content.strip():
        raise SourceError(
            "El documento no contiene contenido utilizable.",
            detail="extracted content is empty after strip",
        )

    return content


def extract_source(uploaded_file) -> str:
    """Wrapper delgado sobre extract_source_bytes para objetos de Streamlit
    (o cualquier objeto con `.name` y `.getvalue()`)."""
    return extract_source_bytes(uploaded_file.name, uploaded_file.getvalue())
