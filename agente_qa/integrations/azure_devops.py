"""Integración Azure DevOps del Agente QA.

Toda la comunicación HTTP con Azure vive aquí. La UI solo selecciona y
confirma; este módulo no contiene Streamlit ni credenciales.
"""
from __future__ import annotations
import base64, html, json, os, re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

API_VERSION = os.getenv("AZDO_API_VERSION", "7.1")
class AzureDevOpsConfigError(RuntimeError): pass
class AzureDevOpsApiError(RuntimeError): pass

@dataclass(frozen=True)
class AzureDevOpsConfig:
    organization: str
    project: str
    pat: str
    enabled: bool = False
    api_version: str = API_VERSION
    @classmethod
    def from_env(cls):
        enabled=os.getenv("AZDO_ENABLED","false").strip().lower() in {"1","true","yes","si","sí"}
        return cls(os.getenv("AZDO_ORGANIZATION",os.getenv("AZURE_DEVOPS_ORG","")).strip(),os.getenv("AZDO_PROJECT",os.getenv("AZURE_DEVOPS_PROJECT","")).strip(),os.getenv("AZDO_PAT",os.getenv("AZURE_DEVOPS_PAT","")).strip(),enabled,os.getenv("AZDO_API_VERSION",API_VERSION).strip() or API_VERSION)
    def validate_for_connection(self):
        missing=[k for k,v in (("organization",self.organization),("project",self.project),("pat",self.pat)) if not v]
        if missing: raise AzureDevOpsConfigError("Faltan variables de Azure DevOps: "+", ".join(missing))

def safe_text(*values: Any) -> str:
    """Primer valor útil, normalizado para Azure. Acepta múltiples argumentos."""
    for value in values:
        if value is None: continue
        if isinstance(value,(list,tuple)): value="\n".join(str(x) for x in value if x is not None)
        text=str(value)
        if not text.strip(): continue
        text=text.replace("\\r\\n","\n").replace("\\n","\n").replace("\\r","\n").replace("/n","\n").replace("\r\n","\n").replace("\r","\n")
        return text.replace("|","").strip()
    return ""

def _safe(value): return safe_text(value)
def _auth_header(pat): return "Basic "+base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
def _api_url(config,path,service=""):
    base=f"https://dev.azure.com/{quote(config.organization,safe='')}/{quote(config.project,safe='')}/_apis"
    return base+(f"/{service}" if service else "")+"/"+path.lstrip("/")
def _testplan_url(config,path): return _api_url(config,path,"testplan")

def _request(config,method,url,body=None,content_type="application/json"):
    headers={"Authorization":_auth_header(config.pat),"Accept":"application/json","User-Agent":"Agente-QA-Streamlit/1.0"}
    data=None
    if body is not None:
        data=json.dumps(body,ensure_ascii=False).encode("utf-8"); headers["Content-Type"]=content_type
    try:
        with urlopen(Request(url,data=data,headers=headers,method=method),timeout=30) as response:
            raw=response.read().decode("utf-8",errors="replace"); return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail=exc.read().decode("utf-8",errors="replace")[:1800]
        raise AzureDevOpsApiError(f"Azure DevOps respondió HTTP {exc.code}: {detail}") from exc
    except URLError as exc: raise AzureDevOpsApiError(f"No fue posible conectarse con Azure DevOps: {exc.reason}") from exc

def validate_connection(config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    return _request(config,"GET",_api_url(config,f"projects/{quote(config.project,safe='')}?api-version={quote(config.api_version,safe='.') }"))

def list_test_plans(config=None,limit=10):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    payload=_request(config,"GET",_testplan_url(config,"plans")+"?"+urlencode({"api-version":config.api_version,"$top":int(limit)}))
    plans=sorted(payload.get("value") or [],key=lambda x:int(x.get("id") or 0),reverse=True)[:int(limit)]
    return [{"id":p.get("id"),"name":safe_text(p.get("name"),"Sin nombre"),"state":p.get("state",""),"area_path":p.get("areaPath",""),"iteration":p.get("iteration","")} for p in plans]

def list_test_suites(plan_id,config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    payload=_request(config,"GET",_testplan_url(config,f"Plans/{quote(str(plan_id),safe='')}/suites")+f"?api-version={config.api_version}")
    rows=[]
    for s in payload.get("value") or []:
        parent=s.get("parentSuite") if isinstance(s.get("parentSuite"),dict) else {}
        rows.append({"id":s.get("id"),"name":safe_text(s.get("name"),"Suite sin nombre"),"suite_type":s.get("suiteType",""),"parent_suite":parent.get("id")})
    return rows

def _normalize_case_rows(payload):
    rows=[]; seen=set()
    for item in payload.get("value") or []:
        if not isinstance(item,dict): continue
        wi=next((item[k] for k in ("testCase","workItem") if isinstance(item.get(k),dict)),item); raw_id=wi.get("id") or item.get("id")
        if not raw_id:
            for container in (wi,item):
                for key in ("url","href","webUrl"):
                    m=re.search(r"/workitems/(\d+)(?:[/?]|$)",str(container.get(key,"")),re.I)
                    if m: raw_id=m.group(1); break
                if raw_id: break
        if raw_id is None or str(raw_id).strip() in seen: continue
        raw_id=str(raw_id).strip(); seen.add(raw_id)
        rows.append({"id":raw_id,"title":safe_text(wi.get("name"),wi.get("title"),item.get("name"),item.get("title"),"Test Case sin título"),"raw":item})
    return rows

def list_test_cases(plan_id,suite_id,config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    path=f"Plans/{quote(str(plan_id),safe='')}/Suites/{quote(str(suite_id),safe='')}/TestCase"
    rows=_normalize_case_rows(_request(config,"GET",_testplan_url(config,path)+"?api-version=7.1&expand=true"))
    if rows: return rows
    fallback=_api_url(config,f"Plans/{quote(str(plan_id),safe='')}/suites/{quote(str(suite_id),safe='')}/testcases?api-version=7.1","test")
    return _normalize_case_rows(_request(config,"GET",fallback))

def _render_lines(lines):
    clean=[x.strip() for x in lines if x.strip()]
    if not clean:return ""
    bullets=[re.match(r"^[-•●▪◦]\s+(.*)$",x) for x in clean]; nums=[re.match(r"^(?:\d+[.)]|[ivxlcdm]+\.)\s+(.*)$",x,re.I) for x in clean]
    if all(bullets): return "<ul>"+"".join(f"<li>{html.escape(m.group(1),quote=False)}</li>" for m in bullets)+"</ul>"
    if all(nums): return "<ol>"+"".join(f"<li>{html.escape(m.group(1),quote=False)}</li>" for m in nums)+"</ol>"
    return "<p>"+"<br/>".join(html.escape(x,quote=False) for x in clean)+"</p>"

def _render_rich_text(value):
    text=html.unescape(safe_text(value)); text=re.sub(r"\*\*([^*]+)\*\*",r"\1",text)
    text=re.sub(r"<br\s*/?>","\n",text,flags=re.I); text=re.sub(r"</?(?:p|div|span|blockquote|ul|ol)[^>]*>","\n",text,flags=re.I)
    text=re.sub(r"<li[^>]*>\s*","- ",text,flags=re.I); text=re.sub(r"</li>","\n",text,flags=re.I); text=re.sub(r"<[^>]+>","",text)
    text=re.sub(r"[ \t]+"," ",text); text=re.sub(r"\n{3,}","\n\n",text).strip()
    return "".join(_render_lines([x.strip() for x in b.splitlines() if x.strip()]) for b in re.split(r"\n\s*\n",text) if b.strip())

def _section(title,value):
    value=safe_text(value)
    if not value:return ""
    label=f"<strong>{html.escape(title)}:</strong>"; content=_render_rich_text(value)
    if content.startswith("<p>") and content.endswith("</p>") and "<br/>" not in content:return f"<p>{label} {content[3:-4]}</p><p>&nbsp;</p>"
    return f"<p>{label}</p>{content}<p>&nbsp;</p>"

def build_description_html(test_case):
    return "".join(_section(k,test_case.get(v)) for k,v in [("Producto","Product"),("Módulo","Module"),("Descripción","Description"),("Resultado esperado de la prueba","Expected Result"),("Precondiciones","Preconditions"),("Caso de uso relacionado","Related Use Case")]).rstrip()

def build_steps_xml(test_case):
    root=ET.Element("steps",{"id":"0","last":"0"}); position=0
    for step in test_case.get("Steps") or []:
        if not isinstance(step,dict):continue
        action=safe_text(step.get("Action"),step.get("action"),step.get("Step")); expected=safe_text(step.get("Expected value"),step.get("Expected"),step.get("expected"))
        if not action and not expected:continue
        position+=1; node=ET.SubElement(root,"step",{"id":str(position),"type":"ActionStep"}); a=ET.SubElement(node,"parameterizedString",{"isformatted":"true"}); a.text=action; e=ET.SubElement(node,"parameterizedString",{"isformatted":"true"}); e.text=expected; ET.SubElement(node,"description")
    root.set("last",str(position)); return ET.tostring(root,encoding="unicode",short_empty_elements=True)

def build_test_case_patch(test_case,parent_id=None,area_path=None):
    title=safe_text(test_case.get("Title"))
    if not title:raise ValueError("El Test Case no tiene Title.")
    patch=[{"op":"add","path":"/fields/System.Title","value":title},{"op":"add","path":"/fields/System.Description","value":build_description_html(test_case)},{"op":"add","path":"/fields/Microsoft.VSTS.TCM.Steps","value":build_steps_xml(test_case)},{"op":"add","path":"/fields/Custom.TipoOrigenProyecto","value":safe_text(test_case.get("Tipo Origen Proyecto"),"Proyecto")}]
    area=safe_text(area_path,test_case.get("Area Path"),r"COTIZADORES WEB\DESARROLLO")
    if area:patch.append({"op":"add","path":"/fields/System.AreaPath","value":area})
    parent=safe_text(parent_id,test_case.get("IDPadre"))
    if parent:patch.append({"op":"add","path":"/fields/Custom.IDPadre","value":int(parent) if parent.isdigit() else parent})
    return patch

def create_test_case(test_case,config=None,parent_id=None,area_path=None):
    config=config or AzureDevOpsConfig.from_env()
    if not config.enabled:raise AzureDevOpsConfigError("AZDO_ENABLED no está activo. El conector está en modo seguro.")
    config.validate_for_connection(); url=_api_url(config,f"$Test%20Case?api-version={quote(config.api_version,safe='.')}","wit/workitems")
    return _request(config,"POST",url,build_test_case_patch(test_case,parent_id,area_path),"application/json-patch+json")

def add_parent_relation_to_work_item(work_item_id,parent_id,config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    if not safe_text(work_item_id) or not safe_text(parent_id):raise AzureDevOpsApiError("Falta el ID del Test Case o del Parent.")
    url=_api_url(config,f"{quote(str(work_item_id),safe='')}?api-version={config.api_version}","wit/workitems"); parent_url=_api_url(config,quote(str(parent_id),safe=''),"wit/workitems")
    patch=[{"op":"add","path":"/relations/-","value":{"rel":"System.LinkTypes.Hierarchy-Reverse","url":parent_url,"attributes":{"comment":"Parent configurado desde la Suite destino."}}}]
    return _request(config,"PATCH",url,patch,"application/json-patch+json")

def add_test_cases_to_suite(plan_id,suite_id,work_item_ids,config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    if not work_item_ids:return []
    path=f"Plans/{quote(str(plan_id),safe='')}/Suites/{quote(str(suite_id),safe='')}/TestCase"; payload=_request(config,"POST",_testplan_url(config,path)+"?api-version=7.1",[{"workItem":{"id":int(w)}} for w in work_item_ids])
    return payload.get("value",payload if isinstance(payload,list) else [])

def parse_steps_xml(xml_text):
    if not xml_text:return []
    decoded=html.unescape(str(xml_text)); rows=[]
    for match in re.finditer(r"<step\b[^>]*>.*?</step>",decoded,re.I|re.S):
        vals=re.findall(r"<parameterizedString[^>]*>(.*?)</parameterizedString>",match.group(0),re.I|re.S); vals=[html.unescape(re.sub(r"<[^>]+>","",v)).strip() for v in vals[:2]]
        if vals:rows.append({"Step #":len(rows)+1,"Action":vals[0],"Expected value":vals[1] if len(vals)>1 else ""})
    return rows

def get_test_case_detail(test_case_id,config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection(); payload=_request(config,"GET",_api_url(config,f"{quote(str(test_case_id),safe='')}?api-version=7.1","wit/workitems")); fields=payload.get("fields") or {}
    return {"id":payload.get("id"),"title":fields.get("System.Title",""),"description":fields.get("System.Description","") or "","steps":parse_steps_xml(fields.get("Microsoft.VSTS.TCM.Steps","") or ""),"area_path":fields.get("System.AreaPath",""),"iteration_path":fields.get("System.IterationPath",""),"state":fields.get("System.State",""),"raw_fields":fields}

def preview_test_case(test_case,parent_id=None,area_path=None):
    return {"title":safe_text(test_case.get("Title")),"description_html":build_description_html(test_case),"steps_xml":build_steps_xml(test_case),"patch":build_test_case_patch(test_case,parent_id,area_path)}
