# Inventario de `main` — reorganización `arquitectura-main-v2`

## Regla de seguridad

- `main` no se modifica.
- `mao-dev-branch` no se modifica.
- `arquitectura-main-v2` tiene respaldo previo en `backup/arquitectura-main-v2-before-main-sync-20260819`.

## Fuentes de `main`

| Fuente | Destino arquitectónico | Estado |
|---|---|---|
| `app.py` | `app.py` + módulos `core`, `extraction`, `providers`, `export`, `integrations`, `ui` | Migrado por responsabilidades |
| `azure_devops.py` | `agente_qa/integrations/azure_devops.py` | Migrado y consolidado |
| `editor_azure.py` | `agente_qa/ui/editor.py` | Migrado |
| `prompt_qa.txt` | `prompts/qa_base.md` | Migrado como fuente de reglas |
| `azure_config.txt` | `config/azure_devops.yaml` | Migrado |
| `azure_template_headers.txt` | `config/columns.yaml` | Migrado |
| `requirements.txt` | `requirements.txt` | Conservado |

## Funcionalidad organizada

### Extracción
`agente_qa/extraction/document.py` conserva TXT/MD, PDF, DOCX, XLSX/XLS y CSV, incluyendo mensajes de error para dependencias y documentos sin contenido.

### Generación
`agente_qa/providers/gemini.py` encapsula Gemini y JSON estructurado. `agente_qa/core/generation.py` valida la estructura y bloquea resultados que no cubran todos los CU.

### Reglas y trazabilidad
Las reglas de cobertura, un CU por CP y separación de escenarios funcionalmente diferentes viven en `agente_qa/core` y `prompts/qa_base.md`, no en la UI.

### Excel
`agente_qa/export/excel.py` conserva las columnas aprobadas de Azure, una fila de cabecera por CP y filas separadas para Steps, además de `Matriz QA`.

### PDF
`agente_qa/export/pdf.py` genera el Test Plan y el detalle de cada CP con Description, resultado, precondiciones, CU y Steps.

### Azure DevOps
`agente_qa/integrations/azure_devops.py` concentra consultas de Test Plans/Suites/Test Cases, creación de Work Items, Description HTML, Steps XML y asociación a Suite. La UI exige confirmación explícita antes de escribir.

### Editor
`agente_qa/ui/editor.py` mantiene edición de Description, Precondiciones, CU relacionado y tabla de Steps.

## Validación pendiente antes de declarar paridad total

La arquitectura ya contiene los bloques funcionales de `main`, pero la paridad 1:1 debe comprobarse ejecutando la aplicación y sus pruebas en un entorno con las dependencias instaladas. No se debe sustituir el `app.py` arquitectónico por el monolito de `main`.
