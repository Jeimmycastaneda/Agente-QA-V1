"""
Conector Azure DevOps para el Agente QA.

Versión reorganizada desde main. No contiene credenciales.
"""

from __future__ import annotations
import base64
import html
import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

API_VERSION = os.getenv("AZDO_API_VERSION", "7.1")

class AzureDevOpsConfigError(RuntimeError):
    pass

class AzureDevOpsApiError(RuntimeError):
    pass

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
        return cls(
            organization=os.getenv("AZDO_ORGANIZATION", "").strip(),
            project=os.getenv("AZDO_PROJECT", "").strip(),
            pat=os.getenv("AZDO_PAT", "").strip(),
            enabled=enabled,
            api_version=os.getenv("AZDO_API_VERSION", API_VERSION).strip() or API_VERSION,
        )

    def validate_for_connection(self):
        missing = []
        if not self.organization: missing.append("AZDO_ORGANIZATION")
        if not self.project: missing.append("AZDO_PROJECT")
        if not self.pat: missing.append("AZDO_PAT")
        if missing:
            raise AzureDevOpsConfigError("Faltan variables de entorno: " + ", ".join(missing))

def _safe(value):
    return "" if value is None else str(value).strip()

def _auth_header(pat):
    token = base64.b64encode(f":{pat}".encode()).decode("ascii")
    return f"Basic {token}"

def _request(config, method, url, body=None, content_type="application/json"):
    headers = {"Authorization": _auth_header(config.pat), "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        headers["Content-Type"] = content_type
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AzureDevOpsApiError(f"Azure DevOps respondió HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise AzureDevOpsApiError(f"No fue posible conectarse con Azure DevOps: {exc.reason}") from exc

def build_description_html(test_case):
    sections = [
        ("Producto", test_case.get("Product")),
        ("Módulo", test_case.get("Module")),
        ("Descripción", test_case.get("Description")),
        ("Resultado esperado de la prueba", test_case.get("Expected Result")),
        ("Precondiciones", test_case.get("Preconditions")),
        ("Caso de uso relacionado", test_case.get("Related Use Case")),
    ]
    html_parts = []
    for label, value in sections:
        text = _safe(value)
        if not text:
            continue
        lines = [x.strip(" •-\t") for x in text.splitlines() if x.strip()]
        label_html = f"<strong>{html.escape(label)}:</strong>"
        if len(lines) == 1:
            html_parts.append(f"<p>{label_html} {html.escape(lines[0])}</p>")
        else:
            html_parts.append(f"<p>{label_html}</p><ul>{''.join(f'<li>{html.escape(x)}</li>' for x in lines)}</ul>")
    return "".join(html_parts)

def build_steps_xml(test_case):
    steps = test_case.get("Steps") or []
    root = ET.Element("steps", {"id": "0", "last": str(len(steps))})
    for position, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue
        node = ET.SubElement(root, "step", {"id": str(position), "type": "ActionStep"})
        action = ET.SubElement(node, "parameterizedString", {"isformatted": "true"})
        action.text = _safe(step.get("Action"))
        expected = ET.SubElement(node, "parameterizedString", {"isformatted": "true"})
        expected.text = _safe(step.get("Expected value"))
        ET.SubElement(node, "description")
    return ET.tostring(root, encoding="unicode", short_empty_elements=True)

def build_test_case_patch(test_case):
    title = _safe(test_case.get("Title"))
    if not title:
        raise ValueError("El Test Case no tiene Title.")
    return [
        {"op":"add","path":"/fields/System.Title","value":title},
        {"op":"add","path":"/fields/System.Description","value":build_description_html(test_case)},
        {"op":"add","path":"/fields/Microsoft.VSTS.TCM.Steps","value":build_steps_xml(test_case)},
    ]

def validate_connection(config=None):
    config = config or AzureDevOpsConfig.from_env()
    config.validate_for_connection()
    org = quote(config.organization, safe="")
    project = quote(config.project, safe="")
    url = f"https://dev.azure.com/{org}/{project}/_apis/projects/{project}?api-version={quote(config.api_version, safe='.')}"
    return _request(config, "GET", url)

def create_test_case(test_case, config=None):
    config = config or AzureDevOpsConfig.from_env()
    if not config.enabled:
        raise AzureDevOpsConfigError("AZDO_ENABLED no está activo. El conector está en modo seguro.")
    config.validate_for_connection()
    org = quote(config.organization, safe="")
    project = quote(config.project, safe="")
    work_item_type = quote("$Test Case", safe="")
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{work_item_type}?api-version={quote(config.api_version, safe='.')}"
    return _request(config, "POST", url, build_test_case_patch(test_case), "application/json-patch+json")

def preview_test_case(test_case):
    return {
        "title": _safe(test_case.get("Title")),
        "description_html": build_description_html(test_case),
        "steps_xml": build_steps_xml(test_case),
        "patch": build_test_case_patch(test_case),
    }
