"""Exportación Excel compatible con Azure DevOps Test Plans."""
from __future__ import annotations
import io
import re
import pandas as pd

AZURE_COLUMNS=["ID","Work Item Type","Title","Description","Test Step","Step Action","Step Expected","Area Path","IDPadre","Tipo Origen Proyecto","Tiempo Real","Assigned To","State"]
MATRIZ_COLUMNS=["TestCaseId","Title","Requirement / Use Case","Criterion","Scenario","Scenario Type","Description","Preconditions","Validation Method","Coverage","Alerts","Effort"]
EXCEL_CONFIGS={
    "Autos Colectivos":{"title_prefix":"CP-AC-","area_path":r"COTIZADORES WEB\DESARROLLO","assigned_to":"","state":"Design"},
    "Siniestros Fasecolda":{"title_prefix":"CP-ACSF-","area_path":r"COTIZADORES WEB\DESARROLLO","assigned_to":"","state":"Design"},
    "General QA":{"title_prefix":"CP-AC-","area_path":r"COTIZADORES WEB\DESARROLLO","assigned_to":"","state":"Design"},
}

def _text(*values):
    for value in values:
        if value is None: continue
        if isinstance(value,(list,dict)): value=" ".join(str(x) for x in value) if isinstance(value,list) else str(value)
        value=str(value).strip()
        if value:return value.replace("|","")
    return ""

def _module_token(module,title="",scenario=""):
    raw=_text(module,title,scenario,"GENERAL"); raw=re.sub(r"[^A-Za-z0-9]+"," ",raw).strip().upper(); words=raw.split()
    if not words:return "GENERAL"
    return words[0][:12] if len(words)==1 else "".join(w[0] for w in words)[:8]

def _case_id(raw_id,module,index,prefix):
    raw=_text(raw_id)
    return raw if re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}",raw,re.I) else f"{prefix}{_module_token(module)}-{index:05d}"

def _title(tc,case_id):
    title=_text(tc.get("Title"))
    if not title or title.upper()==case_id.upper() or re.fullmatch(r"CP-[A-Z0-9_-]+-\d{5}",title,re.I): title=_text(tc.get("Scenario"),tc.get("Description"),tc.get("Related Use Case"),f"Caso de prueba {case_id}")
    return title if title.startswith(case_id) else f"{case_id} {title}"

def _description(tc):
    fields=[("Producto",_text(tc.get("Product"),"Pendiente")),("Módulo",_text(tc.get("Module"),"Pendiente")),("Descripción",_text(tc.get("Description"),tc.get("Scenario"),"Pendiente")),("Resultado esperado de la prueba",_text(tc.get("Expected Result"),tc.get("ExpectedResult"),tc.get("Resultado esperado de la prueba"),"Pendiente")),("Precondiciones",_text(tc.get("Preconditions"),"Pendiente")),("Caso de uso relacionado",_text(tc.get("Related Use Case"),tc.get("RelatedUseCase"),tc.get("Caso de uso relacionado"),"Pendiente"))]
    return "\n\n".join(f"{label}: {value}" for label,value in fields).replace("|","")

def create_excel(data,config_key="Autos Colectivos"):
    config=EXCEL_CONFIGS.get(config_key,EXCEL_CONFIGS["Autos Colectivos"]); azure_rows=[]; matriz_rows=[]
    for idx,tc in enumerate(data.get("TEST_CASES",[]) or [],1):
        module=_text(tc.get("Module"),"GENERAL"); case_id=_case_id(tc.get("ID"),module,idx,config["title_prefix"]); title=_title(tc,case_id); description=_description(tc); steps=tc.get("Steps") if isinstance(tc.get("Steps"),list) else []
        azure_rows.append({"ID":"","Work Item Type":"Test Case","Title":title,"Description":description,"Test Step":"","Step Action":"","Step Expected":"","Area Path":config["area_path"],"IDPadre":"","Tipo Origen Proyecto":"Proyecto","Tiempo Real":"","Assigned To":config["assigned_to"],"State":config["state"]})
        export_steps=steps or [{"Step #":1,"Action":"Información insuficiente para definir el paso.","Expected value":"Validar con el equipo funcional antes de ejecutar."}]
        for n,step in enumerate(export_steps,1):
            azure_rows.append({"ID":"","Work Item Type":"","Title":"","Description":"","Test Step":step.get("Step #",n),"Step Action":_text(step.get("Action"),"Acción no definida"),"Step Expected":_text(step.get("Expected value"),step.get("Expected"),"Resultado esperado no definido"),"Area Path":"","IDPadre":"","Tipo Origen Proyecto":"","Tiempo Real":"","Assigned To":"","State":""})
        matriz_rows.append({"TestCaseId":case_id,"Title":title,"Requirement / Use Case":_text(tc.get("Related Use Case"),tc.get("Requirement / Use Case")),"Criterion":_text(tc.get("Criterion")),"Scenario":_text(tc.get("Scenario"),tc.get("Description")),"Scenario Type":_text(tc.get("Scenario Type"),"No definido"),"Description":description,"Preconditions":_text(tc.get("Preconditions")),"Validation Method":_text(tc.get("Validation Method"),"Pendiente"),"Coverage":_text(tc.get("Coverage"),"Pendiente"),"Alerts":_text(tc.get("Alerts"),"Sin Alertas"),"Effort":_text(tc.get("Effort"),"No definido")})
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        pd.DataFrame(azure_rows,columns=AZURE_COLUMNS).to_excel(writer,sheet_name="Azure Import",index=False)
        pd.DataFrame(matriz_rows,columns=MATRIZ_COLUMNS).to_excel(writer,sheet_name="Matriz QA",index=False)
        for ws in writer.book.worksheets:
            ws.freeze_panes="A2"; ws.auto_filter.ref=ws.dimensions
            for column_cells in ws.columns:
                letter=column_cells[0].column_letter; max_len=max(len(str(c.value or "")) for c in column_cells); ws.column_dimensions[letter].width=min(max(max_len+2,12),60)
    out.seek(0); return out.getvalue()
