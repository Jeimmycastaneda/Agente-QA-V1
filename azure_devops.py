"""Azure DevOps integration for Agente QA.

SAFE PHASE 1: read-only connectivity check only.
No create/update/delete operations are implemented here.
"""

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
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

    return {
        "org": org,
        "project": project,
        "pat": pat,
    }


def _auth_header(pat):
    # Azure DevOps PAT authentication uses HTTP Basic auth with an empty username.
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def test_connection():
    """Read-only check of the configured org/project and Test Case work item type.

    This function performs only HTTP GET requests. It does not create, update,
    or delete any Azure DevOps resource.
    """
    config = get_azure_config()
    missing = [key for key in ("org", "project", "pat") if not config[key]]
    if missing:
        raise AzureDevOpsError(
            "Faltan secretos de Azure DevOps: " + ", ".join(missing)
        )

    org = config["org"]
    project = quote(config["project"], safe="")
    url = (
        f"https://dev.azure.com/{quote(org, safe='')}/{project}"
        f"/_apis/wit/workitemtypes/Test%20Case?api-version=7.1"
    )

    request = Request(
        url,
        method="GET",
        headers={
            "Authorization": _auth_header(config["pat"]),
            "Accept": "application/json",
            "User-Agent": "Agente-QA-Streamlit/1.0",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "ok": True,
                "organization": org,
                "project": config["project"],
                "work_item_type": payload.get("name", "Test Case"),
                "message": "Conexión correcta. Solo se realizó una consulta de lectura.",
            }
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
                "No se encontró el proyecto o el tipo de Work Item Test Case. "
                "Verifica AZURE_DEVOPS_ORG y AZURE_DEVOPS_PROJECT."
            ) from exc
        raise AzureDevOpsError(
            f"Azure respondió HTTP {exc.code}. {detail}"
        ) from exc
    except URLError as exc:
        raise AzureDevOpsError(
            f"No fue posible comunicarse con Azure DevOps: {exc.reason}"
        ) from exc
    except Exception as exc:
        raise AzureDevOpsError(f"Error inesperado de conexión: {exc}") from exc
