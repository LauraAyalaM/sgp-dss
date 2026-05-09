"""Crear pedido."""

from __future__ import annotations

from datetime import date

import streamlit as st

from utils.database import get_connection, init_db, query_df

st.set_page_config(page_title="Crear Pedido", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}"


def _next_pedido_id(fecha: date) -> str:
    prefix = f"PED-{fecha.strftime('%Y%m%d')}-"
    df = query_df("SELECT id FROM Pedidos WHERE id LIKE ?", (prefix + "%",))
    if df.empty:
        seq = 1
    else:
        nums: list[int] = []
        for raw in df["id"].astype(str):
            try:
                nums.append(int(raw.split("-")[-1]))
            except ValueError:
                continue
        seq = max(nums) + 1 if nums else 1
    return f"{prefix}{seq:03d}"


# ── Datos base ─────────────────────────────────────────────────────────────────

clientes_df = query_df("SELECT id, nombre FROM Clientes ORDER BY nombre COLLATE NOCASE")
productos_df = query_df("SELECT id, nombre, precio_unitario FROM Productos ORDER BY nombre COLLATE NOCASE")

if clientes_df.empty:
    st.error("No hay clientes en la base de datos. Registre clientes antes de crear pedidos.")
    st.stop()

if productos_df.empty:
    st.error("No hay productos en la base de datos.")
    st.stop()

ids_cliente = [int(x) for x in clientes_df["id"].tolist()]
nombre_cliente = dict(zip(clientes_df["id"], clientes_df["nombre"]))

ids_producto = [int(x) for x in productos_df["id"].tolist()]
precio_producto = {int(r["id"]): float(r["precio_unitario"]) for _, r in productos_df.iterrows()}
nombre_producto = dict(zip(productos_df["id"].astype(int), productos_df["nombre"]))

# ── UI ─────────────────────────────────────────────────────────────────────────

st.title(" Crear Pedido")

if "cp_ok_msg" in st.session_state:
    st.success(st.session_state.pop("cp_ok_msg"))

# Cabecera del pedido
st.markdown("### Datos del pedido")
with st.container(border=True):
    col_cli, col_fec = st.columns(2)
    with col_cli:
        cliente_sel = st.selectbox(
            "Cliente",
            ids_cliente,
            format_func=lambda cid: str(nombre_cliente.get(cid, cid)),
        )
    with col_fec:
        fecha_pedido = st.date_input("Fecha del pedido", value=date.today())

st.markdown("### Productos del pedido")

st.session_state.setdefault("cp_n_lineas", 1)
st.session_state.setdefault("cp_form_v", 0)
v = int(st.session_state["cp_form_v"])

col_add, col_reset = st.columns([1, 5])
with col_add:
    if st.button("Añadir producto", type="secondary"):
        st.session_state["cp_n_lineas"] = int(st.session_state["cp_n_lineas"]) + 1
        st.rerun()

line_totals: list[float] = []

with st.container(border=True):
    # Encabezados de columnas
    h1, h2, h3, h4 = st.columns([2.5, 1, 1, 0.4])
    h1.markdown("**Producto**")
    h2.markdown("**Cantidad**")
    h3.markdown("**Subtotal**")
    h4.markdown("")

    n_lineas = int(st.session_state["cp_n_lineas"])
    lineas_a_eliminar: int | None = None

    for i in range(n_lineas):
        c_p, c_q, c_s, c_x = st.columns([2.5, 1, 1, 0.4])
        with c_p:
            pid = st.selectbox(
                f"Producto {i+1}",
                ids_producto,
                index=0,
                format_func=lambda x: f"{nombre_producto.get(x, x)}",
                key=f"cp_pid_{v}_{i}",
                label_visibility="collapsed",
            )
        with c_q:
            qty = st.number_input(
                "Cant.",
                min_value=0.01,
                value=1.0,
                step=0.5,
                key=f"cp_qty_{v}_{i}",
                label_visibility="collapsed",
            )
        with c_s:
            pu = precio_producto[int(pid)]
            sub = float(qty) * pu
            line_totals.append(sub)
            st.markdown(
                f"<div style='padding-top:8px;font-weight:600;color:#166534'>{_fmt_cop(sub)}</div>",
                unsafe_allow_html=True,
            )
        with c_x:
            if n_lineas > 1:
                if st.button("✕", key=f"cp_del_line_{v}_{i}", help="Quitar línea"):
                    lineas_a_eliminar = i

    if lineas_a_eliminar is not None:
        # Reorganizar: copiar valores actuales menos la línea eliminada
        nueva_n = n_lineas - 1
        nuevos_pid = []
        nuevos_qty = []
        for j in range(n_lineas):
            if j == lineas_a_eliminar:
                continue
            nuevos_pid.append(st.session_state.get(f"cp_pid_{v}_{j}", ids_producto[0]))
            nuevos_qty.append(st.session_state.get(f"cp_qty_{v}_{j}", 1.0))
        new_v = v + 1
        st.session_state["cp_form_v"] = new_v
        st.session_state["cp_n_lineas"] = nueva_n
        for j, (p, q) in enumerate(zip(nuevos_pid, nuevos_qty)):
            st.session_state[f"cp_pid_{new_v}_{j}"] = p
            st.session_state[f"cp_qty_{new_v}_{j}"] = q
        st.rerun()

# ── Total y resumen ────────────────────────────────────────────────────────────

total_pedido = sum(line_totals)
st.markdown("---")

col_tot, col_btn = st.columns([2, 1])
with col_tot:
    st.markdown(
        f"<div style='background:#dcfce7;border:1px solid #86efac;border-radius:12px;"
        f"padding:16px 24px;display:inline-block;'>"
        f"<span style='font-size:14px;color:#166534;font-weight:500;'>Total del pedido</span><br>"
        f"<span style='font-size:28px;font-weight:700;color:#166534;'>{_fmt_cop(total_pedido)}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    guardar = st.button("Guardar Pedido", type="primary", use_container_width=True)

# ── Guardar ────────────────────────────────────────────────────────────────────

if guardar:
    n = int(st.session_state["cp_n_lineas"])
    lineas_ok: list[tuple[int, float, float, float]] = []
    error = False

    for i in range(n):
        pid_i = st.session_state.get(f"cp_pid_{v}_{i}")
        qty_i = st.session_state.get(f"cp_qty_{v}_{i}")
        if pid_i is None or qty_i is None:
            st.error("Datos incompletos. Revise las líneas del pedido.")
            error = True
            break
        q = float(qty_i)
        if q <= 0:
            st.error("La cantidad debe ser mayor que cero en todas las líneas.")
            error = True
            break
        p_id = int(pid_i)
        pu = precio_producto[p_id]
        lineas_ok.append((p_id, q, pu, q * pu))

    if not error:
        nuevo_id = _next_pedido_id(fecha_pedido)
        total_calc = sum(t[3] for t in lineas_ok)
        conn = get_connection()
        guardado_ok = False
        try:
            conn.execute(
                "INSERT INTO Pedidos (id, cliente_id, fecha, estado, total, notas) VALUES (?, ?, ?, 'pendiente', ?, NULL)",
                (nuevo_id, int(cliente_sel), fecha_pedido.isoformat(), total_calc),
            )
            for p_id, q, pu, sub in lineas_ok:
                conn.execute(
                    "INSERT INTO Detalle_Pedido (pedido_id, producto_id, cantidad, precio_unitario, subtotal) VALUES (?, ?, ?, ?, ?)",
                    (nuevo_id, p_id, q, pu, sub),
                )
            conn.commit()
            guardado_ok = True
        except Exception as exc:
            conn.rollback()
            st.error(f"No se pudo guardar el pedido: {exc}")
        finally:
            conn.close()

        if guardado_ok:
            st.session_state["cp_n_lineas"] = 1
            st.session_state["cp_form_v"] = v + 1
            st.session_state["cp_ok_msg"] = f"✅ Pedido creado correctamente: **{nuevo_id}**"
            st.rerun()