"""Aplicación principal Streamlit."""

import streamlit as st

from utils.database import init_db

st.set_page_config(page_title="SGP-DSS", layout="wide")

init_db()

USUARIOS = {
    "Admin":    {"contraseña": "1234",    "rol": "admin"},
    "Vendedor": {"contraseña": "vend123", "rol": "vendedor"},
}

st.session_state.setdefault("autenticado", False)

if not st.session_state["autenticado"]:
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### Iniciar sesión")
        with st.form("login"):
            usuario   = st.text_input("Usuario")
            contraseña = st.text_input("Contraseña", type="password")
            entrar    = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            datos = USUARIOS.get(usuario)
            if datos and contraseña == datos["contraseña"]:
                st.session_state["autenticado"] = True
                st.session_state["usuario"]     = usuario
                st.session_state["rol"]         = datos["rol"]
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop()

st.title("SGP-DSS")
st.caption(f"Sesión: **{st.session_state.get('usuario', '')}**")