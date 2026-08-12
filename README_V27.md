# Agente QA V27 — Azure Real

Paquete completo actualizado sobre la aplicación con editor tipo Azure.

## Cambios de esta versión

- Se elimina completamente la interfaz de referencias históricas.
- Se elimina el contexto de referencias históricas del prompt enviado a Gemini.
- Se mantiene el editor tipo Azure y eliminación de CP.
- Se agrega validación de cobertura: mínimo un CP por cada CU y un único CU por CP.
- Azure Import usa exactamente las 11 columnas de la plantilla exportada desde Azure:
  ID, Work Item Type, Title, Test Step, Step Action, Step Expected, Area Path, IDPadre, Tiempo Real, Assigned To, State.
- Para CP nuevos: ID vacío, IDPadre vacío, Tiempo Real vacío y State=Design.
- No se agrega Tipo Origen Proyecto.
- Producto: Cotizadores Web.
- Módulo: Cotizador Autos Colectivos.

## Archivos

- app.py
- editor_azure.py
- prompt_qa.txt
- azure_config.txt
- azure_template_headers.txt
- requirements.txt
