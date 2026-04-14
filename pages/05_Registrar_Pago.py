"""Registrar pago de un pedido."""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from utils.database import get_connection, init_db, query_df

st.set_page_config(page_title="Registrar Pago", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()

METODOS = ["efectivo", "transferencia", "QR"]


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cargar_pedidos_con_saldo() -> pd.DataFrame:
    return query_df(
        """
        SELECT
            p.id AS pedido_id,
            c.nombre AS cliente,
            p.total AS total_pedido,
            p.estado AS estado_pedido,
            (
                p.total
                - COALESCE(
                    SUM(
                        CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END
                    ),
                    0
                )
            ) AS saldo_pendiente
        FROM Pedidos p
        JOIN Clientes c ON c.id = p.cliente_id
        LEFT JOIN Pagos pg ON pg.pedido_id = p.id
        WHERE p.estado != 'cancelado'
        GROUP BY p.id, c.nombre, p.total, p.estado
        HAVING (
            p.total
            - COALESCE(
                SUM(
                    CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END
                ),
                0
            )
        ) > 0.001
        ORDER BY p.fecha DESC, p.id DESC
        """
    )


st.title("Registrar Pago")

if "rp_ok" in st.session_state:
    st.success(st.session_state.pop("rp_ok"))

df_ped = _cargar_pedidos_con_saldo()

if df_ped.empty:
    st.info("No hay pedidos con saldo pendiente (según pagos confirmados).")
    st.stop()

ids = [str(x) for x in df_ped["pedido_id"].tolist()]
labels = {
    str(r["pedido_id"]): (
        f"{r['pedido_id']} — {r['cliente']} — {_fmt_cop(r['total_pedido'])}"
    )
    for _, r in df_ped.iterrows()
}
totales = {str(r["pedido_id"]): float(r["total_pedido"]) for _, r in df_ped.iterrows()}
saldos = {str(r["pedido_id"]): float(r["saldo_pendiente"]) for _, r in df_ped.iterrows()}

pedido_sel = st.selectbox(
    "Pedido",
    ids,
    format_func=lambda pid: labels.get(str(pid), pid),
    key="rp_pedido",
)

total_ped = totales[str(pedido_sel)]
saldo_antes = saldos[str(pedido_sel)]

monto = st.number_input(
    "Monto",
    min_value=0.0,
    value=float(max(saldo_antes, 0.0)),
    step=500.0,
    format="%.0f",
    key="rp_monto",
)

metodo = st.selectbox("Método de pago", METODOS, key="rp_metodo")

referencia = st.text_input(
    "Referencia de pago (obligatoria si es transferencia)",
    key="rp_ref",
    disabled=(metodo != "transferencia"),
)

if metodo == "transferencia":
    st.caption("Debe indicar la referencia de la transferencia.")

if monto < total_ped:
    saldo_despues = max(0.0, saldo_antes - float(monto))
    st.warning(
        f"El monto ingresado ({_fmt_cop(monto)}) es menor al **total del pedido** "
        f"({_fmt_cop(total_ped)}). "
        f"Saldo pendiente antes de este pago: **{_fmt_cop(saldo_antes)}**. "
        f"Tras registrar este pago quedaría: **{_fmt_cop(saldo_despues)}**."
    )

if st.button("Guardar Pago"):
    if monto <= 0:
        st.error("El monto debe ser mayor que cero.")
    elif metodo == "transferencia" and not (referencia or "").strip():
        st.error("La referencia de pago es obligatoria para transferencia.")
    else:
        ref_val = (referencia or "").strip() if metodo == "transferencia" else None
        fecha_pago = date.today().isoformat()
        conn = get_connection()
        ok = False
        pagado = 0.0
        try:
            conn.execute(
                """
                INSERT INTO Pagos
                    (pedido_id, monto, metodo_pago, referencia_pago, fecha, estado)
                VALUES (?, ?, ?, ?, ?, 'confirmado')
                """,
                (pedido_sel, float(monto), metodo, ref_val, fecha_pago),
            )
            row = conn.execute(
                """
                SELECT COALESCE(SUM(monto), 0)
                FROM Pagos
                WHERE pedido_id = ? AND estado = 'confirmado'
                """,
                (pedido_sel,),
            ).fetchone()
            pagado = float(row[0]) if row else 0.0
            if pagado + 1e-6 >= total_ped:
                conn.execute(
                    "UPDATE Pedidos SET estado = 'entregado' WHERE id = ?",
                    (pedido_sel,),
                )
            conn.commit()
            ok = True
        except Exception as exc:
            conn.rollback()
            st.error(f"No se pudo guardar el pago: {exc}")
        finally:
            conn.close()
        if ok:
            st.session_state["rp_ok"] = (
                f"Pago registrado para el pedido {pedido_sel}. "
                + (
                    "El pedido quedó como entregado (pago completo)."
                    if pagado + 1e-6 >= total_ped
                    else "Estado del pedido sin cambio (pago parcial)."
                )
            )
            st.rerun()
