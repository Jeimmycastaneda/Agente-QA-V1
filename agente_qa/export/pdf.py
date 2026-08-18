"""Exportación PDF aislada.

El generador definitivo debe conservar la estructura PDF aprobada de main.
"""

import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

def create_pdf(data, config_key="Autos Colectivos", source_name=""):
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("Test plan Ejecución — VERSION PREVIA — DRAFT", styles["Title"])]
    for tc in data.get("TEST_CASES", []):
        story.append(Paragraph(str(tc.get("ID", "")), styles["Heading2"]))
        story.append(Paragraph(str(tc.get("Title", "")), styles["Normal"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    out.seek(0)
    return out.getvalue()
