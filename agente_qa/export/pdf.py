import io
import re
from pathlib import Path
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _safe_text(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _pdf_text(value):
    return escape(_safe_text(value)).replace("\n", "<br/>")


def _unique_values(cases, key):
    values = []
    seen = set()
    for tc in cases:
        value = re.sub(r"\s+", " ", _safe_text(tc.get(key))).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            values.append(value)
    return values


def _case_bullets_as_paragraphs(story, text, style):
    value = _safe_text(text)
    if not value:
        return
    lines = [x.strip() for x in value.splitlines() if x.strip()]
    for line in lines:
        clean = re.sub(r"^[•\-]\s*", "", line)
        story.append(Paragraph(f"• {_pdf_text(clean)}", style))


def _safe_steps(tc):
    steps = tc.get("Steps", [])
    return steps if isinstance(steps, list) else []


def _build_case_title(tc, case_id):
    title = _safe_text(tc.get("Title"))
    if title:
        return title
    return _safe_text(tc.get("Scenario"), case_id)


def _register_reference_fonts():
    font_dir = Path(__file__).resolve().parent / "fonts"
    regular = font_dir / "Aptos.ttf"
    bold = font_dir / "Aptos-Bold.ttf"
    italic = font_dir / "Aptos-BoldItalic.ttf"
    if regular.exists() and bold.exists():
        try:
            pdfmetrics.registerFont(TTFont("Aptos", str(regular)))
            pdfmetrics.registerFont(TTFont("Aptos-Bold", str(bold)))
            if italic.exists():
                pdfmetrics.registerFont(TTFont("Aptos-BoldItalic", str(italic)))
            return "Aptos", "Aptos-Bold", "Aptos-BoldItalic"
        except Exception:
            pass
    return "Helvetica", "Helvetica-Bold", "Helvetica-BoldOblique"


def create_pdf(data, config_key=None, source_name=""):
    """Create the PDF test plan using the PDF implementation from main.

    This module is an organizational copy. The original app.py remains intact.
    """
    buffer = io.BytesIO()
    regular_font, bold_font, italic_font = _register_reference_fonts()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=36,
        title="Test plan Ejecución — VERSION PREVIA — DRAFT",
        author="Agente QA",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("ref_title", parent=styles["Normal"], fontName=bold_font, fontSize=9.5, leading=11, spaceAfter=4)
    cell_label = ParagraphStyle("ref_label", parent=styles["Normal"], fontName=bold_font, fontSize=8, leading=9.5)
    cell_body = ParagraphStyle("ref_body", parent=styles["Normal"], fontName=regular_font, fontSize=8, leading=10)
    section = ParagraphStyle("ref_section", parent=styles["Normal"], fontName=bold_font, fontSize=9.5, leading=11, spaceBefore=8, spaceAfter=5)
    case_head = ParagraphStyle("ref_case", parent=styles["Normal"], fontName=bold_font, fontSize=8.8, leading=10.5, spaceBefore=6, spaceAfter=5)
    summary = ParagraphStyle("ref_summary", parent=styles["Normal"], fontName=bold_font, fontSize=9, leading=11, spaceBefore=4, spaceAfter=5)
    body = ParagraphStyle("ref_body_main", parent=styles["Normal"], fontName=regular_font, fontSize=8.3, leading=11, spaceAfter=4)
    small_note = ParagraphStyle("ref_note", parent=body, fontName=italic_font, fontSize=7.5, leading=9.5)

    cases = data.get("TEST_CASES", []) or []
    products = _unique_values(cases, "Product")
    modules = _unique_values(cases, "Module")
    product_text = ", ".join(products) if products else "No definido en la fuente"
    module_text = ", ".join(modules) if modules else "No definido en la fuente"
    plan_name = _safe_text(source_name, "Documentación proporcionada")

    descriptions = []
    objectives = []
    for tc in cases:
        desc = _safe_text(tc.get("Description"))
        if desc and desc.lower() not in {x.lower() for x in descriptions}:
            descriptions.append(desc)
        scenario = _safe_text(tc.get("Scenario")) or _build_case_title(tc, _safe_text(tc.get("ID"), "CP-00001"))
        if scenario and scenario.lower() not in {x.lower() for x in objectives}:
            objectives.append(scenario)

    description_text = " ".join(descriptions[:3]) if descriptions else "La documentación analizada contiene la información funcional utilizada para derivar los casos de prueba."

    story = [Paragraph(f"Test plan: {_pdf_text(plan_name)}", title_style)]
    objectives_flow = [Paragraph(f"{i}. {_pdf_text(objective)}", cell_body) for i, objective in enumerate(objectives[:10], start=1)]
    elements_flow = [
        Paragraph("<i>Test plan para la documentación de los casos de prueba y su ejecución:</i>", cell_body),
        Spacer(1, 3),
        Paragraph("1. Software Screen Recorder o capturador de pantallas para grabar las evidencias.", cell_body),
        Spacer(1, 2),
        Paragraph("2. Tipos de pruebas:", cell_body),
        Paragraph("a. Pruebas de integración: Validar de manera general el funcionamiento de los módulos afectados por el ajuste.", cell_body),
        Paragraph("b. Pruebas funcionales: Validaciones de los módulos involucrados en el ajuste según casos de prueba diseñados.", cell_body),
    ]
    out_scope = [Paragraph("1. Cualquier otra funcionalidad no especificada en este documento.", cell_body)]
    deliverables = [
        Paragraph("1. Plan de pruebas.", cell_body),
        Paragraph("2. Informe de la ejecución de las pruebas.", cell_body),
        Paragraph("3. Archivo con evidencias de las pruebas realizadas para el proyecto.", cell_body),
        Paragraph("4. Requerimiento (opcional)", cell_body),
    ]

    table_data = [
        [Paragraph("Descripción del<br/>Software", cell_label), Paragraph(_pdf_text(description_text), cell_body)],
        [Paragraph("Objetivos de las<br/>pruebas", cell_label), objectives_flow or [Paragraph("No se identificaron objetivos explícitos en la información procesada.", cell_body)]],
        [Paragraph("Elementos<br/>requeridos", cell_label), elements_flow],
        [Paragraph("Lista de ítems<br/>que no serán<br/>probados", cell_label), out_scope],
        [Paragraph("Entregables", cell_label), deliverables],
    ]
    plan_table = Table(table_data, colWidths=[105, 435])
    plan_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.65, colors.HexColor("#777777")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([plan_table, Spacer(1, 18), Paragraph("Test plan Ejecución", section), HRFlowable(width="100%", thickness=0.65, color=colors.HexColor("#777777")), Spacer(1, 7), Paragraph("DETALLE DE LOS CASOS DE PRUEBA", section)])

    for idx, tc in enumerate(cases, start=1):
        case_id = _safe_text(tc.get("ID"), f"CP-{idx:05d}")
        title_value = _build_case_title(tc, case_id)
        story.extend([Paragraph(f"Test case {_pdf_text(case_id)}: {_pdf_text(title_value)}", case_head), Paragraph("SUMMARY", summary)])
        story.append(Paragraph(f"<b>Producto:</b> {_pdf_text(_safe_text(tc.get('Product'), product_text))}", body))
        story.append(Paragraph(f"<b>Módulo:</b> {_pdf_text(_safe_text(tc.get('Module'), module_text))}", body))
        story.append(Paragraph(f"<b>Descripción:</b> {_pdf_text(_safe_text(tc.get('Description'), 'No definida en la fuente.'))}", body))
        story.append(Paragraph(f"<b>Resultado esperado de la prueba:</b> {_pdf_text(_safe_text(tc.get('Expected Result'), 'No definido en la fuente.'))}", body))

        preconditions = _safe_text(tc.get("Preconditions"))
        if preconditions:
            story.append(Paragraph("<b>Precondiciones:</b>", body))
            _case_bullets_as_paragraphs(story, preconditions, body)
        else:
            story.append(Paragraph("<b>Precondiciones:</b> No se definieron precondiciones en la fuente.", body))

        related = _safe_text(tc.get("Related Use Case"))
        if related:
            story.append(Paragraph("<b>Caso de uso relacionado:</b>", body))
            _case_bullets_as_paragraphs(story, related, body)
        else:
            story.append(Paragraph("<b>Caso de uso relacionado:</b> No se identificó en la fuente.", body))

        steps = _safe_steps(tc)
        if steps:
            story.extend([Spacer(1, 3), Paragraph("<b>Secuencia de prueba:</b>", body)])
            for step in steps:
                num = _safe_text(step.get("Step #"), "")
                action = _safe_text(step.get("Action"))
                expected = _safe_text(step.get("Expected value"))
                story.append(Paragraph(f"{_pdf_text(num)}. {_pdf_text(action)}", body))
                if expected:
                    story.append(Paragraph(f"Resultado esperado: {_pdf_text(expected)}", body))

        case_alerts = tc.get("Alerts", [])
        if isinstance(case_alerts, list) and case_alerts:
            for alert in case_alerts:
                if not isinstance(alert, dict):
                    continue
                note_text = " / ".join(_safe_text(alert.get(k)) for k in ("Alert", "Reason", "Validation Required") if _safe_text(alert.get(k)))
                if note_text:
                    story.append(Paragraph(f"<i>Alerta: {_pdf_text(note_text)}</i>", small_note))
        if idx < len(cases):
            story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
