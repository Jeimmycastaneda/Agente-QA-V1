import io
import re
from html import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agente_qa.config import PROJECT_ROOT
from agente_qa.utils import (
    build_case_title,
    normalize_coverage,
    normalize_validation_method,
    safe_steps,
    safe_text,
)

# ============================================================
# PDF
# ============================================================


def pdf_text(value):
    return escape(safe_text(value)).replace("\n", "<br/>")


def _unique_values(cases, key):
    values = []
    seen = set()
    for tc in cases:
        value = re.sub(r"\s+", " ", safe_text(tc.get(key))).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            values.append(value)
    return values


def _pdf_bullets(story, items, style, prefix="•"):
    for item in items:
        text = safe_text(item)
        if text:
            story.append(Paragraph(f"{prefix} {pdf_text(text)}", style))


def _coverage_summary(data):
    rows = []
    for item in data.get("COVERAGE", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append({
            "Requirement / Use Case": safe_text(item.get("Requirement / Use Case")),
            "Criterion": safe_text(item.get("Criterion")),
            "Scenario": safe_text(item.get("Scenario")),
            "Test Case": safe_text(item.get("Test Case")),
            "Validation Method": normalize_validation_method(
                item.get("Validation Method")
            ),
            "Coverage": normalize_coverage(item.get("Coverage")),
            "Alerts": safe_text(item.get("Alerts")),
        })
    return rows


def _register_reference_fonts():
    """Use Aptos from the supplied client reference when bundled."""
    font_dir = PROJECT_ROOT / "fonts"
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


def _case_bullets_as_paragraphs(story, text, style):
    """Render source-style bullets without introducing a new table/column."""
    value = safe_text(text)
    if not value:
        return
    lines = [x.strip() for x in value.splitlines() if x.strip()]
    for line in lines:
        clean = re.sub(r"^[•\-]\s*", "", line)
        story.append(Paragraph(f"• {pdf_text(clean)}", style))


def create_pdf(data, config_key, source_name=""):
    """
    V16 — PDF alineado visual y estructuralmente con el Test Plan del cliente.

    Se conserva la estructura de referencia:
      1) bloque inicial tipo tabla: Descripción del Software, Objetivos,
         Elementos requeridos, Lista de ítems que no serán probados y Entregables;
      2) Test plan Ejecución;
      3) DETALLE DE LOS CASOS DE PRUEBA;
      4) por caso: Test case, SUMMARY, Producto, Módulo, Descripción,
         Resultado esperado de la prueba, Precondiciones y Caso de uso relacionado.

    No agrega columnas ni bloques de resumen que no existen en el documento de
    referencia. Los datos del caso siguen proviniendo del resultado QA.
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
    title_style = ParagraphStyle(
        "ref_title", parent=styles["Normal"], fontName=bold_font,
        fontSize=9.5, leading=11, spaceAfter=4,
    )
    cell_label = ParagraphStyle(
        "ref_label", parent=styles["Normal"], fontName=bold_font,
        fontSize=8, leading=9.5,
    )
    cell_body = ParagraphStyle(
        "ref_body", parent=styles["Normal"], fontName=regular_font,
        fontSize=8, leading=10,
    )
    cell_body_bold = ParagraphStyle(
        "ref_body_bold", parent=cell_body, fontName=bold_font,
    )
    section = ParagraphStyle(
        "ref_section", parent=styles["Normal"], fontName=bold_font,
        fontSize=9.5, leading=11, spaceBefore=8, spaceAfter=5,
    )
    case_head = ParagraphStyle(
        "ref_case", parent=styles["Normal"], fontName=bold_font,
        fontSize=8.8, leading=10.5, spaceBefore=6, spaceAfter=5,
    )
    summary = ParagraphStyle(
        "ref_summary", parent=styles["Normal"], fontName=bold_font,
        fontSize=9, leading=11, spaceBefore=4, spaceAfter=5,
    )
    body = ParagraphStyle(
        "ref_body_main", parent=styles["Normal"], fontName=regular_font,
        fontSize=8.3, leading=11, spaceAfter=4,
    )
    body_bold = ParagraphStyle(
        "ref_body_bold_main", parent=body, fontName=bold_font,
    )
    small_note = ParagraphStyle(
        "ref_note", parent=body, fontName=italic_font,
        fontSize=7.5, leading=9.5,
    )

    cases = data.get("TEST_CASES", []) or []
    products = _unique_values(cases, "Product")
    modules = _unique_values(cases, "Module")
    product_text = ", ".join(products) if products else "No definido en la fuente"
    module_text = ", ".join(modules) if modules else "No definido en la fuente"

    # Fuente del documento: solo se usa para identificar el entregable, no para inventar un ID.
    plan_name = safe_text(source_name, "Documentación proporcionada")

    # Descripción y objetivos se derivan de los casos generados, sin inventar información adicional.
    descriptions = []
    objectives = []
    for tc in cases:
        desc = safe_text(tc.get("Description"))
        if desc and desc.lower() not in {x.lower() for x in descriptions}:
            descriptions.append(desc)
        scenario = safe_text(tc.get("Scenario")) or build_case_title(
            tc, safe_text(tc.get("ID"), "CP-00001")
        )
        if scenario and scenario.lower() not in {x.lower() for x in objectives}:
            objectives.append(scenario)

    description_text = " ".join(descriptions[:3]) if descriptions else (
        "La documentación analizada contiene la información funcional utilizada "
        "para derivar los casos de prueba."
    )

    # ========================================================
    # BLOQUE INICIAL — MISMA ESTRUCTURA DE LA REFERENCIA
    # ========================================================
    story = []
    story.append(Paragraph(f"Test plan: {pdf_text(plan_name)}", title_style))

    objectives_flow = []
    for i, objective in enumerate(objectives[:10], start=1):
        objectives_flow.append(Paragraph(f"{i}. {pdf_text(objective)}", cell_body))

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

    # Build nested content as one cell to reproduce the client's two-column table.
    desc_cell = Paragraph(pdf_text(description_text), cell_body)
    obj_cell = objectives_flow or [Paragraph("No se identificaron objetivos explícitos en la información procesada.", cell_body)]
    elem_cell = elements_flow
    scope_cell = out_scope
    deliver_cell = deliverables

    table_data = [
        [Paragraph("Descripción del<br/>Software", cell_label), desc_cell],
        [Paragraph("Objetivos de las<br/>pruebas", cell_label), obj_cell],
        [Paragraph("Elementos<br/>requeridos", cell_label), elem_cell],
        [Paragraph("Lista de ítems<br/>que no serán<br/>probados", cell_label), scope_cell],
        [Paragraph("Entregables", cell_label), deliver_cell],
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
    story.append(plan_table)
    story.append(Spacer(1, 18))
    story.append(Paragraph("Test plan Ejecución", section))
    story.append(HRFlowable(width="100%", thickness=0.65, color=colors.HexColor("#777777")))
    story.append(Spacer(1, 7))
    story.append(Paragraph("DETALLE DE LOS CASOS DE PRUEBA", section))

    # ========================================================
    # CASOS — MISMA SECUENCIA DE CAMPOS DE LA REFERENCIA
    # ========================================================
    for idx, tc in enumerate(cases, start=1):
        case_id = safe_text(tc.get("ID"), f"CP-{idx:05d}")
        title_value = build_case_title(tc, case_id)

        story.append(
            Paragraph(
                f"Test case {pdf_text(case_id)}: {pdf_text(title_value)}",
                case_head,
            )
        )
        story.append(Paragraph("SUMMARY", summary))
        story.append(Paragraph(
            f"<b>Producto:</b> {pdf_text(safe_text(tc.get('Product'), product_text))}",
            body,
        ))
        story.append(Paragraph(
            f"<b>Módulo:</b> {pdf_text(safe_text(tc.get('Module'), module_text))}",
            body,
        ))
        story.append(Paragraph(
            f"<b>Descripción:</b> {pdf_text(safe_text(tc.get('Description'), 'No definida en la fuente.'))}",
            body,
        ))

        expected_result = safe_text(tc.get("Expected Result"))
        story.append(Paragraph(
            f"<b>Resultado esperado de la prueba:</b> {pdf_text(expected_result or 'No definido en la fuente.')}",
            body,
        ))

        preconditions = safe_text(tc.get("Preconditions"))
        if preconditions:
            story.append(Paragraph("<b>Precondiciones:</b>", body))
            _case_bullets_as_paragraphs(story, preconditions, body)
        else:
            story.append(Paragraph(
                "<b>Precondiciones:</b> No se definieron precondiciones en la fuente.",
                body,
            ))

        related = safe_text(tc.get("Related Use Case"))
        if related:
            story.append(Paragraph("<b>Caso de uso relacionado:</b>", body))
            _case_bullets_as_paragraphs(story, related, body)
        else:
            story.append(Paragraph(
                "<b>Caso de uso relacionado:</b> No se identificó en la fuente.",
                body,
            ))

        # Los Steps se conservan, pero se presentan como texto corrido/numerado,
        # sin crear una tabla o columnas nuevas que no existen en la referencia.
        steps = safe_steps(tc)
        if steps:
            story.append(Spacer(1, 3))
            story.append(Paragraph("<b>Secuencia de prueba:</b>", body))
            for step in steps:
                num = safe_text(step.get("Step #"), "")
                action = safe_text(step.get("Action"))
                expected = safe_text(step.get("Expected value"))
                story.append(Paragraph(
                    f"{pdf_text(num)}. {pdf_text(action)}",
                    body,
                ))
                if expected:
                    story.append(Paragraph(
                        f"Resultado esperado: {pdf_text(expected)}",
                        body,
                    ))

        # Alerts are only printed when the case actually has one, avoiding a new
        # permanent section in every case.
        case_alerts = tc.get("Alerts", [])
        if isinstance(case_alerts, list) and case_alerts:
            for alert in case_alerts:
                if not isinstance(alert, dict):
                    continue
                alert_name = safe_text(alert.get("Alert"))
                reason = safe_text(alert.get("Reason"))
                validation = safe_text(alert.get("Validation Required"))
                note_text = " / ".join(x for x in [alert_name, reason, validation] if x)
                if note_text:
                    story.append(Paragraph(
                        f"<i>Alerta: {pdf_text(note_text)}</i>",
                        small_note,
                    ))

        if idx < len(cases):
            story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
