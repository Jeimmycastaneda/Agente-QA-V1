from agente_qa.export.pdf import create_pdf


def test_create_pdf_returns_nonempty_pdf_bytes(sample_result):
    pdf_bytes = create_pdf(sample_result, "Autos Colectivos", source_name="sample.txt")
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes[:5] == b"%PDF-"


def test_create_pdf_smoke_all_presets(sample_result):
    for preset in ("Autos Colectivos", "Siniestros Fasecolda", "General QA"):
        pdf_bytes = create_pdf(sample_result, preset, source_name="sample.txt")
        assert pdf_bytes[:5] == b"%PDF-"


def test_create_pdf_without_source_name(sample_result):
    pdf_bytes = create_pdf(sample_result, "General QA")
    assert pdf_bytes[:5] == b"%PDF-"
