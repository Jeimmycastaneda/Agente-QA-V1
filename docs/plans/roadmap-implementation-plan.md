# Plan de implementación — Roadmap Agente QA (6 puntos)

Diseñado con el agente `system-architect` a partir del estado real del repo (auditado con un agente Explore y verificado manualmente contra `config.py`, `generation.py`, `providers/gemini.py`, `utils.py`, `ui/document.py`, `ui/generation_section.py`, `ui/state.py`, `prompts.py`).

Este documento cubre los 6 puntos de "Estado deseado" en `docs/context.md`. Al completar una fase, mover el punto correspondiente de "deseado" a "actual" en ese archivo (ver su sección "Cómo usar este documento").

## 0. Overview y secuenciación

### Correcciones a la dependencia asumida

- **El punto 6 no va "antes" de la extracción de `EXCEL_CONFIGS` del punto 2 — *es* esa extracción.** `docs/context.md` §2 explícitamente la delega a §6. Tratarlos como un solo paquete de trabajo, no dos.
- **El punto 3 (interfaz de proveedor) no bloquea al punto 5 (Azure DevOps).** No comparten nada salvo el resolver de credenciales, que pertenece al punto 1. El bloqueante real del punto 5 es el punto 1, no el 3.
- **Los tests (punto 2) deben ir temprano, no al final.** Los puntos 3 y 6 son refactors de los dos paths más sensibles del código (la llamada al LLM, la salida a Excel). Hacerlos sin un golden test sobre `create_excel` deja el contrato de `AZURE_COLUMNS` protegido solo por revisión manual.
- **Hay un prerequisito no listado en el roadmap: el core no es testeable hoy.** `generation.py`, `providers/gemini.py` y `prompts.py` importan Streamlit y tocan `st.session_state`/`st.cache_data`. Todas las fases siguientes dependen de sacar esa dependencia del core.

### Orden recomendado

| Fase | Contenido | Punto del roadmap | Por qué aquí |
|---|---|---|---|
| 1 | Seguridad + sacar Streamlit del core + validación de upload + resolver de credenciales | 1 | Barato, visible para el usuario, y desbloquea que el resto sea testeable. |
| 2 | Harness de pytest + golden tests de Excel/utils/extraction | 2 | Red de seguridad que debe existir antes de que las fases 3–5 toquen export y generación. |
| 3 | Externalización de config YAML (`EXCEL_CONFIGS`, columnas) | 6 + 2 | Protegida por los golden tests de la fase 2. Entrega el archivo de config que las fases 4 y 5 extienden. |
| 4 | Interfaz de proveedor + registro + port de Gemini | 3 | Depende de la fase 1 (errores tipados) y la fase 3 (archivo de config para declarar proveedores). |
| 5 | `integrations/azure_devops.py` (5a crear/actualizar, 5b asociación a suite) | 5 + 2 | La más grande y riesgosa; se beneficia de las cuatro fases previas. |
| 6 | Historial de prompts + preview Markdown | 4 | Opcional, aislado, sin dependientes. Al final. |

Cada fase es independientemente entregable y revertible. No iniciar una fase antes de que los tests de la anterior estén en verde.

### Código muerto detectado (borrar en fase 1)

- `config.MODEL` — no se importa en ningún lado.
- `providers.gemini.is_gemini_3x` — no se llama.
- `providers.gemini.get_valid_models` — no se llama hoy (el sidebar usa `FALLBACK_MODELS` directo), pero **se mantiene**: la fase 4 la conecta al selector de modelo.
- `st.session_state.quota_exceeded` / `retry_count` — se escriben en `generation.py:107-108,135-136`, nunca se leen, no están en `ui/state.py:_DEFAULTS`.

---

## Fase 1 — Punto 1: Seguridad

### 1.1 Taxonomía de errores (archivo nuevo)

`agente_qa/errors.py`:

```python
class AgenteQAError(Exception):
    """user_message es seguro de mostrar; detail es solo para logs."""
    def __init__(self, user_message: str, *, detail: str = "", code: str = ""): ...
    user_message: str
    detail: str
    code: str

class SourceError(AgenteQAError): ...        # upload/extraction
class ConfigError(AgenteQAError): ...        # fase 3
class ProviderError(AgenteQAError): ...      # base fase 4
class QuotaError(ProviderError): ...
class TransientError(ProviderError): ...     # 5xx / timeout / 429-con-retry-after
class BadRequestError(ProviderError): ...
class IntegrationError(AgenteQAError): ...   # fase 5
```

Nombrar la clase reintentable `TransientError`, no `RetryableProviderError` — la fase 5 la reutiliza para 429/503 de Azure DevOps.

### 1.2 Manejo de upload y secretos (archivos nuevos)

`agente_qa/security.py`:

```python
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = ("txt", "md", "pdf", "docx")

def validate_upload(name: str, data: bytes) -> str
    """Devuelve la extensión normalizada. Lanza SourceError si:
       archivo vacío, > MAX_UPLOAD_BYTES, extensión no permitida,
       mismatch extensión/contenido."""

def sniff_kind(data: bytes) -> str | None
    """b'%PDF-' -> 'pdf'; b'PK\\x03\\x04' + zip contiene 'word/document.xml' -> 'docx';
       decodable como utf-8/cp1252 y sin bytes NUL -> 'text'; si no, None."""

def redact(text: str) -> str
    """Enmascara tokens con forma de API key/PAT, paths absolutos del filesystem,
       y headers Authorization. Se aplica a todo lo que llegue a un log."""
```

`agente_qa/secrets.py`:

```python
def resolve_secret(name: str, default: str = "") -> str
    """st.secrets (import perezoso, tolerante a secrets.toml ausente)
       -> os.environ -> default. El único path de credenciales sancionado,
       usado hoy por GEMINI_API_KEY y por AZURE_DEVOPS_PAT en la fase 5."""
```

Este es el único lugar donde Streamlit puede aparecer fuera de la capa UI, y es monkeypatcheable en tests.

Agregar también `.streamlit/config.toml` con `[server] maxUploadSize = 10` — defensa en profundidad; el default de Streamlit es 200 MB y el chequeo a nivel app corre solo después de bufferear el archivo completo.

### 1.3 Archivos modificados

**`agente_qa/extraction.py`** — separar la dependencia del objeto Streamlit:

```python
def extract_source_bytes(name: str, data: bytes) -> str   # nuevo: core puro, valida y despacha
def extract_source(uploaded_file) -> str                  # firma sin cambios; wrapper delgado
```

`extract_source_bytes` llama primero a `security.validate_upload`, luego despacha según el tipo *sniffeado*, no la extensión. Todos los `ValueError`/`RuntimeError` se vuelven `SourceError` con mensaje seguro para el usuario y el texto técnico en `detail`.

**`agente_qa/ui/document.py:44`** — reemplazar el leak:

```python
except AgenteQAError as exc:
    st.error(f"❌ {exc.user_message}")
    if config.DEBUG:
        with st.expander("Detalle técnico"):
            st.code(redact(exc.detail))
except Exception:
    logger.exception("extract_source failed")
    st.error("❌ No se pudo procesar el archivo. Revisa el formato e inténtalo de nuevo.")
```

**`agente_qa/ui/generation_section.py:49`** — mismo patrón, con rama específica de cuota: `except QuotaError: st.warning("Cuota del proveedor agotada. Espera unos minutos o cambia de modelo.")`.

**`agente_qa/config.py`** — agregar `DEBUG = os.getenv("AGENTE_QA_DEBUG", "") == "1"`; borrar `MODEL`.

**`agente_qa/generation.py`** — borrar `import streamlit as st` y las cuatro escrituras a `st.session_state`. El `RuntimeError` terminal del loop de retry se vuelve `ProviderError(user_message="No se pudo generar...", detail="\n\n".join(errors[-8:]))`, así el log técnico se conserva pero nunca se auto-renderiza.

**`agente_qa/providers/gemini.py`** — quitar `@st.cache_data` de `get_valid_models`; borrar `is_gemini_3x`.

**`agente_qa/prompts.py`** — reemplazar `@st.cache_data(ttl=3600)` en `load_prompt` por un dict a nivel de módulo `_CACHE: dict[str, str]` más `clear_prompt_cache()`. `save_prompt` y `ui/prompt_editor.py` llaman a la nueva función en vez de `load_prompt.clear()`.

**`agente_qa/ui/document.py`** — bug fix de paso: la re-extracción se activa solo por `uploaded.name` (línea 24), así que un archivo distinto subido con el mismo nombre se ignora silenciosamente. Usar como key `hashlib.sha256(data).hexdigest()` guardado en un nuevo `st.session_state.source_hash` (agregar a `ui/state.py:_DEFAULTS`).

### 1.4 Riesgos

- Borrar las escrituras a `st.session_state` es seguro *solo porque* nada las lee — verificado por grep. Re-verificar antes de borrar.
- `validate_upload` rechazando mismatch de contenido/extensión va a rechazar archivos que antes funcionaban (p. ej. un `.txt` que en realidad es un PDF). Aceptar esto; loguear la razón del rechazo con claridad.
- 10 MB es un valor supuesto. Dejarlo como asunción explícita; revisar si un documento real de cliente lo excede. El truncado a 28.000 caracteres en `generation.py` ya limita lo que llega al LLM de todas formas.

---

## Fase 2 — Punto 2: Suite de tests

### Decisión
`pytest` en la raíz del repo, paquete `tests/`, sin cambiar a layout `src/`, **sin** cobertura de `streamlit.testing.v1.AppTest` sobre `ui/*` en esta fase.

### Alternativas descartadas
- **`unittest` (stdlib, sin dependencias)** — genuinamente válido, pero fixtures/parametrize son justo lo que necesita el golden-file testing de los tres presets de Excel.
- **`AppTest` para la UI ahora** — es la única forma real de testear widgets de Streamlit y funciona. Rechazado para esta fase: es lento, acopla los tests al orden de los widgets, y el valor es bajo mientras `ui/*` sea passthrough delgado. Agregar exactamente un boot-smoke test después de la fase 5.

### Trade-offs
Se gana: red de regresión rápida y sin red sobre el 100% de la lógica no-UI antes de los refactors riesgosos. Se pierde: `ui/*` (~618 líneas, sobre todo `editor.py`) queda sin testear; regresiones ahí se detectan solo con `streamlit run` manual. Aceptado porque `ui/*` no contiene reglas de negocio — el refactor de la fase 1 empuja cualquier regla existente hacia abajo.

### Layout

```
requirements-dev.txt            # pytest, ruff
pyproject.toml                  # [tool.pytest.ini_options] testpaths=["tests"]; [tool.ruff] line-length=100
tests/
  conftest.py                   # fixtures FakeUpload, sample_result
  fixtures/
    sample_result.json          # payload canónico TEST_CASES/ALERTS/COVERAGE
    sample.txt / sample.pdf / sample.docx / not_a_pdf.pdf
    golden/
      autos_colectivos_azure.json
      autos_colectivos_matriz.json
      general_qa_azure.json
      siniestros_fasecolda_azure.json
  test_utils.py
  test_security.py
  test_extraction.py
  test_prompts.py
  test_generation.py
  test_export_excel.py
  test_export_pdf.py
```

`conftest.py`, fixture clave — replica exactamente lo que `extraction.py` consume (`.name`, `.getvalue()`):

```python
class FakeUpload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data
    def getvalue(self) -> bytes:
        return self._data
```

### Los dos tests que importan

```python
# tests/test_export_excel.py
def test_azure_columns_are_frozen():
    """Contrato con el formato de import aprobado de Azure DevOps.
       Si esto falla, el import se rompe silenciosamente al subirlo."""
    assert AZURE_COLUMNS == [
        "TestCaseId", "Title", "TestStep", "StepAction", "StepExpected",
        "TestPointId", "Configuration", "Tester", "Outcome", "Comment",
    ]

@pytest.mark.parametrize("preset", ["Autos Colectivos", "Siniestros Fasecolda", "General QA"])
def test_excel_matches_golden(sample_result, preset):
    df = pd.read_excel(io.BytesIO(create_excel(sample_result, preset)), sheet_name=0)
    assert list(df.columns) == AZURE_COLUMNS
    assert df.fillna("").astype(str).values.tolist() == load_golden(preset, "azure")
```

La aserción de columnas congeladas duplica la constante a propósito. Esa duplicación *es* el test.

`test_export_pdf.py` es solo un smoke test: bytes no vacíos, empieza con `b"%PDF"`. Comparar bytes exactos de ReportLab no es estable entre versiones.

`test_generation.py` usa un objeto proveedor fake; asertar el orden del fallback, que un `BadRequestError` pasa al siguiente candidato sin dormir, y que la cuota dispara backoff — con `sleep` inyectado (ver firma de la fase 4) para que la suite siga siendo rápida.

### Gate
Todo módulo bajo `agente_qa/` salvo `agente_qa/ui/` debe tener al menos un archivo de test. Sin objetivo de porcentaje de cobertura — los porcentajes invitan a inflar tests vacíos.

---

## Fase 3 — Punto 6 (+ parte del punto 2): externalizar config

### Decisión
YAML vía `PyYAML` (`yaml.safe_load`), dos archivos bajo `config/` en `PROJECT_ROOT`, cargados por un nuevo `agente_qa/settings.py`, con los literales Python actuales conservados en `agente_qa/defaults.py` como fallback cuando falta el archivo.

### Alternativas descartadas
- **JSON** — sin dependencia, stdlib. Rechazado: el comentario `# COLUMNAS APROBADAS — NO AGREGAR NI CAMBIAR TÍTULOS` es load-bearing y JSON no soporta comentarios. Estos archivos los va a editar gente no-desarrolladora.
- **TOML (`tomllib` stdlib en 3.11+)** — comentarios, sin dependencia. Muy cerca. Rechazado porque las claves de `EXCEL_CONFIGS` contienen espacios como labels de display; los nombres de tabla TOML para `"Siniestros Fasecolda"` son incómodos, y el equipo no tiene hábito de TOML.
- **Un solo `agente_qa.yaml` combinado** — más simple (un archivo). Rechazado: mezcla un contrato aprobado congelado con una lista de presets libremente editable en una sola superficie editable. Dos archivos hace que "no tocar este" sea estructural, no solo una advertencia en comentario.

### Archivos

`config/columns.yaml`:
```yaml
# CONTRATO APROBADO CON AZURE DEVOPS — NO RENOMBRAR NI REORDENAR.
# El loader falla si azure_columns difiere del default salvo allow_override: true.
version: 1
allow_override: false
azure_columns:
  - TestCaseId
  - Title
  # ... exactamente las 10 actuales, en orden
matriz_columns:
  # ... exactamente las 12 actuales, en orden
```

`config/excel_presets.yaml`:
```yaml
version: 1
presets:
  "Autos Colectivos":
    sheet_name: "Azure Import"
    base_id: 10001
    base_testpoint: 1001
    configuration: "Default configuration"
    tester: ""
    title_prefix: "CP-AC-"
    user_default: "Usuario registrado"
    steps_with_users: true
  # ... los otros dos, valores idénticos a config.py hoy
```

Las claves de preset son a la vez keys del dict y labels del sidebar (`ui/sidebar.py:33`). Deben reproducirse byte a byte.

### `agente_qa/settings.py`

```python
@dataclass(frozen=True)
class ExcelPreset:
    key: str; sheet_name: str; base_id: int; base_testpoint: int
    configuration: str; tester: str; title_prefix: str
    user_default: str; steps_with_users: bool
    def as_dict(self) -> dict: ...

@dataclass(frozen=True)
class ColumnSpec:
    azure: tuple[str, ...]
    matriz: tuple[str, ...]

def load_columns(path: Path | None = None) -> ColumnSpec
def load_excel_presets(path: Path | None = None) -> dict[str, ExcelPreset]
def _validate_preset(raw: dict, key: str) -> ExcelPreset   # lanza ConfigError
```

Reglas de validación al cargar (aquí es donde el loader justifica su costo):
- todas las claves presentes, tipos correctos; claves desconocidas se rechazan (typos en un preset deben fallar ruidosamente, no defaultear en silencio).
- `sheet_name`: no vacío, ≤ 31 caracteres, sin ninguno de `[ ] : * ? / \`. Hoy `export/excel.py:139` trunca en silencio con `[:31]`; mantener el truncado por compatibilidad pero emitir `ConfigError` al cargar para atraparlo antes de que el usuario descargue una hoja con nombre incorrecto.
- `base_id`, `base_testpoint`: enteros positivos.
- `title_prefix`: matchea `^[A-Za-z0-9_-]*$` — se concatena en los IDs de caso.
- `columns.yaml`: si `allow_override` es false y `azure_columns != defaults.AZURE_COLUMNS`, lanzar `ConfigError`. Hard-fail, no warning.

### Pasos de migración (en orden, un commit cada uno)

1. Agregar `PyYAML` a `requirements.txt`.
2. Mover los literales actuales tal cual desde `config.py` a `agente_qa/defaults.py`.
3. Crear `config/columns.yaml` + `config/excel_presets.yaml` con valores idénticos.
4. Agregar `settings.py` **y un test que asegure `{k: p.as_dict() for k, p in load_excel_presets().items()} == defaults.EXCEL_CONFIGS`** — escribir este test antes de borrar nada.
5. Rewire `config.py` para mantener los mismos nombres públicos, provistos por el loader:
   ```python
   _cols = load_columns()
   AZURE_COLUMNS = list(_cols.azure)
   MATRIZ_COLUMNS = list(_cols.matriz)
   EXCEL_CONFIGS = {k: p.as_dict() for k, p in load_excel_presets().items()}
   ```
   `export/excel.py`, `export/pdf.py` y `ui/sidebar.py` quedan **intactos**. Los golden tests de la fase 2 deben seguir pasando sin regenerar nada — ese es el criterio de aceptación de esta fase.

Recomendación: **no** migrar `create_excel(data, config_key)` a `create_excel(data, preset: ExcelPreset)`. El dataclass se justifica en el momento de carga/validación; llevarlo hasta los exporters es churn sin beneficio y forzaría regenerar golden files.

### Bug latente a arreglar en esta fase

`agente_qa/utils.py:97` (`normalize_case_id`):
```python
if re.fullmatch(r"CP-AC-[A-Za-z0-9_-]+-\d{5}", candidate):
```
El regex hardcodea `CP-AC-` mientras la función recibe un parámetro `prefix`. Para `General QA` (`CP-`) y `Siniestros Fasecolda` (`CP-ACSF-`), un ID provisto por el modelo **siempre** se descarta y se regenera. Inofensivo mientras los presets estén hardcodeados y poco auditados; un defecto real una vez que los clientes definan sus propios prefijos. Fix:
```python
if re.fullmatch(rf"{re.escape(prefix)}[A-Za-z0-9_-]+-\d{{5}}", candidate):
```
Esto cambia el output para dos de los tres presets, así que los fixtures golden deben regenerarse **deliberadamente y en un commit separado** del paso 5, con el diff revisado. No dejarlo colarse dentro de la migración de config.

### Rollback
Borrar `config/`, revertir `config.py` para que importe de `defaults.py`. El fallback path implica que un `config/` faltante ya es un estado funcional, así que un deploy parcial degrada al comportamiento actual en vez de romperse.

---

## Fase 4 — Punto 3: multi-proveedor LLM

### Decisión
Un `typing.Protocol` en `agente_qa/providers/base.py` más un registro perezoso por string en `providers/__init__.py`. La *clasificación* de errores se mueve de `generation.py` a cada proveedor; la *política* de retry/fallback se queda en `generation.py`.

### Alternativas descartadas
- **Clase base abstracta (`abc.ABC`)** — fuerza el contrato en la instanciación. Rechazado por poco margen: `Protocol` da el mismo chequeo estático sin forzar herencia, lo cual importa si un futuro proveedor envuelve un objeto de SDK de vendor. Cualquiera de las dos es defendible; se elige Protocol y no se sigue debatiendo.
- **LiteLLM / LangChain como capa de abstracción** — resuelve multi-proveedor con una dependencia, hoy. Rechazado: arrastra un árbol transitivo grande, y la semántica de retry/fallback/quota ya implementada acá (`generation.py:118-159`) habría que re-expresarla en sus idiomas. El proyecto necesita *dos o tres* proveedores, no cuarenta.
- **Mantener la clasificación en `generation.py`** — menos archivos. Rechazado: la lógica actual es sniffing de substrings sobre el texto de error de Gemini (`"429" in detail`, `"resource exhausted"`). Aplicar esos substrings a una excepción de OpenAI o Anthropic es una moneda al aire.

### `agente_qa/providers/base.py`

```python
@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    source: str
    schema: dict
    model: str
    temperature: float = 0.0
    max_output_tokens: int = 32768

@dataclass(frozen=True)
class GenerationResult:
    data: dict          # parseado, independiente del proveedor
    model: str
    raw_text: str

class LLMProvider(Protocol):
    name: str
    def list_models(self) -> list[str]: ...
    def default_models(self) -> list[str]: ...
    def generate(self, request: GenerationRequest) -> GenerationResult: ...
```

Los proveedores lanzan `QuotaError` / `TransientError` / `BadRequestError` de `errors.py`. Gemini conserva un `_classify(exc) -> ProviderError` privado que contiene la lógica de substrings actual, sin cambiar de comportamiento, solo relocalizada.

### `agente_qa/providers/__init__.py`

```python
_REGISTRY = {"gemini": "agente_qa.providers.gemini:GeminiProvider"}

def list_providers() -> list[str]
def build_provider(name: str, api_key: str) -> LLMProvider   # importlib, perezoso
```

Import perezoso por string con dotted path para que un `openai` faltante nunca rompa el arranque de la app.

### `agente_qa/generation.py` (firma reescrita)

```python
def generate_qa_data(
    prompt_text: str,
    source_content: str,
    provider: LLMProvider,
    model_name: str,
    *,
    fallback_models: list[str] | None = None,
    temperature: float = 0.0,
    max_retries: int = 2,
    initial_wait: int = 10,
    max_source_chars: int = 28000,
    sleep=time.sleep,
) -> dict
```

`sleep` se inyecta para que los tests de retry de la fase 2 corran instantáneos. `max_source_chars` se vuelve un valor de config por proveedor — las ventanas de contexto difieren y 28.000 es un supuesto de la era Gemini.

El loop de retry conserva su forma exacta actual pero se ramifica por *tipo* de excepción en vez de substring:

| Excepción | Comportamiento |
|---|---|
| `QuotaError` | backoff `initial_wait * (attempt+1)`, retry hasta `max_retries`, luego siguiente modelo |
| `TransientError` | igual |
| `BadRequestError` | sin retry, siguiente modelo de inmediato |
| `ValueError` de `validate_qa_structure` | sin retry, siguiente modelo |

`validate_qa_structure` se queda en `generation.py` e independiente del proveedor — el enforcement de schema es best-effort por vendor, la validación es nuestra. Su mensaje `"La respuesta de Gemini no es un objeto JSON."` debe des-marcarse (quitar la mención a Gemini).

### `config/providers.yaml`

```yaml
version: 1
default_provider: gemini
providers:
  gemini:
    enabled: true
    secret_name: GEMINI_API_KEY
    default_model: gemini-3.6-flash
    max_source_chars: 28000
    fallback_models:
      - gemini-3.6-flash
      - gemini-3.5-flash-lite
      - gemini-2.5-flash
      - gemini-2.5-pro
```

`settings.py` gana `load_providers() -> dict[str, ProviderConfig]`. `config.FALLBACK_MODELS` pasa a derivarse del proveedor default; mantener el nombre por compatibilidad durante un release.

`ui/sidebar.py` gana un selectbox de proveedor encima del selectbox de modelo, y el label/nombre de secreto del campo de API key sigue al proveedor seleccionado vía `resolve_secret(cfg.secret_name)`. El fallback de password manual se queda — ese patrón es correcto y la fase 5 lo copia.

### La trampa de portabilidad de `SCHEMA`

`config.SCHEMA` hoy se pasa directo a `types.GenerateContentConfig(response_schema=...)`. Es *casi* JSON Schema pero no portable:
- **OpenAI**, en structured outputs estrictos, requiere `additionalProperties: false` en cada objeto y que **todas** las propiedades listadas estén en `required` — el schema actual solo marca 5 de 15 propiedades de `TEST_CASES` como requeridas.
- **Anthropic** lo consume como `input_schema` de una tool, que es la forma más tolerante y la más cercana a lo que ya existe.

**Decisión:** mantener `SCHEMA` como el JSON Schema canónico, plano y permisivo, y darle a cada proveedor un adapter privado `_to_provider_schema(schema)`. **No** deformar el schema canónico para satisfacer al proveedor más estricto. Razón: Gemini funciona hoy con esta forma exacta; endurecer `required` cambiaría el output del modelo por un proveedor que nadie agregó todavía.

### Guardia de alcance
Implementar `base.py`, el registro y el port de Gemini. **No escribir un proveedor de OpenAI o Anthropic en esta fase.** Un proveedor especulativo escrito sin una key real es código no testeado que se pudre; agregarlo cuando alguien lo necesite, con un smoke test en vivo.

### Riesgos
- El port de Gemini es un refactor que debe preservar comportamiento del único path de código que funciona hoy en la app. Los tests de orden de fallback de `test_generation.py` (fase 2) son el gate de aceptación.
- `ProviderConfig.fallback_models` duplicado entre YAML y `defaults.py` puede divergir. Hacer que el loader caiga a `defaults` y testear que coinciden.

---

## Fase 5 — Punto 5: integración con Azure DevOps

### Decisión
Cliente REST artesanal sobre `requests` en `agente_qa/integrations/azure_devops.py`. PAT vía HTTP Basic con usuario vacío, resuelto por `secrets.resolve_secret`. El export a Excel/PDF queda intacto — esto es estrictamente aditivo.

### Alternativas descartadas
- **SDK oficial `azure-devops`** — soportado, tipado. Rechazado: es un cliente generado grande con sus propios pins transitivos, documentación escasa para las áreas WIT/TestPlan, y solo necesitamos unos tres endpoints. El costo de la dependencia supera el beneficio.
- **Generar un CSV/XML nativo de ADO para que el usuario lo importe** — sin credenciales, sin red. Rechazado porque es exactamente lo que la app ya hace con Excel; el punto 5 existe específicamente para eliminar ese paso manual.

### Configuración

`config/azure_devops.yaml`:
```yaml
version: 1
enabled: false
organization_url: "https://dev.azure.com/<org>"
project: ""
area_path: ""
iteration_path: ""
api_version: "7.1"
pat_secret_name: AZURE_DEVOPS_PAT   # NOMBRE del secreto, nunca el valor
test_plan_id: null                  # fase 5b
test_suite_id: null                 # fase 5b
```

**El valor del PAT nunca aparece en YAML.** El loader debe hard-fail con `ConfigError` si el mapeo parseado contiene una clave `pat`, `token` o `password` — una guardia contra el error obvio, y barata.

`organization_url` debe validarse contra `^https://(dev\.azure\.com/|[a-z0-9-]+\.visualstudio\.com)` antes de cualquier request. Un host mal tipeado o inyectado recibiría el PAT en un header `Authorization`. Este es el riesgo de mayor severidad de todo el roadmap.

### `agente_qa/integrations/azure_devops.py`

```python
@dataclass(frozen=True)
class AzureDevOpsConfig:
    organization_url: str; project: str; area_path: str
    iteration_path: str; api_version: str; pat_secret_name: str
    test_plan_id: int | None = None
    test_suite_id: int | None = None

@dataclass(frozen=True)
class PushResult:
    created: list[int]
    updated: list[int]
    skipped: list[str]
    failed: list[tuple[str, str]]     # (título del caso, razón segura para el usuario)

class AzureDevOpsClient:
    def __init__(self, config: AzureDevOpsConfig, pat: str, *, session=None, timeout: int = 30)
    def check_connection(self) -> dict
    def find_test_case_by_title(self, title: str) -> int | None     # WIQL
    def create_test_case(self, case: dict, preset: dict) -> int
    def update_test_case(self, work_item_id: int, case: dict) -> int
    def push_test_cases(self, result_json: dict, preset: dict, *,
                        dry_run: bool = True, on_progress=None) -> PushResult
```

Endpoints usados:
- `GET {org}/_apis/projects/{project}?api-version=7.1` — chequeo de conexión.
- `POST {org}/{project}/_apis/wit/workitems/$Test%20Case?api-version=7.1`, `Content-Type: application/json-patch+json`, lista de operaciones JSON-Patch.
- `PATCH {org}/{project}/_apis/wit/workitems/{id}?api-version=7.1` — actualizar.
- `POST {org}/{project}/_apis/wit/wiql?api-version=7.1` — búsqueda por título.
- Fase 5b: `POST {org}/{project}/_apis/testplan/Plans/{planId}/Suites/{suiteId}/TestCase?api-version=7.1`.

### Corrección a la redacción del roadmap

`docs/context.md` §5 dice "crear/actualizar Test Cases y Test Points directamente". **Los Test Points no son creables directamente vía API.** Se materializan cuando Azure DevOps asocia un Test Case a una Test Suite dentro de un Test Plan. La columna `TestPointId` que sintetiza `export/excel.py:67` (`base_testpoint + idx - 1`) es un artefacto del formato de import, no un id real de ADO.

Split en consecuencia:
- **5a** — crear/actualizar solo Test Cases. Útil de forma independiente. Dry-run por defecto.
- **5b** — asociación a suite (que produce los test points reales). Requiere `test_plan_id`/`test_suite_id`, que varían por cliente y por sprint.

### La parte difícil: el campo Steps

`Microsoft.VSTS.TCM.Steps` es un blob XML, no una lista:

```python
def _steps_to_xml(steps: list[dict]) -> str
    # <steps id="0" last="N">
    #   <step id="2" type="ActionStep">
    #     <parameterizedString isformatted="true">&lt;DIV&gt;...action...&lt;/DIV&gt;</parameterizedString>
    #     <parameterizedString isformatted="true">&lt;DIV&gt;...expected...&lt;/DIV&gt;</parameterizedString>
    #     <description/>
    #   </step>
    # </steps>
```

El contenido debe ir HTML-escapado y envuelto. Esta es la pieza menos documentada y con más probabilidad de error del punto 5 — presupuestar tiempo desproporcionado y testear `_steps_to_xml` directamente contra un fixture de string. No tiene dependencia de red, así que es completamente testeable.

### Idempotencia

Pushear dos veces crea duplicados. Aplicar ambas mitigaciones:
1. Escribir el work item id devuelto en `st.session_state.result_json["TEST_CASES"][i]["AzureWorkItemId"]` — un segundo push en la misma sesión actualiza en vez de crear. Barato y exacto.
2. Búsqueda WIQL por título como fallback entre sesiones, con un checkbox explícito "Crear como nuevos (permitir duplicados)" para override.

El matching por título es débil (`build_case_title` puede producir títulos idénticos para casos distintos). Declarar esa limitación en la UI, no esconderla.

### UI

Nuevo `agente_qa/ui/azure_section.py`:
```python
def render_azure_section(result_json: dict, preset_key: str) -> None
```
Se renderiza desde `app.py` solo cuando `azure_devops.yaml` tiene `enabled: true` **y** el PAT resuelve. Flujo obligatorio: chequeo de conexión → tabla de preview en dry-run de qué se crearía/actualizaría → botón de push explícito. `ui/results.py` no cambia; los botones de descarga de Excel y PDF se quedan exactamente donde están.

### Errores y rate limits
ADO devuelve 429 con `Retry-After`. Mapear a `TransientError` y respetar el header. Nunca loguear el PAT; pasar todo mensaje mostrado por `security.redact`.

### Testing
Monkeypatchear la `session` inyectada con un fake que devuelve respuestas prefabricadas. Sin red en CI. Empezar sin la librería `responses`; agregarla solo si el fake artesanal se vuelve inmanejable.

### Riesgos
- Los nombres de campo de ADO y el tipo de work item requerido (`Test Case` vs. un template de proceso customizado) varían por organización. `check_connection` debería también obtener y validar los tipos de work item disponibles antes del primer push.
- `requests` es una dependencia de runtime nueva. Aceptable e inevitable.
- Sin sandbox: un push malo escribe work items reales en un proyecto real. El dry-run debe ser default on, y el documento debe recomendar un proyecto ADO de prueba para la primera corrida.

---

## Fase 6 — Punto 4: versionado de prompts + preview Markdown (opcional)

### Decisión
Historial de archivos con timestamp bajo `prompts/.history/`, escrito por `save_prompt` antes de sobrescribir. Preview vía `st.tabs` + `st.markdown`. Sin dependencias nuevas.

### Alternativas descartadas
- **Commits de git desde la app** — gratis, historial real, diffable. Rechazado: requiere un repo git en runtime y falla directo en un filesystem de deploy read-only o efímero.
- **Guardar versiones de prompt en SQLite** — queryable, atómico. Rechazado como over-engineering para un directorio de archivos de texto chicos.

### Cambios en `agente_qa/prompts.py`

```python
HISTORY_DIR = PROMPTS_DIR / ".history"
MAX_VERSIONS = 20
_VALID_VERSION = re.compile(r"^\d{8}T\d{6}$")

def save_prompt(name: str, content: str) -> None     # snapshotea el contenido previo antes
def list_prompt_versions(name: str) -> list[str]     # más nuevo primero, solo ids de versión
def read_prompt_version(name: str, version: str) -> str
def restore_prompt_version(name: str, version: str) -> None
def _prune_history(name: str) -> None                # conserva las MAX_VERSIONS más nuevas
```

### Restricción crítica sobre la guardia de path-traversal

`is_valid_prompt_name` (`^[A-Za-z0-9_-]+\.md$`) es lo que impide que el editor in-app escriba fuera de `prompts/`. Los ids de versión introducen un segundo componente de path no confiable y generan presión para relajarla y permitir puntos.

**No relajarla.** El id de versión es un *parámetro separado* validado por su propio regex `_VALID_VERSION`, y el path del historial se construye como `HISTORY_DIR / f"{validated_name[:-3]}.{validated_version}.md"` — nunca concatenando input crudo del usuario. Agregar un test que asegure que `read_prompt_version("qa_base.md", "../../etc/passwd")` lanza excepción.

`list_prompts()` hace glob de `PROMPTS_DIR/"*.md"` no recursivo, así que `.history/` ya queda excluido. Verificar que esto se mantenga si el glob se toca alguna vez.

### Preview Markdown
`st.tabs(["Editar", "Vista previa"])`, el preview renderiza `st.markdown(content)` con `unsafe_allow_html` en su default `False`. El contenido del prompt lo escribe el usuario; renderizarlo como HTML crudo en la app no aporta nada.

### Asunción a verificar
Tanto `save_prompt` (hoy) como la escritura de historial asumen un filesystem escribible. El filesystem de Streamlit Community Cloud es efímero y las ediciones se pierden al reiniciar. Si ese es el destino de deploy, la edición de prompts ya es una feature de alcance de sesión y el historial es cosmético — confirmar el destino antes de invertir esfuerzo acá.

---

## Cross-cutting: riesgos, trampas, documentación

### Trampas específicas de este repo (llevar a cada fase)

1. **`AZURE_COLUMNS` es un contrato, no una elección de nombres.** Coincide con un formato de import ADO aprobado; un rename falla en el momento del *upload*, no en build. Protegido por el test de columnas congeladas (fase 2) y el chequeo `allow_override: false` del loader (fase 3).
2. **`is_valid_prompt_name` es un control de seguridad, no ergonomía de validación.** Cualquier presión para relajarla (fase 6) debe resistirse.
3. **Streamlit en el core bloquea el testing.** Después de la fase 1, solo `agente_qa/ui/*` y `agente_qa/secrets.py` pueden importar `streamlit`. Considerar un test que asegure exactamente eso:
   `assert not any("streamlit" in src for src in non_ui_modules)`.
4. **`SCHEMA` tiene forma de Gemini por accidente.** Mantenerlo canónico, adaptar por proveedor.
5. **`utils.normalize_case_id` hardcodea `CP-AC-`** mientras acepta un argumento `prefix` — se vuelve un defecto real una vez que los presets sean provistos por el usuario (fase 3).
6. **`export/excel.py:139` trunca nombres de hoja a 31 caracteres en silencio.** `"28443;Fase 3 - RENK170 Siniestr"` ya está al límite. Validar al cargar la config.
7. **`ui/document.py` solo re-extrae al cambiar el nombre de archivo** — archivos distintos con el mismo nombre se ignoran silenciosamente (fix en fase 1).
8. **`st.cache_data` en `load_prompt` y `get_valid_models`** cachea entre sesiones con TTL de 3600s; un prompt editado ya depende de un `.clear()` explícito. Reemplazarlo por un dict plano (fase 1) preserva el comportamiento y saca el acoplamiento a Streamlit.

### Obligaciones de documentación (por convención del proyecto)

| Fase | Actualizar |
|---|---|
| 1 | `docs/context.md` §1 deseado → actual. `CLAUDE.md` Architecture: agregar `errors.py`, `security.py`, `secrets.py`. |
| 2 | `docs/context.md` §2, línea "sin tests". `CLAUDE.md` Commands: agregar `pytest`, `ruff`. |
| 3 | `docs/context.md` §6 → actual, §2 tercer bullet resuelto. `CLAUDE.md`: descripción de `config.py` ahora dice "cargado desde `config/*.yaml` vía `settings.py`". |
| 4 | `docs/context.md` §3 → actual. `CLAUDE.md`: sección de providers reescrita. |
| 5 | `docs/context.md` §5 → actual, con la corrección de Test Points registrada. `CLAUDE.md`: nueva entrada `integrations/`, nuevo `AZURE_DEVOPS_PAT` en el párrafo de credenciales. |
| 6 | `docs/context.md` §4 pendientes limpiados. |

### Rollback por fase

| Fase | Rollback |
|---|---|
| 1 | Revertir commit. Sin estado persistido, sin archivos de config, sin cambio de schema. |
| 2 | Borrar `tests/`, `requirements-dev.txt`. Impacto cero en runtime. |
| 3 | Borrar `config/`; `config.py` cae automáticamente a `defaults.py`. Un directorio de config faltante ya es un estado válido. |
| 4 | Revertir; el historial de `providers/gemini.py` conserva la versión pre-refactor. Rollback de mayor riesgo porque es el único path de generación que funciona — no apilar la fase 5 encima hasta que la fase 4 haya corrido en producción un ciclo. |
| 5 | Poner `enabled: false` en `config/azure_devops.yaml`. La sección de UI desaparece; el export Excel/PDF no se afecta porque el punto 5 es puramente aditivo. Sin revert de código necesario. |
| 6 | Borrar `prompts/.history/`; `save_prompt` vuelve a sobrescribir. |

### Escalación — decisiones que este plan no puede tomar

Necesitan input antes de que arranque la fase correspondiente:

- **Valor de `MAX_UPLOAD_BYTES`** (fase 1) — 10 MB es un placeholder. Necesita el documento real más grande de algún cliente.
- **Destino de deploy** (fases 1, 6) — Streamlit Community Cloud vs. self-hosted determina si el filesystem es escribible, lo cual determina si el historial de prompts y la edición de `config/` son features reales o decoración.
- **Cuál segundo proveedor de LLM, y si hay una key disponible** (fase 4) — la interfaz no debería diseñarse contra una hipótesis.
- **Template de proceso de Azure DevOps y un proyecto de prueba** (fase 5) — la disponibilidad de campos de work item varía por organización; el punto 5 no se puede validar sin un proyecto real donde pushear.

---

## Archivos relevantes (rutas absolutas)

- `/home/maosuarez/Programas/Agente-QA-V1/docs/context.md`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/config.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/generation.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/providers/gemini.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/extraction.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/prompts.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/utils.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/export/excel.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/ui/document.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/ui/sidebar.py`
- `/home/maosuarez/Programas/Agente-QA-V1/agente_qa/ui/generation_section.py`

Cada fase es independientemente entregable y revertible. No iniciar una fase antes de que los tests de la anterior estén en verde.
