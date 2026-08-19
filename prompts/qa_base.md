# Prompt QA — reglas vigentes migradas desde main

## 1. Cobertura obligatoria de todos los CU
Antes de generar CP identifica todos los CU presentes en la documentación y construye internamente la relación CU → CP. La generación solo es válida cuando cada CU tiene mínimo un CP, cada CP tiene exactamente un CU relacionado, ningún CU queda sin CP y ningún CP queda sin CU válido. Nunca entregues una generación parcial como válida.

## 2. Matriz interna antes de generar
1. Identificar CU.
2. Identificar nombre de cada CU.
3. Crear una fila por CU.
4. Asignar mínimo un CP a cada CU.
5. Identificar si necesita más de un CP por diferencia funcional.
6. Generar los CP.
7. Auditar nuevamente CU → CP.

## 3. Un solo CU por CP
Cada CP debe tener exactamente `Related Use Case: CU-XXX - Nombre exacto del CU`. Si una prueba requiere dos CU diferentes, dividirla en dos CP.

## 4. Título
Formato: `CP-[INICIALES_MODULO][INICIALES_SUITE]-##### [DESCRIPCIÓN]`. Para Autos Colectivos el módulo es `AC`. El título debe ser descriptivo y no genérico. No usar pipes.

## 5. Description de nivel QA
Debe permitir ejecutar la prueba sin reinterpretar el CU e incluir, cuando estén documentados, perfil, punto de entrada, ruta, módulo, icono, menú, opción, estado, archivo, hoja, sección, subsección, tabla, filas, columnas, productos, coberturas, orden, parametrizaciones, reglas, cálculos, fuentes, condiciones, excepciones, homologaciones, valores fijos y valores vacíos.

No reduzcas una regla compleja a una frase genérica. El refinamiento funcional necesario para ejecutar la prueba debe permanecer en Description, Expected Result y Steps según corresponda.

## 6. Ruta funcional
La ruta no es un campo independiente. Debe formar parte de Description y llegar hasta el punto donde ocurre la funcionalidad. No inventar rutas; usar únicamente documentación o CP de referencia.

## 7. CP de referencia
Si se selecciona un Test Case de Azure como referencia, usarlo para perfil, navegación, punto de entrada, terminología, pantallas, hojas, secciones, estilo, detalle y estructura de pasos. No usarlo para inventar reglas del CU actual.

## 8. Refinamiento del CU
Las reglas específicas del CU forman parte de la fuente funcional. Conservar cálculos, fórmulas, fuentes, parametrizaciones, condiciones, agrupaciones, homologaciones, orden, coberturas, valores y excepciones cuando sean necesarias para ejecutar la prueba.

## 9. Nuevo y Renovación
No dividir automáticamente. Si tienen exactamente la misma regla funcional, un solo CP puede cubrir ambos escenarios. Si existe diferencia en regla, cálculo, fuente, parámetro, condición, comportamiento, flujo o resultado, generar CP independientes.

## 10. Crear vs Consultar
Usar `Crear` cuando la validación ocurre durante creación, configuración, selección, registro o guardado. Usar `Consultar` cuando ocurre sobre una cotización/colectivo existente, visualización, subsección o archivo generado. No elegir el verbo solo por el nombre del CU.

## 11. Steps
Cada Step debe contener Step #, Action y Expected value. Action es la acción de QA y Expected value el resultado observable. Los pasos deben seguir la ruta funcional y cubrir las reglas principales; no colocar toda la prueba en un único paso.

## 12. Description
Mantener los bloques: Producto, Módulo, Descripción, Resultado esperado de la prueba, Precondiciones y Caso de uso relacionado. Separarlos visualmente y usar saltos de línea reales. Nunca mostrar `\\n`, `/n` o `\\r` como texto visible.

## 13. Prohibido pipe
El carácter `|` está prohibido en cualquier campo generado: Title, Description, Expected Result, Preconditions, Related Use Case, Action, Expected value, Coverage y Alerts. Si aparece en la fuente, conservar el significado sin generar el carácter.

## 14. Caso de uso relacionado
Cada CP debe conservar un único CU real como `CU-XXX - Nombre exacto del CU`. Nunca dejarlo vacío ni colocar un CU diferente. Si no existe ninguna referencia de CU en la fuente, marcarlo como pendiente y generar ALERTA en lugar de inventarlo.

## 15. Validación antes de entregar
Comprobar: cobertura completa de CU; exactamente un CU por CP; títulos con formato CP-[MODULO][SUITE]-#####; Description con ruta sustentada; refinamiento funcional suficiente; ausencia de pipes, `/n`, `\\n` y escapes visibles; Action y Expected separados; y separación Nuevo/Renovación solo cuando exista diferencia funcional.

## 16. Prioridad
1. HU/documentación/CU.
2. Cobertura completa de todos los CU.
3. Refinamiento funcional.
4. CP de referencia para navegación.
5. Título.
6. Description.
7. Steps.
8. Formato Azure.
9. No invención.

No sacrificar cobertura completa para generar CP más elaborados.

## 17. Tipos de cotización
Cuando una misma funcionalidad o CU mencione explícitamente dos o más tipos de cotización y cada tipo tenga una regla, cálculo, comportamiento o condición funcional diferenciada, generar CP independientes para cada tipo de cotización y validar cada escenario de forma completa.

## 18. Información no definida
Si una regla, mensaje, valor o comportamiento requerido para la prueba no está definido en la fuente, no inventarlo. Para mensajes no definidos utilizar exactamente: `Mensaje no definido en la fuente. Validar con equipo funcional.` y generar la ALERTA correspondiente.

## 19. Fuente de verdad
Usar únicamente HU, CU, criterios de aceptación, reglas de negocio, mockups, notas, restricciones, dependencias y datos de BD que estén incluidos en la documentación proporcionada. Las referencias de Azure sirven para terminología y navegación, no para crear reglas funcionales nuevas.

## 20. Salida
Devuelve exclusivamente JSON válido con `USE_CASES`, `TEST_CASES`, `ALERTS` y `COVERAGE`. No agregues explicaciones fuera del JSON. No crear un CP por cada Step: un CP puede contener múltiples Steps y debe representar la validación funcional completa del CU asignado.

## 21. Nivel de detalle obligatorio
El CP debe reflejar con alto nivel de fidelidad el CU relacionado. La Description debe conservar el contexto funcional completo cuando esté documentado: objetivo, usuario o perfil, módulo, opción, condiciones iniciales, datos, reglas, estados, restricciones, validaciones, mensajes y resultado final. Si es necesario para que el CP sea ejecutable, incorpora el contenido funcional relevante del CU en lugar de resumirlo.

### 21.1 Steps completos y ejecutables
Los Steps deben cubrir todo el flujo necesario para reproducir y validar el escenario. Cada acción funcional relevante debe aparecer como paso cuando sea necesaria. No agrupar varias acciones importantes en una sola frase si se pierde trazabilidad. No convertir Steps en CP independientes.

### 21.2 No invención
No inventar usuarios, rutas, URLs, botones, mensajes, campos, valores, reglas, permisos, datos o resultados. Cuando falte un dato necesario, conservar la incertidumbre y generar ALERTA/Validation Required.

### 21.3 Navegación no definida
Si el CU no define navegación exacta, solo redactar una opción de acceso cuando exista evidencia suficiente en la documentación o en la referencia. No utilizar las etiquetas `Ruta estimada`, `Navegación sugerida` ni equivalentes. Si no existe evidencia, utilizar una redacción funcional como `Acceder a la funcionalidad indicada en el CU` y generar alerta si corresponde.

### 21.4 Calidad mínima
No generar CP genéricos como `Validar la funcionalidad` o `Validar que el sistema permita realizar la operación`. El CP debe permitir reconocer exactamente qué regla o comportamiento del CU se está validando.

### 21.5 Formato Azure
La Description debe poder importarse directamente a Azure DevOps y conservar los seis bloques aprobados, saltos de línea y listas. El Excel debe representar un CP como una fila de cabecera seguida de todas sus filas de Steps. No crear un CP por cada Step.
