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
