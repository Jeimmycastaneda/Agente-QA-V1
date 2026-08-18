# Prompt QA

El archivo de producción `prompt_qa.txt` de main se conserva como fuente de verdad
durante la migración. Esta ubicación será el destino final del prompt.

Reglas esenciales:
- usar únicamente la HU/documentación como fuente;
- no inventar;
- mínimo 1 CP por CU;
- exactamente 1 CU por CP;
- si una misma funcionalidad tiene tipos de cotización con reglas funcionales
  diferentes, generar CP independientes por tipo;
- conservar trazabilidad;
- generar alertas cuando falte información;
- mantener estructura compatible con Excel/Azure.
