"""Exportación PDF del Test Plan y detalle de casos de prueba.

La estructura conserva el contenido funcional de main, pero permanece aislada
del resto de la aplicación para que el PDF no dependa de Streamlit.
"""
from __future__ import annotations

import io
import html
import re
from collections import OrderedDict

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors


def _text(*values, default=""):
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            value = "\n".join(str(x) for x in value if x is not None)
        value = str(value).strip()
        if value:
            return value.replace("|", "")
    return default


def _p(value):
    text = _text(value)
    text = html.escape(text, quote=False)
    text = text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    return text.replace("\n", "<br/>")


def _unique_values(cases, key):
    values = []
    seen = set()
    for case in cases:
        value = re.sub(r"\s+", " ", _text(case.get(key))).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            values.append(value)
    return values


def _bullets(value):
    lines = [x.strip() for x in _text(value).splitlines() if x.strip()]
    return [re.sub(r"^[•●▪◦\-]\s*", "", x) for x in lines]


def _coverage_rows(data):
    rows = []
    for item in data.get("COVERAGE", []) or []:
        if not isinstance(item, dict):
            continue
        rows.append([
            _text(item.get("Requirement / Use Case")),
            _text(item.get("Criterion")),
            _text(item.get("Scenario")),
            _text(item.get("Test Case")),
            _text(item.get("Validation Method"), default="Pendiente"),
            _text(item.get("Coverage"), default="Pendiente"),
            _text(item.get("Alerts"), default="Sin Alertas"),
        ])
    return rows


def create_pdf(data, config_key="Autos Colectivos", source_name=""):
    """Genera el Test Plan y el detalle de CP sin inventar información."""
    out = io.BytesIO()
    doc = SimpleDocTemplate(
        out,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=36,
        bottomMargin=36,
        title="Test plan Ejecución — VERSION PREVIA — DRAFT",
        author="Agente QA",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("qa_title", parent=styles["Title"], fontSize=12, leading=14, spaceAfter=8)
    section = ParagraphStyle("qa_section", parent=styles["Heading2"], fontSize=10, leading=12, spaceBefore=8, spaceAfter=6)
    label = ParagraphStyle("qa_label", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=8, leading=10, spaceAfter=2)
    body = ParagraphStyle("qa_body", parent=styles["BodyText"], fontSize=8, leading=10.5, spaceAfter=4)
    small = ParagraphStyle("qa_small", parent=body, fontSize=7, leading=9)
    case_head = ParagraphStyle("qa_case", parent=label, fontSize=9, leading=11, spaceBefore=7, spaceAfter=4)

    cases = data.get("TEST_CASES", []) or []
    products = _unique_values(cases, "Product")
    modules = _unique_values(cases, "Module")
    source = _text(source_name, default="Documentación proporcionada")

    story = [Paragraph("Test plan Ejecución — VERSION PREVIA — DRAFT", title)]
    story.append(Paragraph(f"<b>Documento fuente:</b> {_p(source)}", body))

    story.append(Paragraph("Descripción del Software", section))
    description_values = [_text(tc.get("Description")) for tc in cases if _text(tc.get("Description"))]
    description = " ".join(OrderedDict.fromkeys(description_values).keys())
    story.append(Paragraph(_p(description or "No definido en la fuente."), body))
    story.append(Paragraph(f"<b>Producto:</b> {_p(', '.join(products) or 'No definido en la fuente')}", body))
    story.append(Paragraph(f"<b>Módulo:</b> {_p(', '.join(modules) or 'No definido en la fuente')}", body))

    story.append(Paragraph("Objetivos", section))
    objectives = []
    for tc in cases:
        value = _text(tc.get("Scenario"), tc.get("Description"))
        if value and value.lower() not in {x.lower() for x in objectives}:
            objectives.append(value)
    if objectives:
        for index, value in enumerate(objectives[:20], 1):
            story.append(Paragraph(f"{index}. {_p(value)}", body))
    else:
        story.append(Paragraph("No definido en la fuente.", body))

    story.append(Paragraph("Elementos requeridos", section))
    story.append(Paragraph("La ejecución debe utilizar únicamente las precondiciones, datos y dependencias definidos en la documentación fuente.", body))

    story.append(Paragraph("Lista de ítems que no serán probados", section))
    story.append(Paragraph("No definido en la fuente. Validar con el equipo funcional.", body))

    story.append(Paragraph("Entregables", section))
    story.append(Paragraph("Casos de prueba generados, matriz de cobertura y alertas identificadas a partir de la documentación fuente.", body))

    coverage = _coverage_rows(data)
    if coverage:
        story.append(PageBreak())
        story.append(Paragraph("Matriz de cobertura", section))
        header = ["Requirement / Use Case", "Criterion", "Scenario", "Test Case", "Validation Method", "Coverage", "Alerts"]
        rows = [[Paragraph(_p(x), label) for x in header]]
        rows.extend([[Paragraph(_p(x), small) for x in row] for row in coverage])
        table = Table(rows, colWidths=[78, 58, 85, 55, 68, 55, 78], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(table)

    story.append(PageBreak())
    story.append(Paragraph("DETALLE DE LOS CASOS DE PRUEBA", section))

    for idx, tc in enumerate(cases, 1):
        case_id = _text(tc.get("ID"), default=f"CP-{idx:05d}")
        case_title = _text(tc.get("Title"), default=case_id)
        story.append(Paragraph(f"Test case {html.escape(case_id)}: {html.escape(case_title)}", case_head))
        story.append(Paragraph("SUMMARY", label))

        fields = [
            ("Producto", tc.get("Product")),
            ("Módulo", tc.get("Module")),
            ("Descripción", tc.get("Description")),
            ("Resultado esperado de la prueba", tc.get("Expected Result"), tc.get("ExpectedResult")),
            ("Precondiciones", tc.get("Preconditions")),
            ("Caso de uso relacionado", tc.get("Related Use Case"), tc.get("RelatedUseCase")),
        ]
        for item in fields:
            name, values = item[0], item[1:]
            value = _text(*values, default="Pendiente")
            if name == "Caso de uso relacionado":
                bullets = _bullets(value)
                if len(bullets) > 1:
                    story.append(Paragraph(f"<b>{html.escape(name)}:</b>", body))
                    for bullet in bullets:
                        story.append(Paragraph(f"• {_p(bullet)}", body))
                    continue
            story.append(Paragraph(f"<b>{html.escape(name)}:</b> {_p(value)}", body))

        story.append(Paragraph("Steps", section))
        rows = [[Paragraph("Steps", label), Paragraph("Action", label), Paragraph("Expected", label)]]
        steps = tc.get("Steps") if isinstance(tc.get("Steps"), list) else []
        for n, step in enumerate(steps, 1):
            if not isinstance(step, dict):
                continue
            rows.append([
                Paragraph(_p(step.get("Step #", n)), body),
                Paragraph(_p(step.get("Action"),), body),
                Paragraph(_p(step.get("Expected value", step.get("Expected"))), body),
            ])
        if len(rows) == 1:
            rows.append([
                Paragraph("1", body),
                Paragraph(_p("Información insuficiente para definir el paso."), body),
                Paragraph(_p("Validar con el equipo funcional antes de ejecutar."), body),
            ])
        table = Table(rows, colWidths=[38, 250, 250], repeatRows=1)
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))

    doc.build(story)
    out.seek(0)
    return out.getvalue()
