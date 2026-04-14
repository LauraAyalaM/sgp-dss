"""Gestión de pedidos."""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from utils.database import execute, init_db, query_df

st.set_page_config(page_title="Gestión de Pedidos", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()

ESTADOS_SELECT = ["Todos", "pendiente", "en_preparacion", "entregado", "cancelado"]
ESTADOS_EDITAR = ["pendiente", "en_preparacion", "entregado", "cancelado"]

_BADGE_STYLES = {
    "pendiente": ("#854d0e", "#fef9c3"),
    "en_preparacion": ("#1e40af", "#dbeafe"),
    "entregado": ("#166534", "#dcfce7"),
    "cancelado": ("#991b1b", "#fecaca"),
}


def _widget_key_suffix(pedido_id: str, idx: int) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in pedido_id)
    return f"{idx}_{safe}"


def badge_html(estado: str) -> str:
    safe = html.escape(estado)
    fg, bg = _BADGE_STYLES.get(estado, ("#374151", "#e5e7eb"))
    return (
        f'<span style="display:inline-block;background-color:{bg};color:{fg};'
        f"padding:4px 10px;border-radius:999px;font-size:13px;font-weight:600;"
        f'border:1px solid rgba(0,0,0,0.06);">{safe}</span>'
    )


def fetch_pedidos(fecha: date | None, cliente: str, estado: str) -> pd.DataFrame:
    conds: list[str] = []
    params: list = []
    if fecha is not None:
        conds.append("date(p.fecha) = date(?)")
        params.append(fecha.isoformat())
    if cliente.strip():
        conds.append("c.nombre LIKE ? COLLATE NOCASE")
        params.append(f"%{cliente.strip()}%")
    if estado != "Todos":
        conds.append("p.estado = ?")
        params.append(estado)
    where = " AND ".join(conds) if conds else "1=1"
    sql = f"""
    SELECT
        p.id AS id_pedido,
        c.nombre AS cliente,
        p.fecha,
        p.total,
        p.estado
    FROM Pedidos p
    JOIN Clientes c ON c.id = p.cliente_id
    WHERE {where}
    ORDER BY p.fecha DESC, p.id DESC
    """
    return query_df(sql, tuple(params) if params else None)


def detalle_pedido_df(pedido_id: str) -> pd.DataFrame:
    return query_df(
        """
        SELECT
            pr.nombre AS producto,
            d.cantidad,
            d.precio_unitario,
            d.subtotal
        FROM Detalle_Pedido d
        JOIN Productos pr ON pr.id = d.producto_id
        WHERE d.pedido_id = ?
        ORDER BY d.id
        """,
        (pedido_id,),
    )


def pedido_cabecera_df(pedido_id: str) -> pd.DataFrame:
    return query_df(
        """
        SELECT
            p.id AS id_pedido,
            c.nombre AS cliente,
            p.fecha,
            p.estado,
            p.total,
            p.notas
        FROM Pedidos p
        JOIN Clientes c ON c.id = p.cliente_id
        WHERE p.id = ?
        """,
        (pedido_id,),
    )


@st.dialog("Detalle del pedido")
def dialogo_ver_pedido() -> None:
    pid = st.session_state.get("gp_dialog_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar", key="dlg_cerrar_nf"):
            st.session_state.pop("gp_dialog_pid", None)
            st.rerun()
        return
    row = cab.iloc[0]
    st.markdown(badge_html(str(row["estado"])), unsafe_allow_html=True)
    st.markdown(
        f"**ID:** `{html.escape(str(row['id_pedido']))}`  \n"
        f"**Cliente:** {html.escape(str(row['cliente']))}  \n"
        f"**Fecha:** {html.escape(str(row['fecha']))}  \n"
        f"**Total:** $ {float(row['total']):,.0f}"
    )
    notas = row["notas"]
    if pd.notna(notas) and str(notas).strip():
        st.markdown(f"**Notas:** {html.escape(str(notas))}")
    st.subheader("Ítems")
    dfd = detalle_pedido_df(pid)
    if dfd.empty:
        st.caption("Sin líneas de detalle.")
    else:
        st.dataframe(dfd, hide_index=True, use_container_width=True)
    if st.button("Cerrar", key="dlg_cerrar"):
        st.session_state.pop("gp_dialog_pid", None)
        st.rerun()


st.title("Gestión de Pedidos")

with st.form("filtros_pedidos"):
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        fecha_default = st.session_state.get("gp_fecha", date.today())
        fecha_in = st.date_input("Fecha", value=fecha_default)
    with col_f2:
        cliente_in = st.text_input(
            "Cliente",
            value=st.session_state.get("gp_cliente", ""),
        )
    with col_f3:
        sel_default = st.session_state.get("gp_estado_sel", "Todos")
        if sel_default not in ESTADOS_SELECT:
            sel_default = "Todos"
        estado_in = st.selectbox(
            "Estado",
            ESTADOS_SELECT,
            index=ESTADOS_SELECT.index(sel_default),
        )
    aplicar = st.form_submit_button("Aplicar Filtros")

if aplicar:
    st.session_state["gp_fecha"] = fecha_in
    st.session_state["gp_cliente"] = cliente_in
    st.session_state["gp_estado_sel"] = estado_in
    st.session_state["gp_filtros"] = {
        "fecha": fecha_in,
        "cliente": cliente_in,
        "estado": estado_in,
    }
    st.session_state["gp_df"] = fetch_pedidos(fecha_in, cliente_in, estado_in)
elif "gp_df" not in st.session_state:
    st.session_state["gp_filtros"] = {
        "fecha": None,
        "cliente": "",
        "estado": "Todos",
    }
    st.session_state["gp_df"] = fetch_pedidos(None, "", "Todos")

df = st.session_state["gp_df"]

leyenda_badges = " ".join(
    badge_html(e) for e in ["pendiente", "en_preparacion", "entregado", "cancelado"]
)
st.markdown(
    f"<p style='font-size:0.9rem;margin-bottom:1rem;'>"
    f"<strong>Leyenda:</strong> {leyenda_badges}</p>",
    unsafe_allow_html=True,
)

if df.empty:
    st.info("No hay pedidos que coincidan con los filtros.")
else:
    df_tabla = df.rename(
        columns={
            "id_pedido": "ID Pedido",
            "cliente": "Cliente",
            "fecha": "Fecha",
            "total": "Total",
            "estado": "Estado",
        }
    )
    st.dataframe(
        df_tabla,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Total": st.column_config.NumberColumn("Total (COP)", format="%d"),
        },
    )

st.subheader("Acciones por pedido")
records = df.to_dict("records") if not df.empty else []

for i, row in enumerate(records):
    pid = str(row["id_pedido"])
    ks = _widget_key_suffix(pid, i)
    titulo = f"{pid} · {row['cliente']}"
    with st.expander(titulo, expanded=False):
        st.markdown(badge_html(str(row["estado"])), unsafe_allow_html=True)
        c_a, c_b = st.columns(2)
        with c_a:
            if st.button("Ver", key=f"gp_ver_{ks}", use_container_width=True):
                st.session_state["gp_dialog_pid"] = pid
        with c_b:
            st.caption("Cambiar estado abajo")
        opts = ESTADOS_EDITAR
        try:
            ix = opts.index(str(row["estado"]))
        except ValueError:
            ix = 0
        nuevo = st.selectbox(
            "Nuevo estado",
            opts,
            index=ix,
            key=f"gp_est_sel_{ks}",
        )
        if st.button("Guardar cambio", key=f"gp_save_{ks}"):
            execute(
                "UPDATE Pedidos SET estado = ? WHERE id = ?",
                (nuevo, pid),
            )
            st.success("Estado actualizado.")
            filt = st.session_state.get(
                "gp_filtros",
                {"fecha": None, "cliente": "", "estado": "Todos"},
            )
            st.session_state["gp_df"] = fetch_pedidos(
                filt["fecha"],
                filt["cliente"],
                filt["estado"],
            )
            st.rerun()

if st.session_state.get("gp_dialog_pid"):
    dialogo_ver_pedido()
