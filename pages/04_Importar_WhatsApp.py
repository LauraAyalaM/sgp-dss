"""Importar pedido desde mensaje de WhatsApp."""

from __future__ import annotations

import html
from datetime import date

import pandas as pd
import streamlit as st

from utils.database import get_connection, init_db, query_df
from utils.wa_parser import parse_whatsapp_message_items

st.set_page_config(page_title="Importar WhatsApp", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()

_COLS = ["Producto", "Cantidad", "Precio Unitario", "Total"]


def _badge_html(kind: str, texto: str) -> str:
    safe = html.escape(texto)
    styles = {
        "ok": ("#166534", "#dcfce7"),
        "warning": ("#a16207", "#fef9c3"),
        "error": ("#991b1b", "#fecaca"),
    }
    fg, bg = styles.get(kind, ("#374151", "#e5e7eb"))
    return (
        f'<span style="display:inline-block;background-color:{bg};color:{fg};'
        f"padding:4px 12px;border-radius:999px;font-size:13px;font-weight:600;"
        f'border:1px solid rgba(0,0,0,0.06);">{safe}</span>'
    )


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


def _resolver_producto_id(nombre_producto: str) -> int | None:
    nombre = (nombre_producto or "").strip()
    if not nombre:
        return None
    df = query_df(
        "SELECT id FROM Productos WHERE TRIM(nombre) = TRIM(?) COLLATE NOCASE LIMIT 1",
        (nombre,),
    )
    if not df.empty:
        return int(df.iloc[0]["id"])
    df_like = query_df(
        "SELECT id FROM Productos WHERE nombre LIKE ? COLLATE NOCASE LIMIT 1",
        (f"%{nombre}%",),
    )
    if not df_like.empty:
        return int(df_like.iloc[0]["id"])
    return None


def _resolver_o_crear_cliente(nombre: str) -> int:
    nombre = nombre.strip()
    df = query_df(
        "SELECT id FROM Clientes WHERE nombre = ? COLLATE NOCASE LIMIT 1",
        (nombre,),
    )
    if not df.empty:
        return int(df.iloc[0]["id"])
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO Clientes (nombre, canal, tipo_cliente, fecha_registro)
            VALUES (?, 'whatsapp', 'minorista', ?)
            """,
            (nombre, date.today().isoformat()),
        )
        conn.commit()
        cur = conn.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])
    finally:
        conn.close()


st.title("Importar desde WhatsApp")

if "wa_ok_msg" in st.session_state:
    st.success(st.session_state.pop("wa_ok_msg"))

msg = st.text_area(
    "Pegue aquí el mensaje del pedido",
    height=220,
    placeholder="Ejemplo:\n2 x Arepa con huevo y café 9000\n1 x Combo ejecutivo 19000",
    key="wa_text_area",
)

if st.button("Procesar Mensaje"):
    res = parse_whatsapp_message_items(msg)
    st.session_state["wa_parse_badge"] = res["badge"]
    st.session_state["wa_parse_msg"] = res["mensaje"]
    items = res.get("items") or []
    st.session_state["wa_df"] = (
        pd.DataFrame(items, columns=_COLS) if items else pd.DataFrame(columns=_COLS)
    )
    st.session_state.pop("wa_df_last", None)
    st.session_state["wa_editor_v"] = int(st.session_state.get("wa_editor_v", 0)) + 1
    st.rerun()

if "wa_parse_badge" in st.session_state:
    b = st.session_state["wa_parse_badge"]
    label = {"ok": "Listo", "warning": "Atención", "error": "Error"}.get(b, b)
    st.markdown(
        f"**Estado:** {_badge_html(b, label)} — {html.escape(st.session_state.get('wa_parse_msg', ''))}",
        unsafe_allow_html=True,
    )

v = int(st.session_state.get("wa_editor_v", 0))
df_edit = st.session_state.get("wa_df")
if df_edit is None or (isinstance(df_edit, pd.DataFrame) and df_edit.empty):
    st.info("Procese un mensaje para ver y editar los productos detectados.")
else:
    edited = st.data_editor(
        df_edit,
        column_config={
            "Producto": st.column_config.TextColumn("Producto", width="large"),
            "Cantidad": st.column_config.NumberColumn("Cantidad", min_value=0.01, step=0.5),
            "Precio Unitario": st.column_config.NumberColumn(
                "Precio Unitario",
                min_value=0.0,
                format="%d",
            ),
            "Total": st.column_config.NumberColumn("Total", min_value=0.0, format="%d"),
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key=f"wa_editor_{v}",
    )
    st.session_state["wa_df_last"] = edited

st.divider()
cn1, cn2 = st.columns(2)
with cn1:
    nombre_cliente = st.text_input("Nombre del Cliente", key="wa_nombre_cliente")
with cn2:
    fecha_pedido = st.date_input("Fecha del Pedido", value=date.today(), key="wa_fecha_pedido")

if st.button("Confirmar Pedido"):
    tab = st.session_state.get("wa_df_last")
    if tab is None:
        tab = st.session_state.get("wa_df")
    if tab is None or tab.empty:
        st.error("No hay productos para confirmar. Procese un mensaje primero.")
    elif not (nombre_cliente or "").strip():
        st.error("Indique el nombre del cliente.")
    else:
        df_ok = tab.copy()
        for c in _COLS:
            if c not in df_ok.columns:
                st.error(f"Falta la columna «{c}» en la tabla.")
                st.stop()
        df_ok["Cantidad"] = pd.to_numeric(df_ok["Cantidad"], errors="coerce").fillna(0)
        df_ok["Precio Unitario"] = pd.to_numeric(
            df_ok["Precio Unitario"], errors="coerce"
        ).fillna(0)
        df_ok["Total"] = df_ok["Cantidad"] * df_ok["Precio Unitario"]
        filas = df_ok[
            (df_ok["Producto"].astype(str).str.strip() != "") & (df_ok["Cantidad"] > 0)
        ]
        if filas.empty:
            st.error("Debe haber al menos una línea con producto y cantidad válidos.")
        else:
            sin_match: list[str] = []
            lineas: list[tuple[int, float, float, float]] = []
            for _, r in filas.iterrows():
                nom = str(r["Producto"]).strip()
                pid = _resolver_producto_id(nom)
                if pid is None:
                    sin_match.append(nom)
                    continue
                q = float(r["Cantidad"])
                pu = float(r["Precio Unitario"])
                sub = q * pu
                lineas.append((pid, q, pu, sub))
            if sin_match:
                st.error(
                    "No se encontró en catálogo: "
                    + ", ".join(f"«{s}»" for s in sin_match)
                )
            elif not lineas:
                st.error("No hay líneas válidas para insertar.")
            else:
                nuevo_id = _next_pedido_id(fecha_pedido)
                total_calc = sum(t[3] for t in lineas)
                cid = _resolver_o_crear_cliente(nombre_cliente)
                conn = get_connection()
                guardado = False
                try:
                    conn.execute(
                        """
                        INSERT INTO Pedidos
                            (id, cliente_id, fecha, estado, total, notas, estado_importacion)
                        VALUES (?, ?, ?, 'pendiente', ?, NULL, 'procesado')
                        """,
                        (
                            nuevo_id,
                            cid,
                            fecha_pedido.isoformat(),
                            total_calc,
                        ),
                    )
                    for p_id, q, pu, sub in lineas:
                        conn.execute(
                            """
                            INSERT INTO Detalle_Pedido
                                (pedido_id, producto_id, cantidad, precio_unitario, subtotal)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (nuevo_id, p_id, q, pu, sub),
                        )
                    conn.commit()
                    guardado = True
                except Exception as exc:
                    conn.rollback()
                    st.error(f"No se pudo guardar el pedido: {exc}")
                finally:
                    conn.close()
                if guardado:
                    st.session_state.pop("wa_df", None)
                    st.session_state.pop("wa_df_last", None)
                    st.session_state.pop("wa_parse_badge", None)
                    st.session_state.pop("wa_parse_msg", None)
                    st.session_state["wa_editor_v"] = (
                        int(st.session_state.get("wa_editor_v", 0)) + 1
                    )
                    st.session_state["wa_ok_msg"] = (
                        f"Pedido importado: {nuevo_id} (estado_importación: procesado)."
                    )
                    st.rerun()
