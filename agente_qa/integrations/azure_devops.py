"""
Ajuste V56 del conector Azure DevOps del Agente QA.

Mantiene la estructura actual del main.
Cambios:
- elimina pipes de todos los textos antes de enviar a Azure;
- corrige \n, /n y escapes de saltos;
- conserva párrafos/listas;
- evita que el contenido quede "espichado";
- mantiene el formato CP-AC[SUITE]-##### cuando el Title ya fue generado;
- no agrega IDPadre automáticamente ni inventa relaciones.
"""

from __future__ import annotations

import base64
import html
import json
import os
import re
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
    def from_env(cls) -> "AzureDevOpsConfig":
        enabled = os.getenv("AZDO_ENABLED", "false").strip().lower() in {
            "1", "true", "yes", "si", "sí"
        }
        return cls(
            organization=os.getenv("AZDO_ORGANIZATION", "").strip(),
            project=os.getenv("AZDO_PROJECT", "").strip(),
            pat=os.getenv("AZDO_PAT", "").strip(),
            enabled=enabled,
            api_version=os.getenv("AZDO_API_VERSION", API_VERSION).strip() or API_VERSION,
        )

    def validate_for_connection(self) -> None:
        missing = []
        if not self.organization:
            missing.append("AZDO_ORGANIZATION")
        if not self.project:
            missing.append("AZDO_PROJECT")
        if not self.pat:
            missing.append("AZDO_PAT")
        if missing:
            raise AzureDevOpsConfigError(
                "Faltan variables de entorno: " + ", ".join(missing)
            )


def _safe(value: Any) -> str:
    """Normalización final de texto para Azure."""
    if value is None:
        return ""

    if isinstance(value, list):
        value = "\n".join(str(x) for x in value if x is not None)

    text = str(value)

    # Escapes literales que han aparecido en las generaciones anteriores.
    text = text.replace("\\r\\n", "\n")
    text = text.replace("\\n", "\n")
    text = text.replace("\\r", "\n")
    text = text.replace("/n", "\n")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Regla definitiva: ningún pipe llega a Azure.
    text = text.replace("|", "")

    return text.strip()


def _auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _render_lines(lines: list[str]) -> str:
    """Renderiza un bloque conservando párrafos y listas."""
    clean_lines = [line.strip() for line in lines if line.strip()]
    if not clean_lines:
        return ""

    bullet_items = []
    numbered_items = []

    for line in clean_lines:
        bullet = re.match(r"^[-•●▪◦]\s+(.*)$", line)
        numbered = re.match(r"^(?:\d+[.)]|[ivxlcdm]+\.)\s+(.*)$", line, re.I)

        if bullet:
            bullet_items.append(bullet.group(1).strip())
        elif numbered:
            numbered_items.append(numbered.group(1).strip())

    if bullet_items and len(bullet_items) == len(clean_lines):
        return "<ul>" + "".join(
            f"<li>{html.escape(item, quote=False)}</li>"
            for item in bullet_items
        ) + "</ul>"

    if numbered_items and len(numbered_items) == len(clean_lines):
        return "<ol>" + "".join(
            f"<li>{html.escape(item, quote=False)}</li>"
            for item in numbered_items
        ) + "</ol>"

    return "<p>" + "<br/>".join(
        html.escape(line, quote=False)
        for line in clean_lines
    ) + "</p>"


def _render_rich_text(value: Any) -> str:
    text = _safe(value)
    if not text:
        return ""

    # Si vienen fragmentos HTML/Markdown de una generación anterior,
    # los convertimos a texto antes de reconstruir el HTML de Azure.
    text = html.unescape(text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:p|div|span|blockquote)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</?(?:ul|ol)[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<li[^>]*>\s*", "- ", text, flags=re.I)
    text = re.sub(r"</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)

    # No compactar el contenido. Solo limpiar espacios horizontales.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
    rendered = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        rendered.append(_render_lines(lines))

    return "".join(rendered)


def _section(title: str, value: Any) -> str:
    value_text = _safe(value)
    if not value_text:
        return ""

    label = f"<strong>{html.escape(title)}:</strong>"
    content = _render_rich_text(value_text)

    # Cada sección tiene su propio párrafo/espacio.
    if content.startswith("<p>") and content.endswith("</p>") and "<br/>" not in content:
        inner = content[3:-4]
        return f"<p>{label} {inner}</p><p>&nbsp;</p>"

    return f"<p>{label}</p>{content}<p>&nbsp;</p>"


def build_description_html(test_case: dict[str, Any]) -> str:
    """Formato visual aprobado para Azure."""
    parts = [
        _section("Producto", test_case.get("Product")),
        _section("Módulo", test_case.get("Module")),
        _section("Descripción", test_case.get("Description")),
        _section(
            "Resultado esperado de la prueba",
            test_case.get("Expected Result"),
        ),
        _section("Precondiciones", test_case.get("Preconditions")),
        _section(
            "Caso de uso relacionado",
            test_case.get("Related Use Case"),
        ),
    ]
    return "".join(parts).rstrip("<p>&nbsp;</p>")


def _step_number(step: dict[str, Any], fallback: int) -> int:
    raw = step.get("Step #", fallback)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback


def build_steps_xml(test_case: dict[str, Any]) -> str:
    """Construye Microsoft.VSTS.TCM.Steps sin pipes ni /n."""
    steps = test_case.get("Steps") or []
    normalized = []

    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue

        action = _safe(
            step.get("Action")
            or step.get("action")
            or step.get("Step")
        )
        expected = _safe(
            step.get("Expected value")
            or step.get("Expected")
            or step.get("expected")
        )

        if not action and not expected:
            continue

        normalized.append({
            "number": _step_number(step, index),
            "action": action,
            "expected": expected,
        })

    root = ET.Element(
        "steps",
        {"id": "0", "last": str(len(normalized))}
    )

    for position, step in enumerate(normalized, start=1):
        node = ET.SubElement(
            root,
            "step",
            {"id": str(position), "type": "ActionStep"},
        )

        action = ET.SubElement(
            node,
            "parameterizedString",
            {"isformatted": "true"},
        )
        action.text = step["action"]

        expected = ET.SubElement(
            node,
            "parameterizedString",
            {"isformatted": "true"},
        )
        expected.text = step["expected"]

        ET.SubElement(node, "description")

    return ET.tostring(
        root,
        encoding="unicode",
        short_empty_elements=True,
    )


def build_test_case_patch(test_case: dict[str, Any]) -> list[dict[str, Any]]:
    title = _safe(test_case.get("Title"))

    if not title:
        raise ValueError("El Test Case no tiene Title.")

    # Defensa final del título: si Gemini agregó pipes, desaparecen.
    title = title.replace("|", "")

    patch = [
        {
            "op": "add",
            "path": "/fields/System.Title",
            "value": title,
        },
        {
            "op": "add",
            "path": "/fields/System.Description",
            "value": build_description_html(test_case),
        },
        {
            "op": "add",
            "path": "/fields/Microsoft.VSTS.TCM.Steps",
            "value": build_steps_xml(test_case),
        },
    ]

    for source_key, azure_path in (
        ("Area Path", "/fields/System.AreaPath"),
        ("Iteration Path", "/fields/System.IterationPath"),
        ("Tags", "/fields/System.Tags"),
    ):
        value = _safe(test_case.get(source_key))
        if value:
            patch.append({
                "op": "add",
                "path": azure_path,
                "value": value,
            })

    return patch


def _request(
    config: AzureDevOpsConfig,
    method: str,
    url: str,
    body: Any | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": _auth_header(config.pat),
        "Accept": "application/json",
        "User-Agent": "Agente-QA-Streamlit/1.0",
    }

    data = None
    if body is not None:
        data = json.dumps(
            body,
            ensure_ascii=False,
        ).encode("utf-8")
        headers["Content-Type"] = "application/json-patch+json"

    request = Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode(
                "utf-8",
                errors="replace",
            )
            return json.loads(raw) if raw else {}

    except HTTPError as exc:
        detail = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise AzureDevOpsApiError(
            f"Azure DevOps respondió HTTP {exc.code}: {detail}"
        ) from exc

    except URLError as exc:
        raise AzureDevOpsApiError(
            f"No fue posible conectarse con Azure DevOps: {exc.reason}"
        ) from exc


def validate_connection(
    config: AzureDevOpsConfig | None = None,
) -> dict[str, Any]:
    config = config or AzureDevOpsConfig.from_env()
    config.validate_for_connection()

    org = quote(config.organization, safe="")
    project = quote(config.project, safe="")

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/projects/"
        f"{project}?api-version={quote(config.api_version, safe='.')}"
    )

    return _request(config, "GET", url)


def create_test_case(
    test_case: dict[str, Any],
    config: AzureDevOpsConfig | None = None,
) -> dict[str, Any]:
    config = config or AzureDevOpsConfig.from_env()

    if not config.enabled:
        raise AzureDevOpsConfigError(
            "AZDO_ENABLED no está activo. El conector está en modo seguro."
        )

    config.validate_for_connection()

    org = quote(config.organization, safe="")
    project = quote(config.project, safe="")
    work_item_type = quote("$Test Case", safe="")

    url = (
        f"https://dev.azure.com/{org}/{project}/_apis/wit/workitems/"
        f"{work_item_type}?api-version={quote(config.api_version, safe='.')}"
    )

    return _request(
        config,
        "POST",
        url,
        build_test_case_patch(test_case),
    )


def create_test_cases(
    test_cases: list[dict[str, Any]],
    config: AzureDevOpsConfig | None = None,
) -> list[dict[str, Any]]:
    results = []

    for index, test_case in enumerate(test_cases, start=1):
        result = create_test_case(
            test_case,
            config=config,
        )

        results.append({
            "sequence": index,
            "source_id": _safe(test_case.get("ID")),
            "title": _safe(test_case.get("Title")),
            "azure_id": result.get("id"),
            "url": result.get(
                "_links",
                {},
            ).get(
                "html",
                {},
            ).get(
                "href",
                "",
            ),
        })

    return results


def preview_test_case(test_case: dict[str, Any]) -> dict[str, Any]:
    """No realiza llamadas de red."""
    return {
        "title": _safe(test_case.get("Title")),
        "description_html": build_description_html(test_case),
        "steps_xml": build_steps_xml(test_case),
        "patch": build_test_case_patch(test_case),
    }
