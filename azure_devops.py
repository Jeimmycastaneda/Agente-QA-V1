"""
Conector Azure DevOps para el Agente QA.

IMPORTANTE:
- Por defecto AZDO_ENABLED=false.
- No contiene credenciales.
- No modifica el prompt QA ni el Excel/PDF existente.
- Crea un Work Item de tipo "Test Case".
- Guarda los pasos nativos de Azure DevOps en Microsoft.VSTS.TCM.Steps.
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
    if value is None:
        return ""
    return str(value).strip()


def _as_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_safe(x) for x in value if _safe(x)]
    text = _safe(value)
    if not text:
        return []
    return [line.strip(" •-\t") for line in text.splitlines() if line.strip()]


def _render_rich_text(value: Any) -> str:
    """Convierte texto del CP a HTML conservando párrafos, listas y saltos reales.

    No usa pipes como separadores y nunca convierte cada línea de un bloque en
    una lista automáticamente.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        lines = [_safe(x) for x in value if _safe(x)]
        text = "\n".join(lines)
    else:
        text = _safe(value)

    # Corrige escapes literales provenientes de modelos/serialización.
    text = text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "\n")
    # Nunca usar pipe como separador visual.
    text = text.replace("|", "\n")

    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    html_blocks = []

    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        # Lista con viñetas.
        bullet_lines = []
        all_bullets = True
        for ln in lines:
            m = re.match(r"^[-•●▪◦]\s+(.*)$", ln)
            if m:
                bullet_lines.append(m.group(1).strip())
            else:
                all_bullets = False
                break
        if all_bullets and bullet_lines:
            html_blocks.append("<ul>" + "".join(f"<li>{html.escape(x)}</li>" for x in bullet_lines) + "</ul>")
            continue

        # Lista numerada o con numeración romana: conservar como líneas separadas.
        if all(re.match(r"^(?:[ivxlcdm]+\.|\d+[.)])\s+", ln, re.I) for ln in lines):
            html_blocks.append("<ol>" + "".join(
                f"<li>{html.escape(re.sub(r'^(?:[ivxlcdm]+\.|\d+[.)])\s+', '', ln, flags=re.I))}</li>"
                for ln in lines
            ) + "</ol>")
            continue

        # Párrafo: conservar saltos internos con <br>.
        html_blocks.append("<p>" + "<br>".join(html.escape(ln) for ln in lines) + "</p>")

    return "".join(html_blocks)


def _section(title: str, value: Any) -> str:
    """Construye cada bloque principal de Description como un párrafo HTML.

    Las listas internas se conservan como listas; no se convierten todas las
    líneas en <li>. Esto evita que Azure compacte o distorsione la Description.
    """
    rendered = _render_rich_text(value)
    if not rendered:
        return ""
    label = f"<strong>{html.escape(title)}:</strong>"

    # Para valores simples, etiqueta y contenido permanecen en el mismo
    # párrafo. Para contenido con listas/párrafos, la etiqueta queda arriba
    # y el contenido conserva su estructura visual.
    plain = _safe(value).replace(r"\r\n", "\n").replace(r"\n", "\n").strip()
    if "\n" not in plain and "<ul>" not in rendered and "<ol>" not in rendered:
        return f"<p>{label} {rendered[3:-4] if rendered.startswith('<p>') and rendered.endswith('</p>') else rendered}</p>"
    return f"<p>{label}</p>{rendered}"


def build_description_html(test_case: dict[str, Any]) -> str:
    """Construye la Description HTML final para Azure DevOps.

    Orden aprobado: Producto, Módulo, Descripción, Resultado esperado de la
    prueba, Precondiciones y Caso de uso relacionado.
    """
    parts = [
        _section("Producto", test_case.get("Product")),
        _section("Módulo", test_case.get("Module")),
        _section("Descripción", test_case.get("Description")),
        _section("Resultado esperado de la prueba", test_case.get("Expected Result")),
        _section("Precondiciones", test_case.get("Preconditions")),
        _section("Caso de uso relacionado", test_case.get("Related Use Case")),
    ]
    return "".join(parts)


def _step_number(step: dict[str, Any], fallback: int) -> int:
    raw = step.get("Step #", fallback)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return fallback


def build_steps_xml(test_case: dict[str, Any]) -> str:
    """
    Construye el XML esperado por el campo:
    Microsoft.VSTS.TCM.Steps

    Cada Step mantiene Action y Expected value separados.
    No se inventa Expected value: si viene vacío, se conserva vacío.
    """
    steps = test_case.get("Steps") or []
    normalized = []
    for index, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            continue
        normalized.append({
            "number": _step_number(step, index),
            "action": _safe(step.get("Action")),
            "expected": _safe(step.get("Expected value")),
        })

    root = ET.Element(
        "steps",
        {"id": "0", "last": str(len(normalized))}
    )

    for position, step in enumerate(normalized, start=1):
        step_id = str(position)
        node = ET.SubElement(
            root,
            "step",
            {"id": step_id, "type": "ActionStep"},
        )
        action = ET.SubElement(
            node, "parameterizedString", {"isformatted": "true"}
        )
        action.text = step["action"]

        expected = ET.SubElement(
            node, "parameterizedString", {"isformatted": "true"}
        )
        expected.text = step["expected"]

        ET.SubElement(node, "description")

    return ET.tostring(root, encoding="unicode", short_empty_elements=True)


def build_test_case_patch(test_case: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Genera el JSON Patch para crear un Test Case.
    """
    title = _safe(test_case.get("Title"))
    if not title:
        raise ValueError("El Test Case no tiene Title.")

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

    # Campos opcionales que existen en el modelo del agente.
    # Solo se envían si la fuente realmente los trae.
    area_path = _safe(test_case.get("Area Path"))
    iteration_path = _safe(test_case.get("Iteration Path"))
    tags = _safe(test_case.get("Tags"))

    if area_path:
        patch.append({
            "op": "add",
            "path": "/fields/System.AreaPath",
            "value": area_path,
        })

    if iteration_path:
        patch.append({
            "op": "add",
            "path": "/fields/System.IterationPath",
            "value": iteration_path,
        })

    if tags:
        patch.append({
            "op": "add",
            "path": "/fields/System.Tags",
            "value": tags,
        })

    return patch


def _auth_header(pat: str) -> str:
    token = base64.b64encode(f":{pat}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _request(
    config: AzureDevOpsConfig,
    method: str,
    url: str,
    body: Any | None = None,
) -> dict[str, Any]:
    headers = {
        "Authorization": _auth_header(config.pat),
        "Accept": "application/json",
    }

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json-patch+json"

    request = Request(url, data=data, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AzureDevOpsApiError(
            f"Azure DevOps respondió HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise AzureDevOpsApiError(
            f"No fue posible conectarse con Azure DevOps: {exc.reason}"
        ) from exc


def validate_connection(config: AzureDevOpsConfig | None = None) -> dict[str, Any]:
    """
    Comprueba acceso al proyecto sin crear ni modificar Work Items.
    """
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
    """
    Crea un Test Case real únicamente cuando AZDO_ENABLED=true.

    El Work Item type es Test Case y los pasos se almacenan en
    Microsoft.VSTS.TCM.Steps para que Azure DevOps los muestre
    como Steps / Action / Expected result.
    """
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
    """
    Crea los casos uno por uno para facilitar trazabilidad y detectar
    exactamente cuál caso falla.
    """
    results = []
    for index, test_case in enumerate(test_cases, start=1):
        result = create_test_case(test_case, config=config)
        results.append({
            "sequence": index,
            "source_id": _safe(test_case.get("ID")),
            "title": _safe(test_case.get("Title")),
            "azure_id": result.get("id"),
            "url": result.get("_links", {}).get("html", {}).get("href", ""),
        })
    return results


def preview_test_case(test_case: dict[str, Any]) -> dict[str, Any]:
    """
    Modo seguro: no realiza llamadas de red.
    Permite revisar exactamente qué se enviaría a Azure.
    """
    return {
        "title": _safe(test_case.get("Title")),
        "description_html": build_description_html(test_case),
        "steps_xml": build_steps_xml(test_case),
        "patch": build_test_case_patch(test_case),
    }
