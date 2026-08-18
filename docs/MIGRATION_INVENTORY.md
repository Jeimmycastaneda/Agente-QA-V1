# Inventario de main usado para la reorganización

Archivos detectados en main:
- app.py
- azure_config.txt
- azure_devops.py
- azure_template_headers.txt
- editor_azure.py
- prompt_qa.txt
- requirements.txt

Destinos propuestos:
- app.py -> app.py + agente_qa/ui/*
- editor_azure.py -> agente_qa/ui/editor.py
- azure_devops.py -> agente_qa/integrations/azure_devops.py
- prompt_qa.txt -> prompts/qa_base.md
- azure_config.txt -> config/azure_devops.yaml
- azure_template_headers.txt -> config/columns.yaml
- requirements.txt -> requirements.txt / requirements-dev.txt

Nota:
La migración 1:1 del app.py de 130 KB debe hacerse por bloques y validarse con
pruebas para no perder comportamiento. Esta entrega NO afirma que sea todavía
equivalente funcional al main completo.
