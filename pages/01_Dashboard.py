"""Dashboard principal."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.database import init_db, query_df

st.set_page_config(page_title="Dashboard Principal", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


# --- Métricas del día y pendientes ---
sql_pedidos_hoy = """
SELECT COUNT(*) AS n
FROM Pedidos
WHERE date(fecha) = date('now', 'localtime')
"""
sql_ingresos_hoy = """
SELECT COALESCE(SUM(monto), 0) AS total
FROM Pagos
WHERE estado = 'confirmado'
  AND date(fecha) = date('now', 'localtime')
"""
sql_pagos_pendientes = """
SELECT COALESCE(SUM(monto), 0) AS total
FROM Pagos
WHERE estado = 'pendiente'
"""

pedidos_hoy = int(query_df(sql_pedidos_hoy).iloc[0]["n"])
ingresos_hoy = float(query_df(sql_ingresos_hoy).iloc[0]["total"])
pagos_pend = float(query_df(sql_pagos_pendientes).iloc[0]["total"])

st.title("Dashboard Principal")

m1, m2, m3 = st.columns(3)
m1.metric("Pedidos del Día", f"{pedidos_hoy:,}".replace(",", "."))
m2.metric("Ingresos del Día", _fmt_cop(ingresos_hoy))
m3.metric("Pagos Pendientes", _fmt_cop(pagos_pend))

st.divider()

# --- Accesos rápidos ---
b1, b2, b3 = st.columns(3)
with b1:
    if st.button("Crear Nuevo Pedido", use_container_width=True, key="dash_nuevo_pedido"):
        st.switch_page("pages/03_Crear_Pedido.py")
with b2:
    if st.button(
        "Importar Pedido de WhatsApp",
        use_container_width=True,
        key="dash_wa",
    ):
        st.switch_page("pages/04_Importar_WhatsApp.py")
with b3:
    if st.button("Registrar Pago", use_container_width=True, key="dash_pago"):
        st.switch_page("pages/05_Registrar_Pago.py")

st.subheader("Actividad reciente")
sql_actividad = """
SELECT movimiento, referencia, fecha, estado, monto, metodo_pago
FROM (
    SELECT
        'Pedido' AS movimiento,
        p.id AS referencia,
        p.fecha AS fecha,
        p.estado AS estado,
        p.total AS monto,
        CAST(NULL AS TEXT) AS metodo_pago
    FROM Pedidos p
    WHERE date(p.fecha) = date('now', 'localtime')
    UNION ALL
    SELECT
        'Pago' AS movimiento,
        printf('%d', pg.id) AS referencia,
        pg.fecha AS fecha,
        pg.estado AS estado,
        pg.monto AS monto,
        pg.metodo_pago AS metodo_pago
    FROM Pagos pg
    WHERE date(pg.fecha) = date('now', 'localtime')
)
ORDER BY fecha DESC, movimiento DESC, referencia DESC
LIMIT 10
"""
df_act = query_df(sql_actividad)
if df_act.empty:
    st.info("No hay pedidos ni pagos registrados para hoy.")
else:
    df_show = df_act.rename(
        columns={
            "movimiento": "Movimiento",
            "referencia": "Referencia",
            "fecha": "Fecha",
            "estado": "Estado",
            "monto": "Monto (COP)",
            "metodo_pago": "Método pago",
        }
    )
    df_show["Monto (COP)"] = df_show["Monto (COP)"].apply(
        lambda x: _fmt_cop(x) if pd.notna(x) else ""
    )
    df_show["Método pago"] = df_show["Método pago"].fillna("—")
    st.dataframe(df_show, hide_index=True, use_container_width=True)

st.subheader("Ingresos semanales")
sql_semana = """
SELECT date(fecha) AS dia, COALESCE(SUM(monto), 0) AS ingresos
FROM Pagos
WHERE estado = 'confirmado'
  AND date(fecha) >= date('now', 'localtime', '-6 days')
  AND date(fecha) <= date('now', 'localtime')
GROUP BY date(fecha)
ORDER BY dia
"""
df_inc = query_df(sql_semana)
end = pd.Timestamp.now().normalize()
days = pd.date_range(end=end, periods=7, freq="D")
if df_inc.empty:
    plot_df = pd.DataFrame({"dia": days, "ingresos": 0.0})
else:
    df_inc["dia"] = pd.to_datetime(df_inc["dia"])
    plot_df = pd.DataFrame({"dia": days})
    plot_df = plot_df.merge(df_inc, on="dia", how="left")
    plot_df["ingresos"] = plot_df["ingresos"].fillna(0.0)

plot_df["dia_label"] = plot_df["dia"].dt.strftime("%d/%m")
fig = px.bar(
    plot_df,
    x="dia_label",
    y="ingresos",
    labels={"dia_label": "Día", "ingresos": "Ingresos (COP)"},
    text="ingresos",
)
fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
fig.update_layout(yaxis_tickformat=",.0f", showlegend=False, height=420)
st.plotly_chart(fig, use_container_width=True)
