# Arquitectura propuesta — arquitectura-main-v2

## Principio

La rama se construye desde `main`, no desde `mao-dev-branch`.

- `app.py`: punto de entrada Streamlit.
- `ui/`: interfaz.
- `core/`: reglas y validaciones QA.
- `providers/`: Gemini.
- `extraction/`: documentos.
- `export/`: Excel/PDF.
- `integrations/`: Azure DevOps.
- `config/`: configuración.
- `prompts/`: prompt.
- `tests/`: pruebas.

## Flujo

Streamlit → extracción → core QA → Gemini → validación/cobertura → editor → Excel/PDF → Azure.

## Regla de seguridad

Esta arquitectura es experimental. No hacer merge a `main` hasta validar regresión funcional.

## Importante

Los archivos grandes de `main` requieren una migración por bloques para evitar perder
funciones existentes. Por eso esta primera entrega separa los contratos críticos y
deja puntos de integración claros. No debe considerarse todavía una sustitución
automática 1:1 del `app.py` monolítico.
