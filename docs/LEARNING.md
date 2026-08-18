# Cómo estudiar esta arquitectura

No existe un único estándar universal para ordenar carpetas. La estructura combina
principios conocidos:

1. separación de responsabilidades;
2. paquetes Python;
3. inversión/aislamiento del proveedor de IA;
4. capa de integración externa;
5. capa de presentación;
6. exportadores independientes;
7. pruebas aisladas.

Para Streamlit, estudiar la documentación oficial sobre `st.Page` y `st.navigation`.
El entrypoint puede actuar como router/picture frame y las páginas pueden vivir en
archivos separados.

También estudiar Python Packaging User Guide sobre flat layout vs src layout.
