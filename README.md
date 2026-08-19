# Agente QA — arquitectura-main-v2

Rama de reorganización segura del Agente QA. `main` y `mao-dev-branch` no se modifican desde esta rama.

## Objetivo

Migrar progresivamente la funcionalidad vigente de `main` hacia una arquitectura por responsabilidades, sin perder las reglas QA ni el comportamiento de Azure DevOps.

## Estructura

- `app.py`: orquestador Streamlit.
- `agente_qa/core/`: generación, cobertura, reglas, validación y trazabilidad.
- `agente_qa/extraction/`: extracción de documentos.
- `agente_qa/providers/`: proveedor Gemini.
- `agente_qa/export/`: exportaciones Excel/PDF.
- `agente_qa/integrations/`: conectores externos, incluido Azure DevOps.
- `agente_qa/ui/`: interfaz Streamlit separada por responsabilidades.
- `config/`: configuración de Azure, columnas y proveedores.
- `prompts/`: reglas QA vigentes.
- `docs/`: inventario, arquitectura y estado de migración.
- `tests/`: pruebas de componentes migrados.

## Migración vigente desde main

Se incorporaron a la arquitectura las reglas vigentes del prompt de `main`, el editor Azure con edición de Description/Precondiciones/CU/Steps y la versión endurecida del conector Azure DevOps, incluyendo sanitización de pipes y escapes, separación visual de párrafos y construcción de Steps XML.

La arquitectura conserva además la configuración de `Area Path`, `parent_from_suite` y `related_work_from_use_case` definida para esta rama.

## Seguridad de ramas

Antes de modificar esta rama se creó un respaldo remoto:

`backup/arquitectura-main-v2-before-main-sync-20260819`

Ese respaldo parte exactamente del estado anterior de `arquitectura-main-v2`.

## Estado

Esta rama sigue siendo experimental. No hacer merge a `main` hasta completar la migración funcional 1:1 del `app.py` monolítico y ejecutar pruebas de regresión.

## Ejecución

```bash
streamlit run app.py
```
