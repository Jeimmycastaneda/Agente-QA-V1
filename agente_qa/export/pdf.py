"""Exportación PDF del Test Plan y detalle de casos de prueba."""
from __future__ import annotations
import io, html
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors


def _text(value, default=""):
    if value is None or not str(value).strip(): return default
    return str(value).strip().replace("|","")

def _p(value): return html.escape(_text(value)).replace("\n","<br/>")

def create_pdf(data, config_key="Autos Colectivos", source_name=""):
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=letter,rightMargin=40,leftMargin=40,topMargin=36,bottomMargin=36,title="Test plan Ejecución — Agente QA",author="Agente QA")
    styles=getSampleStyleSheet(); body=ParagraphStyle("body",parent=styles["BodyText"],fontSize=8.5,leading=11,spaceAfter=5); label=ParagraphStyle("label",parent=body,fontName="Helvetica-Bold"); section=ParagraphStyle("section",parent=styles["Heading2"],fontSize=10,leading=12,spaceBefore=8,spaceAfter=6); small=ParagraphStyle("small",parent=body,fontSize=7.5)
    cases=data.get("TEST_CASES",[]) or []; story=[Paragraph("Test plan Ejecución — VERSION PREVIA — DRAFT",styles["Title"]),Paragraph(_p(source_name or "Documentación proporcionada"),body),Spacer(1,8)]
    story.append(Paragraph("Descripción del Software",section)); story.append(Paragraph(_p("La información funcional de la documentación procesada se utiliza como fuente para los casos de prueba."),body))
    story.append(Paragraph("DETALLE DE LOS CASOS DE PRUEBA",section))
    for idx,tc in enumerate(cases,1):
        case_id=_text(tc.get("ID"),f"CP-{idx:05d}"); title=_text(tc.get("Title"),case_id)
        story.append(Paragraph(f"Test case {html.escape(case_id)}: {html.escape(title)}",label)); story.append(Paragraph("SUMMARY",label))
        fields=[("Producto",tc.get("Product")),("Módulo",tc.get("Module")),("Descripción",tc.get("Description")),("Resultado esperado de la prueba",tc.get("Expected Result")),("Precondiciones",tc.get("Preconditions")),("Caso de uso relacionado",tc.get("Related Use Case"))]
        for name,value in fields: story.append(Paragraph(f"<b>{html.escape(name)}:</b> {_p(value or 'Pendiente')}",body))
        story.append(Paragraph("Steps",section))
        rows=[[Paragraph("Steps",label),Paragraph("Action",label),Paragraph("Expected",label)]]
        steps=tc.get("Steps") if isinstance(tc.get("Steps"),list) else []
        for n,step in enumerate(steps,1): rows.append([str(step.get("Step #",n)),Paragraph(_p(step.get("Action")),body),Paragraph(_p(step.get("Expected value",step.get("Expected"))),body)])
        if len(rows)==1: rows.append(["1",Paragraph(_p("Información insuficiente para definir el paso."),body),Paragraph(_p("Validar con el equipo funcional antes de ejecutar."),body)])
        table=Table(rows,colWidths=[38,250,250],repeatRows=1); table.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,colors.grey),("VALIGN",(0,0),(-1,-1),"TOP"),("BACKGROUND",(0,0),(-1,0),colors.lightgrey),("LEFTPADDING",(0,0),(-1,-1),4),("RIGHTPADDING",(0,0),(-1,-1),4)])); story.append(table); story.append(Spacer(1,10))
    doc.build(story); out.seek(0); return out.getvalue()
