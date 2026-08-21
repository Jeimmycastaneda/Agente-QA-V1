# 🤖 Agente QA

Agente especializado en analizar Historias de Usuario (HU), Casos de Uso, Criterios de Aceptación y reglas funcionales para generar **Casos de Prueba (CP) funcionales en versión DRAFT**, con trazabilidad y validaciones orientadas a QA.

> **Estado:** MVP / evolución activa.

## 🎯 Objetivo

El Agente QA busca convertir documentación funcional en casos de prueba estructurados, revisables y preparados para su gestión en Azure DevOps, evitando inventar información que no esté sustentada por la fuente.

El flujo actual mantiene:

```text
Documento funcional
       ↓
    Streamlit
       ↓
      Gemini
       ↓
Análisis QA + reglas
       ↓
 Casos de Prueba
   ↙      ↓       ↘
Editor   Excel     PDF
             ↓
       Azure DevOps
```

## 🧠 Componentes principales

### Streamlit

Es la interfaz de la aplicación. Permite cargar documentación, ejecutar la generación, revisar los CP y trabajar con las salidas generadas.

### Gemini

Es el **cerebro de IA** del agente. Analiza la documentación siguiendo el prompt QA y genera la estructura de Casos de Prueba.

### Motor QA

La lógica funcional debe garantizar, entre otras reglas:

- usar únicamente información disponible en la documentación;
- **no inventar** datos funcionales;
- generar alertas cuando falte información;
- conservar contradicciones de la fuente y alertarlas;
- mantener trazabilidad entre HU, CU, criterios y CP;
- generar como mínimo **1 CP por Caso de Uso**;
- mantener **1 Caso de Uso relacionado por CP**;
- cuando una misma funcionalidad tenga dos o más tipos de cotización con reglas, cálculos, condiciones o comportamientos diferenciados, generar **CP independientes por cada tipo** y validar cada escenario de forma completa.

## 🧪 Estructura de un Caso de Prueba

Los CP utilizan la estructura funcional definida para el proyecto, incluyendo información como:

- ID del CP;
- Producto;
- Módulo;
- Descripción;
- Resultado esperado de la prueba;
- Precondiciones;
- Caso de uso relacionado;
- Steps con **Steps / Action / Expected**;
- alertas y trazabilidad cuando corresponda.

El formato de identificación utilizado para Autos Colectivos sigue el patrón:

```text
CP-AC-<MÓDULO>-#####
```

## 📊 Exportaciones

La aplicación contempla generación de:

- **Excel** compatible con el flujo de importación de Azure DevOps y con la **Matriz QA** aprobada.
- **PDF** para revisión/consulta de los casos generados.

Se debe conservar el modelo aprobado de columnas y títulos; cualquier cambio estructural debe validarse antes de incorporarse.

## ☁️ Azure DevOps

El proyecto está evolucionando para permitir la creación y sincronización de Test Cases en Azure DevOps.

La integración contempla trabajar con:

- Test Plans;
- Suites;
- Test Cases;
- Parent asociado a la Suite seleccionada;
- Related Work asociado al Caso de Uso;
- Steps nativos de Azure DevOps;
- descripción estructurada.

La integración debe permanecer protegida y **deshabilitada por defecto** hasta configurar las credenciales necesarias.

## 📁 Estructura actual del repositorio

La rama `main` contiene actualmente una aplicación Streamlit que concentra buena parte de la lógica en `app.py`. Los módulos de edición, integración con Azure DevOps, prompt y configuración ya viven en su ubicación de módulo funcional (no hay copias duplicadas en la raíz):

```text
Agente-QA-V1/
│
├── app.py                          # Punto de entrada y lógica principal actual
├── agente_qa/ui/editor_azure.py    # Editor de CP con estructura tipo Azure
├── agente_qa/integrations/azure_devops.py  # Integración/conector Azure DevOps
├── prompts/prompt_qa.txt           # Prompt QA / reglas del agente
├── config/azure_config.txt         # Configuración relacionada con Azure
├── config/azure_template_headers.txt
├── requirements.txt                # Dependencias Python
└── README.md
```

La arquitectura futura se está reorganizando en una rama aislada para separar responsabilidades sin comprometer `main`.

## 🏗️ Arquitectura objetivo

La evolución propuesta separa la aplicación en capas:

```text
app.py
  │
  ├── agente_qa/ui/             → Streamlit / interfaz
  ├── agente_qa/core/           → reglas, validación y cobertura QA
  ├── agente_qa/providers/      → Gemini
  ├── agente_qa/extraction/     → PDF/DOCX/TXT/XLSX/CSV
  ├── agente_qa/export/         → Excel/PDF
  └── agente_qa/integrations/   → Azure DevOps

config/                         → configuración
prompts/                        → prompts
tests/                          → pruebas automatizadas
docs/                           → documentación
.streamlit/                     → configuración Streamlit
```

Esta reorganización se está realizando en:

```text
arquitectura-main-v2
```

sin modificar `main` ni `mao-dev-branch` hasta completar las pruebas y obtener aprobación.

## 🚀 Instalación local

Clonar el repositorio y crear un entorno virtual:

```bash
python -m venv .venv
```

Activar el entorno en Windows:

```bash
.venv\Scripts\activate
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

## ▶️ Ejecutar la aplicación

Desde la raíz del proyecto:

```bash
streamlit run app.py
```

La aplicación utiliza Streamlit como interfaz web local.

## 🔐 Variables / secretos

Las credenciales y secretos **no deben guardarse en el repositorio**.

Para Gemini se utiliza la clave de API mediante configuración segura de Streamlit o variable de entorno.

Para Azure DevOps se utilizan credenciales mediante configuración segura.

El conector Azure debe permanecer deshabilitado hasta que exista configuración válida.

## 🛡️ Principios del proyecto

1. **No inventar información funcional.**
2. **Trazabilidad completa.**
3. **Alertar información faltante o contradictoria.**
4. **Conservar la estructura aprobada de Excel/PDF.**
5. **No modificar títulos de columnas sin aprobación.**
6. **Separar la lógica QA de la interfaz.**
7. **Mantener Gemini como cerebro del agente.**
8. **Mantener Streamlit como interfaz.**
9. **Proteger las ramas estables.**
10. **Probar la nueva arquitectura antes de hacer merge.**

## 🌿 Ramas de trabajo

| Rama | Propósito |
|---|---|
| `main` | Rama principal / versión estable actual |
| `mao-dev-branch` | Rama de referencia/desarrollo existente |
| `arquitectura-main-v2` | Reorganización experimental de la arquitectura de `main` |

**Regla:** `main` y `mao-dev-branch` no deben modificarse como parte del trabajo experimental de arquitectura.

## 📚 Próximos pasos

- Completar la migración 1:1 del `app.py` monolítico hacia módulos.
- Mantener las reglas actuales del prompt QA.
- Validar generación y cobertura de CP.
- Validar Excel y Matriz QA.
- Validar PDF.
- Validar editor.
- Validar conexión con Azure DevOps.
- Validar Parent/Suite y Related Work/CU.
- Ejecutar pruebas de regresión.
- Revisar la arquitectura antes de cualquier merge a `main`.

---

**Agente QA — proyecto en evolución**
