# Agente QA — arquitectura-main-v2

Rama experimental para reorganizar el Agente QA sin tocar `main` ni `mao-dev-branch`.

## Ejecución Streamlit

```bash
streamlit run app.py
```

## Estado

Esta entrega contiene la arquitectura y la separación de responsabilidades, con
módulos funcionales extraídos de los componentes críticos de `main`.

Antes de usarla como reemplazo de producción hay que completar la migración 1:1 del
`app.py` monolítico, especialmente UI Azure, PDF completo y todas las funciones
auxiliares de generación/exportación.

No hacer merge hasta pasar pruebas de regresión.
