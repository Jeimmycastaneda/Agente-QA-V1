"""Resolución de credenciales.

Único punto fuera de `agente_qa/ui/` donde se permite importar Streamlit.
El import es perezoso y tolerante a la ausencia de `secrets.toml` para que
`resolve_secret` funcione igual en tests y fuera de un runtime Streamlit.
"""

import os


def resolve_secret(name: str, default: str = "") -> str:
    """Busca `name` en st.secrets, luego en variables de entorno, luego default."""
    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        # Sin secrets.toml, sin runtime Streamlit, o cualquier otro fallo
        # al acceder a st.secrets: se sigue con el resto de las fuentes.
        pass

    return os.environ.get(name, default)
