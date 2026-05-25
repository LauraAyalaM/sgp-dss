"""Reportes y Análisis."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st
from datetime import date, timedelta

from utils.database import init_db, query_df
from utils.ml_service import segmentar_clientes
from utils.sidebar import render_sidebar

st.set_page_config(page_title="Reportes y Análisis", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

if st.session_state.get("rol") != "admin":
    st.error("No tienes permiso para acceder a esta página.")
    st.stop()

render_sidebar()
init_db()


def _fmt_cop(value: float | int) -> str:
    return f"$ {float(value):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _obtener_categorias() -> list[str]:
    df = query_df("SELECT DISTINCT categoria FROM Productos WHERE categoria IS NOT NULL")
    return df["categoria"].tolist() if not df.empty else []


def _obtener_productos_top(fecha_inicio: str, fecha_fin: str, categoria: str | None) -> pd.DataFrame:
    sql = """
    SELECT 
        p.nombre AS producto,
        p.categoria,
        SUM(dp.cantidad) AS cantidad_vendida,
        SUM(dp.subtotal) AS ingreso
    FROM Detalle_Pedido dp
    JOIN Productos p ON dp.producto_id = p.id
    JOIN Pedidos pe ON dp.pedido_id = pe.id
    WHERE date(pe.fecha) >= date(?)
      AND date(pe.fecha) <= date(?)
      AND pe.estado != 'cancelado'
    """
    params = [fecha_inicio, fecha_fin]
    
    if categoria:
        sql += " AND p.categoria = ?"
        params.append(categoria)
    
    sql += """
    GROUP BY p.id
    ORDER BY cantidad_vendida DESC
    LIMIT 5
    """
    return query_df(sql, params)


def _obtener_ventas_mensuales() -> pd.DataFrame:
    sql = """
    SELECT 
        strftime('%Y-%m', fecha) AS mes,
        COUNT(*) AS pedidos,
        SUM(total) AS ventas
    FROM Pedidos
    WHERE estado != 'cancelado'
    GROUP BY strftime('%Y-%m', fecha)
    ORDER BY mes
    """
    return query_df(sql)


def _obtener_clientes_frecuentes() -> pd.DataFrame:
    sql = """
    SELECT 
        c.nombre AS cliente,
        COUNT(p.id) AS pedidos,
        COALESCE(SUM(p.total), 0) AS monto_total
    FROM Clientes c
    JOIN Pedidos p ON c.id = p.cliente_id
    WHERE p.estado != 'cancelado'
    GROUP BY c.id
    ORDER BY monto_total DESC
    """
    return query_df(sql)


st.title("Reportes y Análisis")

tab1, tab2, tab3, tab4 = st.tabs([
    "Productos más vendidos",
    "Ventas por fecha",
    "Clientes frecuentes",
    "Descargar reporte PDF",
])

with tab1:
    st.subheader("Top 5 Productos más Vendidos")
    
    col_filtro1, col_filtro2 = st.columns(2)
    with col_filtro1:
        categorias = _obtener_categorias()
        cat_seleccionada = st.selectbox("Categoría", ["Todas"] + categorias, key="cat_productos")
    with col_filtro2:
        hoy = date.today()
        inicio_default = hoy - timedelta(days=30)
        fecha_inicio = st.date_input("Desde", value=inicio_default, key="prod_fecha_inicio")
        fecha_fin = st.date_input("Hasta", value=hoy, key="prod_fecha_fin")
    
    cat_filter = None if cat_seleccionada == "Todas" else cat_seleccionada
    
    if fecha_inicio and fecha_fin:
        df_top = _obtener_productos_top(
            fecha_inicio.strftime("%Y-%m-%d"),
            fecha_fin.strftime("%Y-%m-%d"),
            cat_filter,
        )
        
        if df_top.empty:
            st.info("No hay datos en el período seleccionado.")
        else:
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("**Por Cantidad**")
                fig_cant = px.bar(
                    df_top.sort_values("cantidad_vendida", ascending=True),
                    x="cantidad_vendida",
                    y="producto",
                    orientation="h",
                    labels={"cantidad_vendida": "Cantidad", "producto": "Producto"},
                    text="cantidad_vendida",
                )
                fig_cant.update_traces(textposition="outside")
                st.plotly_chart(fig_cant, use_container_width=True)
            
            with c2:
                st.markdown("**Por Ingreso**")
                fig_ing = px.bar(
                    df_top.sort_values("ingreso", ascending=True),
                    x="ingreso",
                    y="producto",
                    orientation="h",
                    labels={"ingreso": "Ingreso (COP)", "producto": "Producto"},
                    text="ingreso",
                )
                fig_ing.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
                fig_ing.update_layout(xaxis_tickformat=",.0f")
                st.plotly_chart(fig_ing, use_container_width=True)


with tab2:
    st.subheader("Ventas por Mes")
    
    df_mensual = _obtener_ventas_mensuales()
    
    if df_mensual.empty:
        st.info("No hay datos de ventas.")
    else:
        df_mensual["mes"] = pd.to_datetime(df_mensual["mes"])
        df_mensual["anio_mes"] = df_mensual["mes"].dt.strftime("%Y-%m")
        df_mensual["mes_nombre"] = df_mensual["mes"].dt.strftime("%b %Y")
        
        def get_fechas_especiales(mes: int) -> str | None:
            especiales = {
                5: "Día de la Madre",
                6: "Día del Padre",
                9: "Amor y Amistad",
                12: "Navidad",
            }
            return especiales.get(mes)
        
        df_mensual["fecha_especial"] = df_mensual["mes"].dt.month.apply(get_fechas_especiales)
        
        fig = px.line(
            df_mensual,
            x="mes_nombre",
            y="ventas",
            markers=True,
            labels={"mes_nombre": "Mes", "ventas": "Ventas (COP)"},
        )
        fig.update_traces(mode="lines+markers+text", textposition="top center")
        fig.update_layout(
            yaxis_tickformat=",.0f",
            xaxis_title=None,
            height=450,
        )
        
        for idx, row in df_mensual.iterrows():
            fecha_especial = row["fecha_especial"]
            if pd.notna(fecha_especial) and fecha_especial:
                fig.add_annotation(
                    x=row["mes_nombre"],
                    y=row["ventas"],
                    text=f"★ {row['fecha_especial']}",
                    showarrow=True,
                    arrowhead=2,
                    arrowsize=1,
                    ax=0,
                    ay=-30,
                    font=dict(color="red", size=10),
                )
        
        st.plotly_chart(fig, use_container_width=True)
        
        st.caption("★ Indica fechas especiales: Mayo (Día de la Madre), Junio (Día del Padre), Septiembre (Amor y Amistad), Diciembre (Navidad)")


with tab3:
    st.subheader("Clientes Frecuentes")
    
    df_clientes = _obtener_clientes_frecuentes()
    
    if df_clientes.empty:
        st.info("No hay clientes con pedidos.")
    else:
        df_segmentado = segmentar_clientes()
        
        if df_segmentado.empty:
            st.warning("No hay datos suficientes para segmentación. Entrena los modelos primero.")
        else:
            # Las columnas del modelo: total_compras, frecuencia_pedidos, segmento, etiqueta
            df_show = df_segmentado.rename(
                columns={
                    "total_compras": "Monto Total (COP)",
                    "frecuencia_pedidos": "Pedidos",
                    "etiqueta": "Segmento",
                }
            )
            
            if "Monto Total (COP)" in df_show.columns:
                df_show["Monto Total (COP)"] = df_show["Monto Total (COP)"].apply(_fmt_cop)
            
            # Seleccionar columnas relevantes para mostrar
            columnas_mostrar = ["Monto Total (COP)", "Pedidos", "Segmento"]
            df_display = df_show[[c for c in columnas_mostrar if c in df_show.columns]]
            
            col_info, col_tabla = st.columns([1, 3])
            
            with col_info:
                st.markdown("**Segmentación KMeans**")
                st.markdown("- **Alto valor**: clientes con más pedidos y mayor gasto")
                st.markdown("- **Medio valor**: clientes con actividad moderada")
                st.markdown("- **Bajo valor**: clientes con poco consumo")
            
            with col_tabla:
                st.dataframe(df_display, hide_index=True, use_container_width=True)

with tab4:
    from utils.pdf_report import generar_reporte_pdf  # type: ignore
 
    st.subheader("Descargar Reporte PDF")
    st.markdown(
        "Genera un reporte completo en PDF con KPIs, ventas por día, "
        "productos más vendidos, métodos de pago y clientes destacados."
    )
 
    # ── Selector de rango rápido ──────────────────────────────────────────
    hoy = date.today()
 
    col_rango, col_custom = st.columns([2, 3])
 
    with col_rango:
        rango = st.selectbox(
            "Rango predefinido",
            ["Hoy", "Ayer", "Últimos 7 días", "Últimos 30 días",
             "Este mes", "Mes anterior", "Personalizado"],
            index=2,
            key="pdf_rango",
        )
 
    # Calcular fechas según rango
    if rango == "Hoy":
        f_ini_default, f_fin_default = hoy, hoy
    elif rango == "Ayer":
        ayer = hoy - timedelta(days=1)
        f_ini_default, f_fin_default = ayer, ayer
    elif rango == "Últimos 7 días":
        f_ini_default = hoy - timedelta(days=6)
        f_fin_default = hoy
    elif rango == "Últimos 30 días":
        f_ini_default = hoy - timedelta(days=29)
        f_fin_default = hoy
    elif rango == "Este mes":
        f_ini_default = hoy.replace(day=1)
        f_fin_default = hoy
    elif rango == "Mes anterior":
        primer_dia_mes = hoy.replace(day=1)
        ultimo_mes = primer_dia_mes - timedelta(days=1)
        f_ini_default = ultimo_mes.replace(day=1)
        f_fin_default = ultimo_mes
    else:  # Personalizado
        f_ini_default = hoy - timedelta(days=6)
        f_fin_default = hoy
 
    with col_custom:
        if rango == "Personalizado":
            c1, c2 = st.columns(2)
            with c1:
                f_ini = st.date_input("Desde", value=f_ini_default, key="pdf_ini")
            with c2:
                f_fin = st.date_input("Hasta", value=f_fin_default, key="pdf_fin")
        else:
            f_ini, f_fin = f_ini_default, f_fin_default
            st.info(
                f"Período: **{f_ini.strftime('%d/%m/%Y')}** — **{f_fin.strftime('%d/%m/%Y')}**"
            )
 
    # ── Vista previa de métricas ──────────────────────────────────────────
    if f_ini <= f_fin:
        from utils.database import query_df  # ya importado arriba, pero por si acaso
 
        df_prev = query_df(
            """
            SELECT
                COUNT(*)                    AS pedidos,
                COALESCE(SUM(total), 0)     AS ingresos,
                COALESCE(AVG(total), 0)     AS ticket
            FROM Pedidos
            WHERE date(fecha) BETWEEN date(?) AND date(?)
              AND estado != 'cancelado'
            """,
            (f_ini.strftime("%Y-%m-%d"), f_fin.strftime("%Y-%m-%d")),
        )
 
        if not df_prev.empty:
            row = df_prev.iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("Pedidos en el período", int(row["pedidos"]))
            m2.metric("Ingresos", _fmt_cop(float(row["ingresos"])))
            m3.metric("Ticket promedio", _fmt_cop(float(row["ticket"])))
 
        # ── Botón de descarga ─────────────────────────────────────────────
        st.divider()
        nombre_archivo = (
            f"reporte_{f_ini.strftime('%Y%m%d')}_{f_fin.strftime('%Y%m%d')}.pdf"
        )
 
        if st.button("Generar PDF", type="primary", key="pdf_generar"):
            with st.spinner("Generando reporte…"):
                try:
                    pdf_bytes = generar_reporte_pdf(
                        fecha_inicio=f_ini,
                        fecha_fin=f_fin,
                        nombre_negocio="SGP-DSS",
                    )
                    st.session_state["pdf_bytes"]   = pdf_bytes
                    st.session_state["pdf_archivo"] = nombre_archivo
                    st.success("¡Reporte listo! Haz clic en Descargar.")
                except Exception as e:
                    st.error(f"Error al generar el PDF: {e}")
 
        if "pdf_bytes" in st.session_state:
            st.download_button(
                label="Descargar PDF",
                data=st.session_state["pdf_bytes"],
                file_name=st.session_state["pdf_archivo"],
                mime="application/pdf",
                type="primary",
            )
    else:
        st.warning("La fecha de inicio debe ser anterior o igual a la fecha de fin.")