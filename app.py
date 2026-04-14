"""Aplicación principal Streamlit."""

import streamlit as st

from utils.database import init_db

st.set_page_config(page_title="SGP-DSS", layout="wide")

init_db()

st.session_state.setdefault("autenticado", False)

if not st.session_state["autenticado"]:
    _, c, _ = st.columns([1, 1.2, 1])
    with c:
        st.markdown("### Iniciar sesión")
        with st.form("login"):
            usuario = st.text_input("Usuario")
            contraseña = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            if usuario == "Admin" and contraseña == "1234":
                st.session_state["autenticado"] = True
                st.session_state["usuario"] = "Admin"
                st.rerun()
            else:
                st.error("Usuario o contraseña incorrectos.")
    st.stop()

with st.sidebar:
    if st.button("Cerrar Sesión"):
        st.session_state["autenticado"] = False
        st.session_state.pop("usuario", None)
        st.rerun()

st.title("SGP-DSS")
st.caption(f"Sesión: **{st.session_state.get('usuario', '')}**")
