# Agente QA V1

Mini aplicación web para analizar Historias de Usuario y documentos asociados con Gemini, revisar/editar casos de prueba y exportar Excel/PDF.

## Archivos
- app.py — entrypoint de Streamlit
- agente_qa/ — lógica de la app (config, extracción, generación, export, UI)
- prompts/ — prompts QA en Markdown, editables desde la interfaz
- requirements.txt

## Configuración
La clave `GEMINI_API_KEY` debe guardarse como Secret en Streamlit Cloud. Nunca debe subirse a GitHub.
