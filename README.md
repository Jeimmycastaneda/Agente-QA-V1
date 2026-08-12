# Agente QA V23 — Redacción QA

Aplicación Streamlit para analizar Historias de Usuario/documentación con Gemini, generar casos de prueba funcionales, editarlos con una experiencia tipo Azure y exportar Excel/PDF.

## V23

Esta versión elimina por completo la carga/campo de "Referencias históricas QA" de la interfaz y de la lógica de generación.

Los proyectos históricos sirven únicamente como estándar interno de calidad de redacción definido en `prompt_qa.txt`. No se cargan desde la interfaz ni se envían a Gemini como contexto adicional.

### Reglas principales

- Mínimo 1 CP por cada CU.
- 1 CP = 1 CU.
- No mezclar funcionalidades.
- Escenarios adicionales solo cuando estén sustentados.
- Description contextual y específica.
- Expected verificable.
- Steps atómicos y ejecutables.
- Action y Expected separados.
- No invención.
- Producto para Autos Colectivos: `Cotizadores Web`.
- Módulo: `Cotizador Autos Colectivos`.
- Editor de casos con experiencia tipo Azure.
- Eliminación de CP disponible.
- Excel/PDF conservan la estructura aprobada.

## Archivos

- `app.py`
- `editor_azure.py`
- `prompt_qa.txt`
- `requirements.txt`
- `README.md`

## Configuración

La clave `GEMINI_API_KEY` debe guardarse como Secret en Streamlit Cloud. Nunca debe subirse a GitHub.
