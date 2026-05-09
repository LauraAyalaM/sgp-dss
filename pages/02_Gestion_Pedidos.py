"""Gestión de pedidos."""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from utils.database import execute, get_connection, init_db, query_df

st.set_page_config(page_title="Gestión de Pedidos", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()

ESTADOS_SELECT = ["Todos", "pendiente", "en_preparacion", "entregado", "cancelado"]
ESTADOS_EDITAR = ["pendiente", "en_preparacion", "entregado", "cancelado"]
METODOS_PAGO   = ["efectivo", "transferencia", "QR"]

_BADGE_CSS = {
    "pendiente":      "background:#fef9c3;color:#854d0e;border:1px solid #fde047;",
    "en_preparacion": "background:#dbeafe;color:#1e40af;border:1px solid #93c5fd;",
    "entregado":      "background:#dcfce7;color:#166534;border:1px solid #86efac;",
    "cancelado":      "background:#fecaca;color:#991b1b;border:1px solid #fca5a5;",
}
_ESTADO_EMOJI = {
    "pendiente":      "🕐",
    "en_preparacion": "👨‍🍳",
    "entregado":      "✅",
    "cancelado":      "❌",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def badge_html(estado: str) -> str:
    safe = html.escape(estado)
    emoji = _ESTADO_EMOJI.get(estado, "")
    css   = _BADGE_CSS.get(estado, "background:#e5e7eb;color:#374151;border:1px solid #d1d5db;")
    return (
        f'<span style="display:inline-block;{css}'
        f'padding:4px 12px;border-radius:999px;font-size:13px;font-weight:600;">'
        f'{emoji} {safe}</span>'
    )


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}"


def _widget_key_suffix(pedido_id: str, idx: int) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in pedido_id)
    return f"{idx}_{safe}"


# ── Queries ────────────────────────────────────────────────────────────────────

def fetch_pedidos(fecha: date | None, cliente: str, estado: str) -> pd.DataFrame:
    """Trae pedidos con filtros. Las columnas 'pagado' y 'saldo' se calculan en Python."""
    conds: list[str] = []
    params: list     = []
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

    # Query base — sin agregación de pagos para evitar problemas con GROUP BY
    sql = f"""
    SELECT
        p.id       AS id_pedido,
        c.nombre   AS cliente,
        p.fecha,
        p.total,
        p.estado,
        p.notas
    FROM Pedidos p
    JOIN Clientes c ON c.id = p.cliente_id
    WHERE {where}
    ORDER BY p.fecha DESC, p.id DESC
    """
    df = query_df(sql, tuple(params) if params else None)
    if df.empty:
        df["pagado"] = pd.Series(dtype=float)
        df["saldo"]  = pd.Series(dtype=float)
        return df

    # Pagos confirmados por pedido en un query separado
    ids_pedido = df["id_pedido"].tolist()
    placeholders = ",".join("?" * len(ids_pedido))
    df_pagos = query_df(
        f"""
        SELECT pedido_id, COALESCE(SUM(monto), 0) AS pagado
        FROM Pagos
        WHERE estado = 'confirmado' AND pedido_id IN ({placeholders})
        GROUP BY pedido_id
        """,
        tuple(ids_pedido),
    )

    if df_pagos.empty:
        df["pagado"] = 0.0
    else:
        df = df.merge(df_pagos, left_on="id_pedido", right_on="pedido_id", how="left")
        df["pagado"] = df["pagado"].fillna(0.0)
        if "pedido_id" in df.columns:
            df = df.drop(columns=["pedido_id"])

    df["saldo"] = (df["total"] - df["pagado"]).clip(lower=0)
    return df


def detalle_pedido_df(pedido_id: str) -> pd.DataFrame:
    return query_df(
        """
        SELECT pr.nombre AS producto, d.cantidad, d.precio_unitario, d.subtotal
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
        SELECT p.id AS id_pedido, c.nombre AS cliente, c.id AS cliente_id,
               p.fecha, p.estado, p.total, p.notas
        FROM Pedidos p
        JOIN Clientes c ON c.id = p.cliente_id
        WHERE p.id = ?
        """,
        (pedido_id,),
    )


def _saldo_pedido(pedido_id: str) -> float:
    df = query_df(
        """
        SELECT
            p.total - COALESCE(SUM(CASE WHEN pg.estado='confirmado' THEN pg.monto ELSE 0 END), 0) AS saldo
        FROM Pedidos p
        LEFT JOIN Pagos pg ON pg.pedido_id = p.id
        WHERE p.id = ?
        GROUP BY p.id, p.total
        """,
        (pedido_id,),
    )
    if df.empty:
        return 0.0
    val = df.iloc[0]["saldo"]
    return max(0.0, float(val))


def _refresh_df() -> None:
    filt = st.session_state.get("gp_filtros", {"fecha": None, "cliente": "", "estado": "Todos"})
    st.session_state["gp_df"] = fetch_pedidos(filt["fecha"], filt["cliente"], filt["estado"])


# ── Métricas ───────────────────────────────────────────────────────────────────

def _metricas_rapidas(df: pd.DataFrame) -> None:
    total      = len(df)
    pendientes = int((df["estado"] == "pendiente").sum())
    en_prep    = int((df["estado"] == "en_preparacion").sum())
    entregados = int((df["estado"] == "entregado").sum())
    cancelados = int((df["estado"] == "cancelado").sum())
    ventas     = float(df.loc[df["estado"] != "cancelado", "total"].sum())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total pedidos",  total)
    c2.metric("Pendientes",     pendientes)
    c3.metric("En preparación", en_prep)
    c4.metric("Entregados",     entregados)
    c5.metric("Cancelados",     cancelados)
    c6.metric("Ventas",         _fmt_cop(ventas))


# ── Diálogo: ver detalle ───────────────────────────────────────────────────────

@st.dialog("Detalle del pedido")
def dialogo_ver_pedido() -> None:
    pid = st.session_state.get("gp_dialog_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_dialog_pid", None)
            st.rerun()
        return
    row = cab.iloc[0]

    st.markdown(badge_html(str(row["estado"])), unsafe_allow_html=True)
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**ID:** `{html.escape(str(row['id_pedido']))}`")
        st.markdown(f"**Cliente:** {html.escape(str(row['cliente']))}")
    with col2:
        st.markdown(f"**Fecha:** {html.escape(str(row['fecha']))}")
        st.markdown(f"**Total:** {_fmt_cop(float(row['total']))}")

    notas = row["notas"]
    if pd.notna(notas) and str(notas).strip():
        st.info(f"Notas: {html.escape(str(notas))}")

    st.markdown("#### Items del pedido")
    dfd = detalle_pedido_df(pid)
    if dfd.empty:
        st.caption("Sin líneas de detalle.")
    else:
        st.dataframe(
            dfd, hide_index=True, use_container_width=True,
            column_config={
                "precio_unitario": st.column_config.NumberColumn("Precio unit.", format="$ %d"),
                "subtotal":        st.column_config.NumberColumn("Subtotal",     format="$ %d"),
            },
        )

    df_pagos = query_df(
        "SELECT fecha, monto, metodo_pago, referencia_pago, estado FROM Pagos WHERE pedido_id = ? ORDER BY id",
        (pid,),
    )
    if not df_pagos.empty:
        st.markdown("#### Pagos registrados")
        st.dataframe(
            df_pagos, hide_index=True, use_container_width=True,
            column_config={"monto": st.column_config.NumberColumn("Monto", format="$ %d")},
        )

    if st.button("Cerrar", key="dlg_ver_cerrar"):
        st.session_state.pop("gp_dialog_pid", None)
        st.rerun()


# ── Diálogo: editar ────────────────────────────────────────────────────────────

@st.dialog("Editar pedido")
def dialogo_editar_pedido() -> None:
    pid = st.session_state.get("gp_edit_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_edit_pid", None)
            st.rerun()
        return
    row = cab.iloc[0]

    st.markdown(f"**Pedido:** `{html.escape(str(row['id_pedido']))}`")
    st.markdown(f"**Cliente:** {html.escape(str(row['cliente']))}")
    st.markdown("---")

    try:
        ix_estado = ESTADOS_EDITAR.index(str(row["estado"]))
    except ValueError:
        ix_estado = 0

    nuevo_estado = st.selectbox(
        "Estado", ESTADOS_EDITAR, index=ix_estado,
        format_func=lambda e: f"{_ESTADO_EMOJI.get(e, '')} {e}",
        key="dlg_edit_estado",
    )
    notas_actuales = str(row["notas"]) if pd.notna(row["notas"]) else ""
    nuevas_notas   = st.text_area("Notas", value=notas_actuales, key="dlg_edit_notas", height=100)

    col_g, col_c = st.columns(2)
    with col_g:
        if st.button("Guardar cambios", use_container_width=True, type="primary"):
            execute(
                "UPDATE Pedidos SET estado = ?, notas = ? WHERE id = ?",
                (nuevo_estado, nuevas_notas.strip() or None, pid),
            )
            st.session_state.pop("gp_edit_pid", None)
            _refresh_df()
            st.rerun()
    with col_c:
        if st.button("Cancelar", use_container_width=True):
            st.session_state.pop("gp_edit_pid", None)
            st.rerun()


# ── Diálogo: cancelar pedido ───────────────────────────────────────────────────

@st.dialog("Cancelar pedido")
def dialogo_cancelar_pedido() -> None:
    pid = st.session_state.get("gp_cancel_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_cancel_pid", None)
            st.rerun()
        return
    row = cab.iloc[0]

    if str(row["estado"]) == "cancelado":
        st.info("Este pedido ya está cancelado.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_cancel_pid", None)
            st.rerun()
        return

    st.warning(
        f"¿Marcar como cancelado el pedido `{row['id_pedido']}` "
        f"de **{row['cliente']}** por **{_fmt_cop(float(row['total']))}**?\n\n"
        "Los pagos ya registrados no se eliminarán."
    )
    motivo = st.text_area("Motivo de cancelación (opcional)", key="dlg_cancel_motivo", height=80)

    col_s, col_c = st.columns(2)
    with col_s:
        if st.button("Sí, cancelar", use_container_width=True, type="primary"):
            execute(
                "UPDATE Pedidos SET estado = 'cancelado', notas = ? WHERE id = ?",
                (motivo.strip() or None, pid),
            )
            st.session_state.pop("gp_cancel_pid", None)
            _refresh_df()
            st.rerun()
    with col_c:
        if st.button("Volver", use_container_width=True):
            st.session_state.pop("gp_cancel_pid", None)
            st.rerun()


# ── Diálogo: confirmar pago ────────────────────────────────────────────────────

@st.dialog("Confirmar pago del pedido")
def dialogo_confirmar_pago() -> None:
    pid = st.session_state.get("gp_confirm_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_confirm_pid", None)
            st.rerun()
        return
    row   = cab.iloc[0]
    saldo = _saldo_pedido(pid)

    st.markdown(f"**Pedido:** `{html.escape(str(row['id_pedido']))}`")
    st.markdown(f"**Cliente:** {html.escape(str(row['cliente']))}")
    st.markdown(f"**Total pedido:** {_fmt_cop(float(row['total']))}")
    st.markdown(f"**Saldo pendiente:** {_fmt_cop(saldo)}")
    st.markdown("---")

    if saldo <= 0:
        st.success("Este pedido ya está pagado en su totalidad.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_confirm_pid", None)
            st.rerun()
        return

    monto = st.number_input(
        "Monto a registrar",
        min_value=0.01,
        max_value=float(saldo),
        value=float(saldo),
        step=500.0,
        format="%.0f",
        key="dlg_confirm_monto",
    )
    metodo     = st.selectbox("Método de pago", METODOS_PAGO, key="dlg_confirm_metodo")
    referencia = st.text_input(
        "Referencia (obligatoria si es transferencia)",
        key="dlg_confirm_ref",
        disabled=(metodo != "transferencia"),
    )
    comprobante = st.file_uploader(
        "Subir comprobante (opcional)",
        type=["png", "jpg", "jpeg", "pdf", "webp"],
        key="dlg_confirm_comprobante",
    )
    if comprobante is not None:
        if comprobante.type.startswith("image/"):
            st.image(comprobante, caption="Vista previa", use_container_width=True)
        else:
            st.success(f"Archivo cargado: {comprobante.name}")

    if monto < saldo:
        st.info(f"Pago parcial: quedará un saldo de {_fmt_cop(saldo - monto)} tras este registro.")

    col_g, col_c = st.columns(2)
    with col_g:
        if st.button("Registrar pago", use_container_width=True, type="primary"):
            if metodo == "transferencia" and not (referencia or "").strip():
                st.error("La referencia es obligatoria para transferencia.")
                return
            ref_val = (referencia or "").strip() if metodo == "transferencia" else None
            conn    = get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO Pagos (pedido_id, monto, metodo_pago, referencia_pago, fecha, estado)
                    VALUES (?, ?, ?, ?, ?, 'confirmado')
                    """,
                    (pid, float(monto), metodo, ref_val, date.today().isoformat()),
                )
                row_sum = conn.execute(
                    "SELECT COALESCE(SUM(monto),0) FROM Pagos WHERE pedido_id=? AND estado='confirmado'",
                    (pid,),
                ).fetchone()
                total_pagado = float(row_sum[0]) if row_sum else 0.0
                if total_pagado + 1e-6 >= float(row["total"]):
                    conn.execute("UPDATE Pedidos SET estado='entregado' WHERE id=?", (pid,))
                conn.commit()
            except Exception as exc:
                conn.rollback()
                st.error(f"No se pudo registrar el pago: {exc}")
                conn.close()
                return
            finally:
                conn.close()
            st.session_state.pop("gp_confirm_pid", None)
            _refresh_df()
            st.rerun()
    with col_c:
        if st.button("Cancelar", use_container_width=True):
            st.session_state.pop("gp_confirm_pid", None)
            st.rerun()


# ── Diálogo: eliminar ─────────────────────────────────────────────────────────

@st.dialog("Eliminar pedido")
def dialogo_eliminar_pedido() -> None:
    pid = st.session_state.get("gp_del_pid")
    if not pid:
        return
    cab = pedido_cabecera_df(pid)
    if cab.empty:
        st.warning("No se encontró el pedido.")
        if st.button("Cerrar"):
            st.session_state.pop("gp_del_pid", None)
            st.rerun()
        return
    row = cab.iloc[0]

    st.error(
        f"¿Eliminar el pedido `{row['id_pedido']}` de **{row['cliente']}** "
        f"por **{_fmt_cop(float(row['total']))}**?\n\n"
        "Esta acción no se puede deshacer. Se eliminará también el detalle y los pagos asociados."
    )
    col_d, col_c = st.columns(2)
    with col_d:
        if st.button("Sí, eliminar", use_container_width=True, type="primary"):
            execute("DELETE FROM Detalle_Pedido WHERE pedido_id = ?", (pid,))
            execute("DELETE FROM Pagos WHERE pedido_id = ?", (pid,))
            execute("DELETE FROM Pedidos WHERE id = ?", (pid,))
            st.session_state.pop("gp_del_pid", None)
            _refresh_df()
            st.rerun()
    with col_c:
        if st.button("Cancelar", use_container_width=True):
            st.session_state.pop("gp_del_pid", None)
            st.rerun()


# ── Tabla con acciones ─────────────────────────────────────────────────────────

def _render_tabla_pedidos(subdf: pd.DataFrame, tab_prefix: str = "t") -> None:
    if subdf.empty:
        st.info("No hay pedidos en esta categoría.")
        return

    # Garantizar que las columnas de pago existen (por si el df llega vacío de pagos)
    for col, default in [("pagado", 0.0), ("saldo", 0.0)]:
        if col not in subdf.columns:
            subdf = subdf.copy()
            subdf[col] = default

    df_show = subdf[["id_pedido", "cliente", "fecha", "total", "pagado", "saldo", "estado"]].rename(
        columns={
            "id_pedido": "ID Pedido",
            "cliente":   "Cliente",
            "fecha":     "Fecha",
            "total":     "Total (COP)",
            "pagado":    "Pagado (COP)",
            "saldo":     "Saldo (COP)",
            "estado":    "Estado",
        }
    )
    st.dataframe(
        df_show, hide_index=True, use_container_width=True,
        column_config={
            "Total (COP)":  st.column_config.NumberColumn("Total (COP)",  format="$ %d"),
            "Pagado (COP)": st.column_config.NumberColumn("Pagado (COP)", format="$ %d"),
            "Saldo (COP)":  st.column_config.NumberColumn("Saldo (COP)",  format="$ %d"),
        },
    )

    st.markdown("#### Acciones por pedido")
    for i, row in enumerate(subdf.to_dict("records")):
        pid        = str(row["id_pedido"])
        ks         = f"{tab_prefix}_{_widget_key_suffix(pid, i)}"
        estado_str = str(row["estado"])
        emoji      = _ESTADO_EMOJI.get(estado_str, "")
        saldo      = float(row.get("saldo", 0.0))
        pagado     = float(row.get("pagado", 0.0))

        with st.expander(f"{emoji} {pid} · {row['cliente']} · {_fmt_cop(float(row['total']))}", expanded=False):
            col_meta1, col_meta2 = st.columns(2)
            with col_meta1:
                st.markdown(f"**Fecha:** {row['fecha']}")
                st.markdown(badge_html(estado_str), unsafe_allow_html=True)
            with col_meta2:
                st.markdown(f"**Pagado:** {_fmt_cop(pagado)}")
                st.markdown(f"**Saldo:** {_fmt_cop(saldo)}")
                notas = row.get("notas", "")
                if pd.notna(notas) and str(notas).strip():
                    st.caption(html.escape(str(notas)))

            st.markdown("")
            ca, cb, cc, cd = st.columns(4)

            with ca:
                if st.button("Ver detalle", key=f"ver_{ks}", use_container_width=True):
                    st.session_state["gp_dialog_pid"] = pid
                    st.rerun()

            with cb:
                pago_disabled = saldo <= 0 or estado_str == "cancelado"
                if st.button(
                    "Confirmar pago",
                    key=f"confirm_{ks}",
                    use_container_width=True,
                    disabled=pago_disabled,
                    help="Sin saldo pendiente" if pago_disabled else "Registrar pago",
                ):
                    st.session_state["gp_confirm_pid"] = pid
                    st.rerun()

            with cc:
                if st.button("Editar", key=f"edit_{ks}", use_container_width=True):
                    st.session_state["gp_edit_pid"] = pid
                    st.rerun()

            with cd:
                cancel_disabled = estado_str in ("cancelado", "entregado")
                if st.button(
                    "Cancelar",
                    key=f"cancel_{ks}",
                    use_container_width=True,
                    disabled=cancel_disabled,
                    help="No se puede cancelar un pedido ya entregado o cancelado" if cancel_disabled else "",
                ):
                    st.session_state["gp_cancel_pid"] = pid
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# UI PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

st.title("Gestión de Pedidos")

# ── Filtros ────────────────────────────────────────────────────────────────────

with st.expander("Filtros", expanded=True):
    col_f1, col_f2, col_f3, col_f4 = st.columns([1.2, 1.5, 1.2, 0.8])
    with col_f1:
        fecha_in = st.date_input("Fecha", value=st.session_state.get("gp_fecha", None))
    with col_f2:
        cliente_in = st.text_input(
            "Buscar cliente",
            value=st.session_state.get("gp_cliente", ""),
            placeholder="Nombre del cliente…",
        )
    with col_f3:
        sel_default = st.session_state.get("gp_estado_sel", "Todos")
        if sel_default not in ESTADOS_SELECT:
            sel_default = "Todos"
        estado_in = st.selectbox(
            "Estado", ESTADOS_SELECT,
            index=ESTADOS_SELECT.index(sel_default),
            format_func=lambda e: f"{_ESTADO_EMOJI.get(e, '')} {e}" if e != "Todos" else "Todos",
        )
    with col_f4:
        st.markdown("<br>", unsafe_allow_html=True)
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            aplicar = st.button("Aplicar", use_container_width=True, type="primary")
        with col_b2:
            limpiar = st.button("Limpiar", use_container_width=True)

if limpiar:
    for k in ["gp_fecha", "gp_cliente", "gp_estado_sel", "gp_filtros", "gp_df"]:
        st.session_state.pop(k, None)
    st.rerun()

if aplicar:
    st.session_state["gp_fecha"]      = fecha_in
    st.session_state["gp_cliente"]    = cliente_in
    st.session_state["gp_estado_sel"] = estado_in
    st.session_state["gp_filtros"]    = {"fecha": fecha_in, "cliente": cliente_in, "estado": estado_in}
    st.session_state["gp_df"]         = fetch_pedidos(fecha_in, cliente_in, estado_in)
elif "gp_df" not in st.session_state:
    st.session_state["gp_filtros"] = {"fecha": None, "cliente": "", "estado": "Todos"}
    st.session_state["gp_df"]      = fetch_pedidos(None, "", "Todos")

df = st.session_state["gp_df"]

# ── Métricas ───────────────────────────────────────────────────────────────────

st.markdown("---")
_metricas_rapidas(df)
st.markdown("---")

# ── Tabs por estado ────────────────────────────────────────────────────────────

tab_todos, tab_pend, tab_prep, tab_entg, tab_canc = st.tabs([
    f"Todos ({len(df)})",
    f"Pendientes ({int((df['estado']=='pendiente').sum())})",
    f"En preparación ({int((df['estado']=='en_preparacion').sum())})",
    f"Entregados ({int((df['estado']=='entregado').sum())})",
    f"Cancelados ({int((df['estado']=='cancelado').sum())})",
])

with tab_todos:
    _render_tabla_pedidos(df, tab_prefix="todos")

with tab_pend:
    _render_tabla_pedidos(
        df[df["estado"] == "pendiente"].reset_index(drop=True), tab_prefix="pend"
    )
with tab_prep:
    _render_tabla_pedidos(
        df[df["estado"] == "en_preparacion"].reset_index(drop=True), tab_prefix="prep"
    )
with tab_entg:
    _render_tabla_pedidos(
        df[df["estado"] == "entregado"].reset_index(drop=True), tab_prefix="entg"
    )
with tab_canc:
    _render_tabla_pedidos(
        df[df["estado"] == "cancelado"].reset_index(drop=True), tab_prefix="canc"
    )

# ── Diálogos ───────────────────────────────────────────────────────────────────

if st.session_state.get("gp_dialog_pid"):
    dialogo_ver_pedido()

if st.session_state.get("gp_edit_pid"):
    dialogo_editar_pedido()

if st.session_state.get("gp_cancel_pid"):
    dialogo_cancelar_pedido()

if st.session_state.get("gp_confirm_pid"):
    dialogo_confirmar_pago()

if st.session_state.get("gp_del_pid"):
    dialogo_eliminar_pedido()