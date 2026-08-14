"""Azure DevOps integration for Agente QA.

SAFE PHASE 1: read-only connectivity and Test Plans consultation only.
No create/update/delete operations are implemented here.

IMPORTANT: this module is intentionally restricted to GET requests.
"""

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class AzureDevOpsError(RuntimeError):
    """Controlled Azure DevOps integration error."""


def get_azure_config():
    """Read Azure DevOps configuration from Streamlit secrets or env vars."""
    try:
        import streamlit as st
        secrets = st.secrets
    except Exception:
        secrets = {}

    org = str(secrets.get("AZURE_DEVOPS_ORG", os.getenv("AZURE_DEVOPS_ORG", ""))).strip()
    project = str(secrets.get("AZURE_DEVOPS_PROJECT", os.getenv("AZURE_DEVOPS_PROJECT", ""))).strip()
    pat = str(secrets.get("AZURE_DEVOPS_PAT", os.getenv("AZURE_DEVOPS_PAT", ""))).strip()
    return {"org": org, "project": project, "pat": pat}


def _auth_header(pat):
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _get_json(url, pat):
    """Execute one GET request. This helper NEVER performs writes."""
    request = Request(
        url,
        method="GET",
        headers={
            "Authorization": _auth_header(pat),
            "Accept": "application/json",
            "User-Agent": "Agente-QA-Streamlit/1.0",
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, response.headers
    except HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
        except Exception:
            pass
        if exc.code in (401, 403):
            raise AzureDevOpsError(
                f"Azure rechazó la autenticación/autorización (HTTP {exc.code}). "
                "Verifica el PAT, su vigencia y sus scopes."
            ) from exc
        if exc.code == 404:
            raise AzureDevOpsError(
                "No se encontró el proyecto o el recurso de Test Plans. "
                "Verifica AZURE_DEVOPS_ORG y AZURE_DEVOPS_PROJECT."
            ) from exc
        raise AzureDevOpsError(f"Azure respondió HTTP {exc.code}. {detail}") from exc
    except URLError as exc:
        raise AzureDevOpsError(
            f"No fue posible comunicarse con Azure DevOps: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise AzureDevOpsError(f"Error inesperado de conexión: {exc}") from exc


def _validate_config(config):
    missing = [key for key in ("org", "project", "pat") if not config[key]]
    if missing:
        raise AzureDevOpsError(
            "Faltan secretos de Azure DevOps: " + ", ".join(missing)
        )


def test_connection():
    """Read-only check of the configured org/project and Test Case work item type.

    This function performs only HTTP GET requests. It does not create, update,
    or delete any Azure DevOps resource.
    """
    config = get_azure_config()
    _validate_config(config)
    org = config["org"]
    project = quote(config["project"], safe="")
    url = (
        f"https://dev.azure.com/{quote(org, safe='')}/{project}"
        f"/_apis/wit/workitemtypes/Test%20Case?api-version=7.1"
    )
    payload, _ = _get_json(url, config["pat"])
    return {
        "ok": True,
        "organization": org,
        "project": config["project"],
        "work_item_type": payload.get("name", "Test Case"),
        "message": "Conexión correcta. Solo se realizó una consulta de lectura.",
    }


def list_test_plans():
    """Return the Test Plans visible to the configured project.

    SAFETY CONTRACT: this function ONLY issues GET requests to the Test Plans
    list endpoint. It does not create, update, delete, or modify Test Plans,
    Test Suites, Test Cases, Work Items, or any other Azure DevOps resource.
    """
    config = get_azure_config()
    _validate_config(config)

    org = quote(config["org"], safe="")
    project = quote(config["project"], safe="")
    base_url = f"https://dev.azure.com/{org}/{project}/_apis/testplan/plans"
    continuation = None
    plans = []

    # Read all pages when Azure provides a continuation token. Every request
    # remains GET-only and is limited to the Test Plans list endpoint.
    while True:
        params = {"api-version": "7.1"}
        if continuation:
            params["continuationToken"] = continuation
        url = f"{base_url}?{urlencode(params)}"
        payload, headers = _get_json(url, config["pat"])
        plans.extend(payload.get("value") or [])
        continuation = headers.get("x-ms-continuationtoken")
        if not continuation:
            break

    return {
        "ok": True,
        "organization": config["org"],
        "project": config["project"],
        "count": len(plans),
        "plans": [
            {
                "id": plan.get("id"),
                "name": plan.get("name", ""),
                "state": plan.get("state", ""),
                "area_path": plan.get("areaPath", ""),
                "iteration": plan.get("iteration", ""),
            }
            for plan in plans
        ],
        "message": (
            "Consulta de Test Plans correcta. Solo se realizaron consultas GET; "
            "no se creó, modificó ni eliminó ningún recurso."
        ),
    }



def _project_testplan_url(config, path):
    org = quote(config["org"], safe="")
    project = quote(config["project"], safe="")
    return f"https://dev.azure.com/{org}/{project}/_apis/testplan/{path}"


def list_test_plans(limit=10):
    """Read-only: returns only the 10 most recent plans from the first API response."""
    config = get_azure_config()
    _validate_config(config)
    url = _project_testplan_url(config, "plans") + "?api-version=7.1"
    payload, _ = _get_json(url, config["pat"])
    plans = payload.get("value") or []
    plans = sorted(plans, key=lambda x: int(x.get("id") or 0), reverse=True)[:int(limit)]
    return {"ok": True, "organization": config["org"], "project": config["project"], "count": len(plans), "plans": [
        {"id": p.get("id"), "name": p.get("name", ""), "state": p.get("state", ""),
         "area_path": p.get("areaPath", ""), "iteration": p.get("iteration", ""),
         "start_date": p.get("startDate", ""), "end_date": p.get("endDate", "")}
        for p in plans
    ], "message": "Consulta de Test Plans correcta. Solo se realizó una consulta GET; no se modificó Azure."}


def get_test_plan(plan_id):
    """Read-only detail for one selected Test Plan."""
    config = get_azure_config(); _validate_config(config)
    url = _project_testplan_url(config, f"plans/{quote(str(plan_id), safe='')}") + "?api-version=7.1"
    payload, _ = _get_json(url, config["pat"])
    return payload


def list_test_suites(plan_id):
    """Read-only: list suites belonging to one selected Test Plan."""
    config = get_azure_config(); _validate_config(config)
    url = _project_testplan_url(config, f"Plans/{quote(str(plan_id), safe='')}/suites") + "?api-version=7.1"
    payload, _ = _get_json(url, config["pat"])
    suites = payload.get("value") or []
    return [{"id": s.get("id"), "name": s.get("name", ""), "suite_type": s.get("suiteType", ""),
             "plan_id": s.get("plan", {}).get("id") if isinstance(s.get("plan"), dict) else plan_id,
             "parent_suite": s.get("parentSuite", {}).get("id") if isinstance(s.get("parentSuite"), dict) else None}
            for s in suites]


def list_test_cases(plan_id, suite_id):
    """Read-only: list Test Cases in one selected Suite.

    Uses the Azure DevOps Test service endpoint because some projects return
    404 for the equivalent Test Plan controller endpoint even though the
    selected Test Plan and Suite are valid. This function is GET-only.
    """
    config = get_azure_config(); _validate_config(config)
    org = quote(config["org"], safe="")
    project = quote(config["project"], safe="")
    plan = quote(str(plan_id), safe="")
    suite = quote(str(suite_id), safe="")

    # Official Azure DevOps Test API: list all test cases in a suite.
    # GET only; no create/update/delete operation is performed.
    url = (
        f"https://dev.azure.com/{org}/{project}"
        f"/_apis/test/Plans/{plan}/suites/{suite}/testcases?api-version=7.1"
    )
    payload, _ = _get_json(url, config["pat"])

    rows = []
    for item in payload.get("value") or []:
        tc = item.get("testCase") if isinstance(item.get("testCase"), dict) else item
        test_id = tc.get("id") or item.get("id")
        if not test_id:
            continue

        # The suite-list response normally contains only the Test Case id/url.
        # Read the title with a separate GET so the UI can offer a meaningful
        # reference selector.
        title = tc.get("name") or tc.get("title") or ""
        if not title:
            try:
                detail = get_test_case_detail(test_id)
                title = detail.get("title", "")
            except Exception:
                title = ""

        rows.append({"id": test_id, "title": title, "raw": item})

    return rows

def _parse_steps_xml(xml_text):
    import html as _html
    import re as _re
    if not xml_text:
        return []
    text = _html.unescape(str(xml_text))
    steps = []
    for match in _re.finditer(r'<step\b[^>]*>.*?</step>', text, flags=_re.I | _re.S):
        node = match.group(0)
        vals = _re.findall(r'<parameterizedString[^>]*>(.*?)</parameterizedString>', node, flags=_re.I | _re.S)
        clean = []
        for value in vals[:2]:
            value = _re.sub(r'<[^>]+>', '', value)
            clean.append(_html.unescape(value).strip())
        if clean:
            steps.append({"Step #": len(steps)+1, "Action": clean[0] if len(clean)>0 else "", "Expected value": clean[1] if len(clean)>1 else ""})
    return steps


def get_test_case_detail(test_case_id):
    """Read-only detail of one existing Test Case for structure comparison."""
    config = get_azure_config(); _validate_config(config)
    org = quote(config["org"], safe=""); project = quote(config["project"], safe="")
    url = f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/{quote(str(test_case_id), safe='')}?api-version=7.1"
    payload, _ = _get_json(url, config["pat"])
    fields = payload.get("fields") or {}
    description = fields.get("System.Description", "") or ""
    steps_xml = fields.get("Microsoft.VSTS.TCM.Steps", "") or ""
    steps = _parse_steps_xml(steps_xml)
    return {
        "id": payload.get("id"),
        "title": fields.get("System.Title", ""),
        "description": description,
        "steps": steps,
        "area_path": fields.get("System.AreaPath", ""),
        "iteration_path": fields.get("System.IterationPath", ""),
        "state": fields.get("System.State", ""),
        "work_item_type": fields.get("System.WorkItemType", "Test Case"),
        "raw_fields": fields,
    }


def compare_test_case_structure(detail):
    """No network. Compares the selected Azure case with our approved structure."""
    description = str(detail.get("description") or "")
    labels = ["Producto:", "Módulo:", "Descripción:", "Resultado esperado de la prueba:", "Precondiciones:", "Caso de uso relacionado:"]
    present = {label: label.lower() in description.lower() for label in labels}
    return {
        "description_has_product": present["Producto:"],
        "description_has_module": present["Módulo:"],
        "description_has_description": present["Descripción:"],
        "description_has_expected": present["Resultado esperado de la prueba:"],
        "description_has_preconditions": present["Precondiciones:"],
        "description_has_related_use_case": present["Caso de uso relacionado:"],
        "steps_count": len(detail.get("steps") or []),
        "steps_have_action_expected": all(bool(str(s.get("Action", "")).strip()) and bool(str(s.get("Expected value", "")).strip()) for s in (detail.get("steps") or [])),
        "reference_model": "Description: Producto + Módulo + Descripción + Resultado esperado de la prueba + Precondiciones + Caso de uso relacionado; Steps: Steps + Action + Expected."
    }
