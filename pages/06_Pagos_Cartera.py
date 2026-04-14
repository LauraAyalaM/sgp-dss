"""Pagos y cartera."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.database import init_db, query_df

st.set_page_config(page_title="Pagos y Cartera", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()


def _fmt_cop_metric(value: float | int) -> str:
    return f"$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- Métricas resumen ---
sql_cobrado_hoy = """
SELECT COALESCE(SUM(monto), 0) AS total
FROM Pagos
WHERE estado = 'confirmado'
  AND date(fecha) = date('now', 'localtime')
"""
sql_pendiente_total = """
SELECT COALESCE(SUM(saldo), 0) AS total
FROM (
    SELECT
        (
            p.total
            - COALESCE(
                SUM(
                    CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END
                ),
                0
            )
        ) AS saldo
    FROM Pedidos p
    LEFT JOIN Pagos pg ON pg.pedido_id = p.id
    WHERE p.estado != 'cancelado'
    GROUP BY p.id, p.total
    HAVING saldo > 0.001
) t
"""
sql_n_cartera = """
SELECT COUNT(*) AS n
FROM (
    SELECT p.id
    FROM Pedidos p
    LEFT JOIN Pagos pg ON pg.pedido_id = p.id
    WHERE p.estado != 'cancelado'
    GROUP BY p.id, p.total
    HAVING (
        p.total
        - COALESCE(
            SUM(
                CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END
            ),
            0
        )
    ) > 0.001
) u
"""

cobrado_hoy = float(query_df(sql_cobrado_hoy).iloc[0]["total"])
total_pendiente = float(query_df(sql_pendiente_total).iloc[0]["total"])
n_cartera = int(query_df(sql_n_cartera).iloc[0]["n"])

st.title("Pagos y Cartera")

m1, m2, m3 = st.columns(3)
m1.metric("Total cobrado hoy", _fmt_cop_metric(cobrado_hoy))
m2.metric("Total pendiente", _fmt_cop_metric(total_pendiente))
m3.metric("Pedidos en cartera", f"{n_cartera:,}".replace(",", "."))

st.divider()

# --- Lista de pagos ---
st.subheader("Lista de pagos")
df_pagos = query_df(
    """
    SELECT
        pg.id AS id_pago,
        pg.pedido_id AS pedido_asociado,
        pg.monto,
        pg.metodo_pago,
        pg.fecha,
        pg.estado
    FROM Pagos pg
    ORDER BY date(pg.fecha) DESC, pg.id DESC
    """
)
if df_pagos.empty:
    st.caption("No hay pagos registrados.")
else:
    df_pagos_show = df_pagos.rename(
        columns={
            "id_pago": "ID Pago",
            "pedido_asociado": "Pedido asociado",
            "monto": "Monto",
            "metodo_pago": "Método",
            "fecha": "Fecha",
            "estado": "Estado",
        }
    )
    st.dataframe(
        df_pagos_show,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Monto": st.column_config.NumberColumn("Monto (COP)", format="%d"),
        },
    )

st.divider()

# --- Cartera pendiente ---
st.subheader("Cartera pendiente")
st.caption(
    "La fecha de vencimiento se calcula como **7 días** después de la fecha del pedido. "
    "Las filas vencidas se resaltan en rojo."
)

df_cartera = query_df(
    """
    SELECT
        p.id AS id_pedido,
        c.nombre AS cliente,
        p.total AS monto_total,
        COALESCE(
            SUM(CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END),
            0
        ) AS monto_pagado,
        (
            p.total
            - COALESCE(
                SUM(CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END),
                0
            )
        ) AS pendiente,
        date(p.fecha, '+7 days') AS fecha_vencimiento
    FROM Pedidos p
    JOIN Clientes c ON c.id = p.cliente_id
    LEFT JOIN Pagos pg ON pg.pedido_id = p.id
    WHERE p.estado != 'cancelado'
    GROUP BY p.id, c.nombre, p.total, p.fecha
    HAVING (
        p.total
        - COALESCE(
            SUM(CASE WHEN pg.estado = 'confirmado' THEN pg.monto ELSE 0 END),
            0
        )
    ) > 0.001
    ORDER BY date(p.fecha) ASC, p.id ASC
    """
)

if df_cartera.empty:
    st.info("No hay pedidos con saldo pendiente.")
else:
    df_cartera = df_cartera.copy()
    fv = pd.to_datetime(df_cartera["fecha_vencimiento"], errors="coerce")
    hoy = pd.Timestamp.now().normalize()
    vencido = fv.dt.normalize() < hoy

    df_show = df_cartera.rename(
        columns={
            "id_pedido": "ID Pedido",
            "cliente": "Cliente",
            "monto_total": "Monto total",
            "monto_pagado": "Monto pagado",
            "pendiente": "Pendiente",
            "fecha_vencimiento": "Fecha vencimiento",
        }
    )

    def _style_vencidos(row: pd.Series) -> list[str]:
        es_v = bool(vencido.loc[row.name])
        estilo = (
            "background-color: #fecaca; color: #7f1d1d; font-weight: 600"
            if es_v
            else ""
        )
        return [estilo] * len(row)

    styled = df_show.style.apply(_style_vencidos, axis=1).format(
        {
            "Monto total": "{:,.0f}",
            "Monto pagado": "{:,.0f}",
            "Pendiente": "{:,.0f}",
        }
    )
    st.dataframe(styled, use_container_width=True)
