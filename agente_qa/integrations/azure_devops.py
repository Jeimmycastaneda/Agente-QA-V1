"""Cliente REST artesanal de Azure DevOps (Fase 5).

Sin SDK oficial (`azure-devops`): solo unos pocos endpoints hacen falta y el
SDK generado arrastra un árbol de dependencias grande para eso. Auth vía HTTP
Basic con usuario vacío y el PAT como password. El export a Excel/PDF
(`export/excel.py`, `export/pdf.py`) no se toca -- este módulo es puramente
aditivo.

Todo mensaje de error que se propaga hacia arriba pasa por
`agente_qa.security.redact` antes de guardarse en `detail`: el PAT nunca se
loguea ni se muestra, ni siquiera en el detalle técnico.

Split 5a/5b (ver docs/plans/roadmap-implementation-plan.md Fase 5 -- corrige
la redacción de docs/context.md §5, "crear Test Points directamente" no es
posible vía API):
- **5a** (implementado, prioritario): crear/actualizar Test Cases. Idempotente
  vía `AzureWorkItemId` en el caso (misma sesión) + búsqueda WIQL por título
  como fallback entre sesiones. `dry_run=True` por defecto: sin llamadas de
  escritura (create/update) contra la API.
- **5b** (`add_to_test_suite`): asociar un Test Case ya creado a una Test
  Suite dentro de un Test Plan -- es la única forma real de que Azure DevOps
  materialice un Test Point. La columna `TestPointId` que sintetiza
  `export/excel.py` es un artefacto del formato de import Excel, no un id
  real de Azure DevOps.
"""

import html
from dataclasses import dataclass

import requests

from agente_qa.errors import IntegrationError, TransientError
from agente_qa.security import redact
from agente_qa.settings import AzureDevOpsConfig
from agente_qa.utils import build_case_title, normalize_case_id, safe_steps, safe_text

_WORK_ITEM_TYPE = "Test Case"


@dataclass(frozen=True)
class PushResult:
    created: list  # list[int]: ids de work items creados
    updated: list  # list[int]: ids de work items actualizados
    skipped: list  # list[str]: descripción de casos omitidos (p. ej. sin título)
    failed: list  # list[tuple[str, str]]: (título del caso, razón segura para el usuario)


def _steps_to_xml(steps: list) -> str:
    """Construye el blob XML de `Microsoft.VSTS.TCM.Steps`.

    Sin dependencia de red -- testeable directamente contra fixtures de
    string. Cada acción/resultado esperado se envuelve en `<DIV>...</DIV>`
    (como el editor web de Test Cases) y esa combinación se HTML-escapa una
    sola vez, así los `<`/`>` literales del wrapper y cualquier carácter
    especial del contenido del usuario terminan como entidades válidas
    dentro del XML.
    """
    if not steps:
        steps = [
            {
                "Action": "Información insuficiente para definir el paso.",
                "Expected value": "Validar con el equipo funcional antes de ejecutar.",
            }
        ]

    step_nodes = []
    for i, step in enumerate(steps, start=1):
        action_html = html.escape(f"<DIV>{safe_text(step.get('Action'))}</DIV>")
        expected_html = html.escape(f"<DIV>{safe_text(step.get('Expected value'))}</DIV>")
        step_nodes.append(
            f'<step id="{i}" type="ActionStep">'
            f'<parameterizedString isformatted="true">{action_html}</parameterizedString>'
            f'<parameterizedString isformatted="true">{expected_html}</parameterizedString>'
            "<description/>"
            "</step>"
        )

    return f'<steps id="0" last="{len(steps)}">' + "".join(step_nodes) + "</steps>"


class AzureDevOpsClient:
    """Cliente HTTP delgado sobre la API REST de Azure DevOps (Work Items + Test Plans)."""

    def __init__(self, config: AzureDevOpsConfig, pat: str, *, session=None, timeout: int = 30):
        self.config = config
        self.timeout = timeout
        self.session = session if session is not None else requests.Session()
        # HTTP Basic con usuario vacío y el PAT como password -- convención
        # estándar de Azure DevOps para auth por PAT.
        self.session.auth = ("", pat)
        self._base = config.organization_url.rstrip("/")

    def _project_base(self) -> str:
        return f"{self._base}/{self.config.project}"

    def _raise_for_response(self, response, *, user_message: str):
        status = getattr(response, "status_code", 200)

        if status == 429:
            retry_after = None
            headers = getattr(response, "headers", None)
            if headers:
                retry_after = headers.get("Retry-After")
            raise TransientError(
                user_message=(
                    "Azure DevOps aplicó rate limiting. Espera unos segundos e intenta de nuevo."
                ),
                detail=redact(
                    f"429 Too Many Requests; Retry-After={retry_after!r}; "
                    f"body={getattr(response, 'text', '')[:500]}"
                ),
            )

        if status >= 400:
            raise IntegrationError(
                user_message,
                detail=redact(f"HTTP {status}: {getattr(response, 'text', '')[:500]}"),
            )

    def check_connection(self) -> dict:
        """`GET {org}/_apis/projects/{project}` -- valida URL/proyecto/PAT antes de cualquier push."""
        url = f"{self._base}/_apis/projects/{self.config.project}?api-version={self.config.api_version}"
        try:
            response = self.session.get(url, timeout=self.timeout)
        except requests.RequestException as exc:
            raise IntegrationError(
                "No se pudo conectar con Azure DevOps. Verifica la URL de la organización y la red.",
                detail=redact(str(exc)),
            ) from exc

        self._raise_for_response(
            response,
            user_message=(
                "No se pudo verificar el proyecto de Azure DevOps. "
                "Revisa organization_url, project y el PAT configurado."
            ),
        )
        return response.json()

    def find_test_case_by_title(self, title: str) -> int | None:
        """WIQL: busca un Test Case existente por título exacto. Devuelve el primer id o None."""
        url = f"{self._project_base()}/_apis/wit/wiql?api-version={self.config.api_version}"
        escaped_title = title.replace("'", "''")
        wiql = {
            "query": (
                "SELECT [System.Id] FROM WorkItems WHERE "
                f"[System.WorkItemType] = '{_WORK_ITEM_TYPE}' "
                f"AND [System.Title] = '{escaped_title}'"
            )
        }
        try:
            response = self.session.post(url, json=wiql, timeout=self.timeout)
        except requests.RequestException as exc:
            raise IntegrationError(
                "No se pudo buscar el caso de prueba en Azure DevOps.",
                detail=redact(str(exc)),
            ) from exc

        self._raise_for_response(
            response, user_message="No se pudo buscar el caso de prueba en Azure DevOps."
        )
        data = response.json()
        work_items = data.get("workItems") or []
        if not work_items:
            return None
        return work_items[0].get("id")

    def _build_create_patch(self, case: dict, title: str) -> list:
        ops = [
            {"op": "add", "path": "/fields/System.Title", "value": title},
            {"op": "add", "path": "/fields/Microsoft.VSTS.TCM.Steps", "value": _steps_to_xml(safe_steps(case))},
        ]
        if self.config.area_path:
            ops.append({"op": "add", "path": "/fields/System.AreaPath", "value": self.config.area_path})
        if self.config.iteration_path:
            ops.append(
                {"op": "add", "path": "/fields/System.IterationPath", "value": self.config.iteration_path}
            )
        return ops

    def create_test_case(self, case: dict, preset: dict) -> int:
        """`POST {org}/{project}/_apis/wit/workitems/$Test%20Case` con un documento JSON-Patch."""
        url = (
            f"{self._project_base()}/_apis/wit/workitems/$Test%20Case"
            f"?api-version={self.config.api_version}"
        )
        module = safe_text(case.get("Module"), "GENERAL")
        case_id = normalize_case_id(case.get("ID"), module, 1, preset.get("title_prefix", ""))
        title = build_case_title(case, case_id)
        ops = self._build_create_patch(case, title)

        try:
            response = self.session.post(
                url,
                json=ops,
                headers={"Content-Type": "application/json-patch+json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise IntegrationError(
                "No se pudo crear el caso de prueba en Azure DevOps.",
                detail=redact(str(exc)),
            ) from exc

        self._raise_for_response(
            response, user_message="No se pudo crear el caso de prueba en Azure DevOps."
        )
        return response.json()["id"]

    def update_test_case(self, work_item_id: int, case: dict) -> int:
        """`PATCH {org}/{project}/_apis/wit/workitems/{id}` con un documento JSON-Patch."""
        url = (
            f"{self._project_base()}/_apis/wit/workitems/{work_item_id}"
            f"?api-version={self.config.api_version}"
        )
        title = build_case_title(case, safe_text(case.get("ID"), f"CP-{work_item_id}"))
        ops = [
            {"op": "replace", "path": "/fields/System.Title", "value": title},
            {
                "op": "replace",
                "path": "/fields/Microsoft.VSTS.TCM.Steps",
                "value": _steps_to_xml(safe_steps(case)),
            },
        ]

        try:
            response = self.session.patch(
                url,
                json=ops,
                headers={"Content-Type": "application/json-patch+json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise IntegrationError(
                "No se pudo actualizar el caso de prueba en Azure DevOps.",
                detail=redact(str(exc)),
            ) from exc

        self._raise_for_response(
            response, user_message="No se pudo actualizar el caso de prueba en Azure DevOps."
        )
        return response.json()["id"]

    def add_to_test_suite(self, work_item_id: int) -> None:
        """Fase 5b: asocia un Test Case ya creado a la Test Suite configurada.

        Esta asociación es lo único que materializa un Test Point real en
        Azure DevOps -- no son creables directamente vía API. Requiere
        `test_plan_id`/`test_suite_id` seteados en la config.
        """
        if not self.config.test_plan_id or not self.config.test_suite_id:
            raise IntegrationError(
                "No se configuró test_plan_id/test_suite_id para asociar el caso a una suite.",
                detail=(
                    "add_to_test_suite called without test_plan_id/test_suite_id "
                    "in AzureDevOpsConfig"
                ),
            )

        url = (
            f"{self._project_base()}/_apis/testplan/Plans/{self.config.test_plan_id}"
            f"/Suites/{self.config.test_suite_id}/TestCase?api-version={self.config.api_version}"
        )
        body = [{"workItem": {"id": work_item_id}}]

        try:
            response = self.session.post(url, json=body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise IntegrationError(
                "No se pudo asociar el caso de prueba a la Test Suite.",
                detail=redact(str(exc)),
            ) from exc

        self._raise_for_response(
            response, user_message="No se pudo asociar el caso de prueba a la Test Suite."
        )

    def push_test_cases(
        self,
        result_json: dict,
        preset: dict,
        *,
        dry_run: bool = True,
        on_progress=None,
        skip_title_match: bool = False,
    ) -> PushResult:
        """Crea/actualiza los `TEST_CASES` de `result_json` en Azure DevOps.

        Idempotencia: si un caso ya tiene `AzureWorkItemId` (escrito por un
        push anterior en la misma sesión), se actualiza; si no, se busca por
        título vía WIQL (fallback entre sesiones) y se actualiza si se
        encuentra, o se crea si no. `skip_title_match=True` (checkbox
        "Crear como nuevos" en la UI) salta la búsqueda por título y siempre
        crea -- útil para forzar duplicados a propósito.

        `dry_run=True` (default) no hace NINGUNA llamada de red: solo
        clasifica cada caso como "create"/"update" a partir de si ya trae
        `AzureWorkItemId`, y lo reporta vía `on_progress`. El matching por
        título es débil (dos casos distintos pueden compartir título) y no
        se resuelve en dry-run -- se declara esta limitación, no se esconde.

        `on_progress(index, total, title, action)` se llama por cada caso
        procesado, con `action` en {"create", "update", "fail"}.
        """
        created: list = []
        updated: list = []
        skipped: list = []
        failed: list = []

        cases = result_json.get("TEST_CASES", []) if isinstance(result_json, dict) else []
        total = len(cases)

        for idx, case in enumerate(cases, start=1):
            module = safe_text(case.get("Module"), "GENERAL")
            case_id = normalize_case_id(case.get("ID"), module, idx, preset.get("title_prefix", ""))
            title = build_case_title(case, case_id)

            if not title.strip():
                skipped.append(f"caso #{idx}: sin título válido")
                continue

            existing_id = case.get("AzureWorkItemId")

            if dry_run:
                if existing_id:
                    updated.append(int(existing_id))
                    action = "update"
                else:
                    created.append(0)
                    action = "create"
                if on_progress:
                    on_progress(idx, total, title, action)
                continue

            try:
                if existing_id:
                    work_item_id = self.update_test_case(int(existing_id), case)
                    case["AzureWorkItemId"] = work_item_id
                    updated.append(work_item_id)
                    if on_progress:
                        on_progress(idx, total, title, "update")
                    continue

                found_id = None if skip_title_match else self.find_test_case_by_title(title)
                if found_id:
                    work_item_id = self.update_test_case(found_id, case)
                    case["AzureWorkItemId"] = work_item_id
                    updated.append(work_item_id)
                    if on_progress:
                        on_progress(idx, total, title, "update")
                else:
                    work_item_id = self.create_test_case(case, preset)
                    case["AzureWorkItemId"] = work_item_id
                    created.append(work_item_id)
                    if on_progress:
                        on_progress(idx, total, title, "create")
            except IntegrationError as exc:
                failed.append((title, exc.user_message))
                if on_progress:
                    on_progress(idx, total, title, "fail")

        return PushResult(created=created, updated=updated, skipped=skipped, failed=failed)
