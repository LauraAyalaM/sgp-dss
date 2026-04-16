"""Cierre de Caja - Resumen diario y histórico."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import date

from utils.database import execute, init_db, query_df

st.set_page_config(page_title="Cierre de Caja", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _obtener_metricas_dia() -> dict:
    """Obtiene las métricas del día actual."""
    fecha_hoy = "date('now', 'localtime')"
    
    sql_ventas = f"""
    SELECT COALESCE(SUM(total), 0) AS total
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado != 'cancelado'
    """
    sql_pagos = f"""
    SELECT COALESCE(SUM(monto), 0) AS total
    FROM Pagos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'confirmado'
    """
    sql_pendientes = f"""
    SELECT COALESCE(SUM(total), 0) AS total
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'pendiente'
    """
    sql_cancelados = f"""
    SELECT COALESCE(SUM(total), 0) AS total
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'cancelado'
    """
    
    ventas = float(query_df(sql_ventas).iloc[0]["total"])
    pagos = float(query_df(sql_pagos).iloc[0]["total"])
    pendientes = float(query_df(sql_pendientes).iloc[0]["total"])
    cancelados = float(query_df(sql_cancelados).iloc[0]["total"])
    
    return {
        "ventas": ventas,
        "pagos": pagos,
        "pendientes": pendientes,
        "cancelaciones": cancelados,
    }


def _generar_cierre() -> tuple[bool, str]:
    """Genera el cierre de caja del día. Devuelve (éxito, mensaje)."""
    from utils.database import get_connection
    
    fecha_hoy = "date('now', 'localtime')"
    
    sql_existe = f"SELECT id FROM Cierre_Caja WHERE fecha = {fecha_hoy}"
    if not query_df(sql_existe).empty:
        return False, "Ya existe un cierre de caja para el día de hoy."
    
    sql_ventas = f"""
    SELECT COALESCE(SUM(total), 0) AS total, COUNT(*) AS n
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado != 'cancelado'
    """
    sql_pagos = f"""
    SELECT COALESCE(SUM(monto), 0) AS total
    FROM Pagos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'confirmado'
    """
    sql_pendientes = f"""
    SELECT COALESCE(SUM(total), 0) AS total
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'pendiente'
    """
    sql_entregados = f"""
    SELECT COUNT(*) AS n
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'entregado'
    """
    sql_cancelados = f"""
    SELECT COUNT(*) AS n
    FROM Pedidos
    WHERE date(fecha) = {fecha_hoy}
      AND estado = 'cancelado'
    """
    
    df_ventas = query_df(sql_ventas)
    df_pagos = query_df(sql_pagos)
    df_pendientes = query_df(sql_pendientes)
    df_entregados = query_df(sql_entregados)
    df_cancelados = query_df(sql_cancelados)
    
    total_ventas = float(df_ventas.iloc[0]["total"])
    total_pedidos = int(df_ventas.iloc[0]["n"])
    total_pagos = float(df_pagos.iloc[0]["total"])
    total_pendiente = float(df_pendientes.iloc[0]["total"])
    pedidos_entregados = int(df_entregados.iloc[0]["n"])
    pedidos_cancelados = int(df_cancelados.iloc[0]["n"])
    
    sql_insert = """
    INSERT INTO Cierre_Caja (
        fecha, total_ventas, total_pagos_recibidos, total_pendiente,
        total_pedidos, pedidos_entregados, pedidos_cancelados
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    
    conn = get_connection()
    try:
        conn.execute(sql_insert, (
            pd.Timestamp.now().strftime("%Y-%m-%d"),
            total_ventas,
            total_pagos,
            total_pendiente,
            total_pedidos,
            pedidos_entregados,
            pedidos_cancelados,
        ))
        conn.commit()
    finally:
        conn.close()
    
    return True, "Cierre de caja generado correctamente."


def _obtener_transacciones_dia() -> pd.DataFrame:
    """Obtiene las transacciones del día."""
    sql = """
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
    ORDER BY fecha DESC
    """
    return query_df(sql)


def _obtener_ventas_por_hora() -> pd.DataFrame:
    """Obtiene las ventas por hora del día."""
    sql = """
    SELECT strftime('%H', fecha) AS hora, COALESCE(SUM(total), 0) AS ventas
    FROM Pedidos
    WHERE date(fecha) = date('now', 'localtime')
      AND estado != 'cancelado'
    GROUP BY strftime('%H', fecha)
    ORDER BY hora
    """
    return query_df(sql)


def _obtener_cierres_rango(fecha_inicio: str, fecha_fin: str) -> pd.DataFrame:
    """Obtiene los cierres en un rango de fechas."""
    sql = """
    SELECT
        fecha, total_ventas, total_pagos_recibidos, total_pendiente,
        total_pedidos, pedidos_entregados, pedidos_cancelados
    FROM Cierre_Caja
    WHERE date(fecha) >= date(?)
      AND date(fecha) <= date(?)
    ORDER BY fecha DESC
    """
    return query_df(sql, (fecha_inicio, fecha_fin))


st.title("Cierre de Caja")

metricas = _obtener_metricas_dia()

m1, m2, m3, m4 = st.columns(4)
m1.metric("Ventas del Día", _fmt_cop(metricas["ventas"]))
m2.metric("Pagos Recibidos", _fmt_cop(metricas["pagos"]))
m3.metric("Pendientes", _fmt_cop(metricas["pendientes"]))
m4.metric("Cancelaciones", _fmt_cop(metricas["cancelaciones"]))

st.divider()

c1, c2 = st.columns(2)
with c1:
    if st.button("Generar Cierre", use_container_width=True, key="btn_generar_cierre"):
        exito, mensaje = _generar_cierre()
        if exito:
            st.success(mensaje)
        else:
            st.error(mensaje)
with c2:
    df_trans = _obtener_transacciones_dia()
    if df_trans.empty:
        st.button(
            "Exportar Reporte",
            disabled=True,
            use_container_width=True,
            key="btn_exportar_disabled",
        )
    else:
        csv = df_trans.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Exportar Reporte",
            data=csv,
            file_name=f"cierre_caja_{pd.Timestamp.now().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_exportar",
        )

st.divider()

st.subheader("Transacciones del Día")
if df_trans.empty:
    st.info("No hay transacciones registradas para hoy.")
else:
    df_show = df_trans.rename(
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

st.subheader("Ventas por Hora")
df_hora = _obtener_ventas_por_hora()
if df_hora.empty:
    st.info("No hay ventas registradas para hoy.")
else:
    df_hora["hora"] = df_hora["hora"].astype(int)
    horas = list(range(0, 24))
    plot_df = pd.DataFrame({"hora": horas})
    plot_df = plot_df.merge(df_hora, on="hora", how="left")
    plot_df["ventas"] = plot_df["ventas"].fillna(0.0)
    
    fig = px.bar(
        plot_df,
        x="hora",
        y="ventas",
        labels={"hora": "Hora", "ventas": "Ventas (COP)"},
        text="ventas",
    )
    fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
    fig.update_layout(
         xaxis_tickmode="linear",
         xaxis_tick0=0,
         xaxis_dtick=1,   # <-- era dx=1, el correcto es xaxis_dtick
         yaxis_tickformat=",.0f",
         showlegend=False,
         height=400,
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

st.subheader("Histórico de Cierres")
fecha_defecto = date.today()
mes_anterior = fecha_defecto.month - 1 if fecha_defecto.month > 1 else 12
anno_anterior = fecha_defecto.year if fecha_defecto.month > 1 else fecha_defecto.year - 1
fecha_inicio = st.date_input(
    "Desde",
    value=date(anno_anterior, mes_anterior, fecha_defecto.day),
    key="fecha_inicio",
)
fecha_fin = st.date_input(
    "Hasta",
    value=fecha_defecto,
    key="fecha_fin",
)

if fecha_inicio and fecha_fin:
    df_cierres = _obtener_cierres_rango(
        fecha_inicio.strftime("%Y-%m-%d"),
        fecha_fin.strftime("%Y-%m-%d"),
    )
    if df_cierres.empty:
        st.info("No hay cierres en el período seleccionado.")
    else:
        df_show = df_cierres.rename(
            columns={
                "fecha": "Fecha",
                "total_ventas": "Ventas (COP)",
                "total_pagos_recibidos": "Pagos (COP)",
                "total_pendiente": "Pendiente (COP)",
                "total_pedidos": "Pedidos",
                "pedidos_entregados": "Entregados",
                "pedidos_cancelados": "Cancelados",
            }
        )
        df_show["Ventas (COP)"] = df_show["Ventas (COP)"].apply(_fmt_cop)
        df_show["Pagos (COP)"] = df_show["Pagos (COP)"].apply(_fmt_cop)
        df_show["Pendiente (COP)"] = df_show["Pendiente (COP)"].apply(_fmt_cop)
        st.dataframe(df_show, hide_index=True, use_container_width=True)