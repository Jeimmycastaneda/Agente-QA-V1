"""Conector Azure DevOps migrado desde main.
Mantiene sanitización de pipes/escapes, formato de Description y Steps XML,
y modo seguro sin credenciales en código.
"""
from __future__ import annotations
import base64, html, json, os, re
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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
        enabled = os.getenv("AZDO_ENABLED", "false").strip().lower() in {"1","true","yes","si","sí"}
        return cls(os.getenv("AZDO_ORGANIZATION", "").strip(), os.getenv("AZDO_PROJECT", "").strip(), os.getenv("AZDO_PAT", "").strip(), enabled, os.getenv("AZDO_API_VERSION", API_VERSION).strip() or API_VERSION)
    def validate_for_connection(self):
        missing=[]
        if not self.organization: missing.append("AZDO_ORGANIZATION")
        if not self.project: missing.append("AZDO_PROJECT")
        if not self.pat: missing.append("AZDO_PAT")
        if missing: raise AzureDevOpsConfigError("Faltan variables de entorno: "+", ".join(missing))

def _safe(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, list): value="\n".join(str(x) for x in value if x is not None)
    text=str(value).replace("\\r\\n","\n").replace("\\n","\n").replace("\\r","\n").replace("/n","\n").replace("\r\n","\n").replace("\r","\n")
    return text.replace("|", "").strip()

def _auth_header(pat):
    return "Basic "+base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")

def _render_lines(lines):
    clean=[x.strip() for x in lines if x.strip()]
    if not clean: return ""
    bullets=[re.match(r"^[-•●▪◦]\s+(.*)$",x) for x in clean]
    nums=[re.match(r"^(?:\d+[.)]|[ivxlcdm]+\.)\s+(.*)$",x,re.I) for x in clean]
    if all(bullets): return "<ul>"+"".join(f"<li>{html.escape(m.group(1),quote=False)}</li>" for m in bullets)+"</ul>"
    if all(nums): return "<ol>"+"".join(f"<li>{html.escape(m.group(1),quote=False)}</li>" for m in nums)+"</ol>"
    return "<p>"+"<br/>".join(html.escape(x,quote=False) for x in clean)+"</p>"

def _render_rich_text(value):
    text=html.unescape(_safe(value))
    text=re.sub(r"\*\*([^*]+)\*\*",r"\1",text)
    text=re.sub(r"<br\s*/?>","\n",text,flags=re.I)
    text=re.sub(r"</?(?:p|div|span|blockquote)[^>]*>","\n",text,flags=re.I)
    text=re.sub(r"</?(?:ul|ol)[^>]*>","\n",text,flags=re.I)
    text=re.sub(r"<li[^>]*>\s*","- ",text,flags=re.I)
    text=re.sub(r"</li>","\n",text,flags=re.I)
    text=re.sub(r"<[^>]+>","",text)
    text=re.sub(r"[ \t]+"," ",text)
    text=re.sub(r"\n[ \t]+","\n",text)
    text=re.sub(r"[ \t]+\n","\n",text)
    text=re.sub(r"\n{3,}","\n\n",text).strip()
    return "".join(_render_lines([line.strip() for line in block.splitlines() if line.strip()]) for block in re.split(r"\n\s*\n",text) if block.strip())

def _section(title,value):
    value_text=_safe(value)
    if not value_text: return ""
    label=f"<strong>{html.escape(title)}:</strong>"
    content=_render_rich_text(value_text)
    if content.startswith("<p>") and content.endswith("</p>") and "<br/>" not in content:
        return f"<p>{label} {content[3:-4]}</p><p>&nbsp;</p>"
    return f"<p>{label}</p>{content}<p>&nbsp;</p>"

def build_description_html(test_case):
    return "".join(_section(k,test_case.get(v)) for k,v in [("Producto","Product"),("Módulo","Module"),("Descripción","Description"),("Resultado esperado de la prueba","Expected Result"),("Precondiciones","Preconditions"),("Caso de uso relacionado","Related Use Case")]).rstrip("<p>&nbsp;</p>")

def build_steps_xml(test_case):
    steps=test_case.get("Steps") or []; normalized=[]
    for i,step in enumerate(steps,1):
        if not isinstance(step,dict): continue
        action=_safe(step.get("Action") or step.get("action") or step.get("Step")); expected=_safe(step.get("Expected value") or step.get("Expected") or step.get("expected"))
        if action or expected: normalized.append((action,expected))
    root=ET.Element("steps",{"id":"0","last":str(len(normalized))})
    for pos,(action,expected) in enumerate(normalized,1):
        node=ET.SubElement(root,"step",{"id":str(pos),"type":"ActionStep"})
        a=ET.SubElement(node,"parameterizedString",{"isformatted":"true"}); a.text=action
        e=ET.SubElement(node,"parameterizedString",{"isformatted":"true"}); e.text=expected
        ET.SubElement(node,"description")
    return ET.tostring(root,encoding="unicode",short_empty_elements=True)

def build_test_case_patch(test_case):
    title=_safe(test_case.get("Title"))
    if not title: raise ValueError("El Test Case no tiene Title.")
    patch=[{"op":"add","path":"/fields/System.Title","value":title},{"op":"add","path":"/fields/System.Description","value":build_description_html(test_case)},{"op":"add","path":"/fields/Microsoft.VSTS.TCM.Steps","value":build_steps_xml(test_case)}]
    for source,path in (("Area Path","/fields/System.AreaPath"),("Iteration Path","/fields/System.IterationPath"),("Tags","/fields/System.Tags")):
        value=_safe(test_case.get(source))
        if value: patch.append({"op":"add","path":path,"value":value})
    return patch

def _request(config,method,url,body=None):
    headers={"Authorization":_auth_header(config.pat),"Accept":"application/json","User-Agent":"Agente-QA-Streamlit/1.0"}
    data=None
    if body is not None:
        data=json.dumps(body,ensure_ascii=False).encode("utf-8"); headers["Content-Type"]="application/json-patch+json"
    try:
        with urlopen(Request(url,data=data,headers=headers,method=method),timeout=30) as response:
            raw=response.read().decode("utf-8",errors="replace"); return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise AzureDevOpsApiError(f"Azure DevOps respondió HTTP {exc.code}: {exc.read().decode('utf-8',errors='replace')}") from exc
    except URLError as exc:
        raise AzureDevOpsApiError(f"No fue posible conectarse con Azure DevOps: {exc.reason}") from exc

def validate_connection(config=None):
    config=config or AzureDevOpsConfig.from_env(); config.validate_for_connection()
    org=quote(config.organization,safe=""); project=quote(config.project,safe="")
    return _request(config,"GET",f"https://dev.azure.com/{org}/{project}/_apis/projects/{project}?api-version={quote(config.api_version,safe='.')}")

def create_test_case(test_case,config=None):
    config=config or AzureDevOpsConfig.from_env()
    if not config.enabled: raise AzureDevOpsConfigError("AZDO_ENABLED no está activo. El conector está en modo seguro.")
    config.validate_for_connection(); org=quote(config.organization,safe=""); project=quote(config.project,safe="")
    url=f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{quote('$Test Case',safe='')}?api-version={quote(config.api_version,safe='.')}"
    return _request(config,"POST",url,build_test_case_patch(test_case))

def create_test_cases(test_cases,config=None):
    results=[]
    for index,test_case in enumerate(test_cases,1):
        result=create_test_case(test_case,config)
        results.append({"sequence":index,"source_id":_safe(test_case.get("ID")),"title":_safe(test_case.get("Title")),"azure_id":result.get("id"),"url":result.get("_links",{}).get("html",{}).get("href","")})
    return results

def preview_test_case(test_case):
    return {"title":_safe(test_case.get("Title")),"description_html":build_description_html(test_case),"steps_xml":build_steps_xml(test_case),"patch":build_test_case_patch(test_case)}
