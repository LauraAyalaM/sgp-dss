"""Sidebar compartido: sesión y navegación."""

from __future__ import annotations

import streamlit as st


def render_sidebar() -> None:
    """Renderiza el sidebar con info de sesión y botón de cierre."""
    with st.sidebar:
        st.markdown(f"**Usuario:** {st.session_state.get('usuario', '')}")
        st.caption(f"Rol: {st.session_state.get('rol', '')}")
        st.divider()
        if st.button("Cerrar sesión", use_container_width=True):
            for k in ["autenticado", "usuario", "rol"]:
                st.session_state.pop(k, None)
            st.switch_page("app.py")