# Agente QA — punto de control previo a creación

Esta versión deja el flujo de Azure DevOps detenido antes de cualquier futura creación de Test Case.

Flujo:
1. Consultar 10 Test Plans (GET).
2. Seleccionar Test Plan de referencia (GET).
3. Consultar Suites (GET).
4. Seleccionar Suite (GET).
5. Consultar Test Cases de la Suite (GET).
6. Seleccionar un Test Case existente.
7. Consultar el detalle del Test Case como referencia (GET).
8. Mostrar Description, Preconditions, Steps y campos base para comparación.
9. Mostrar una comparación estructural preliminar.
10. DETENERSE. No se agrega creación, actualización ni eliminación como parte de este ajuste.

No se debe usar un Test Case existente para modificarlo. La consulta del detalle es únicamente para estudiar la estructura real antes de definir el payload del nuevo CP.
