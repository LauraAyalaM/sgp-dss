"""
utils/pdf_report.py
-------------------
Genera reportes PDF de ventas usando reportlab.
Se importa desde 08_Reportes.py.

Uso:
    from utils.pdf_report import generar_reporte_pdf
    pdf_bytes = generar_reporte_pdf(fecha_inicio, fecha_fin, titulo)
    st.download_button("Descargar PDF", pdf_bytes, "reporte.pdf", "application/pdf")
"""

from __future__ import annotations

import io
from datetime import date, datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)


# ── Paleta de colores del negocio ─────────────────────────────────────────
COLOR_PRIMARY   = colors.HexColor("#694141")   # azul oscuro — encabezados
COLOR_ACCENT    = colors.HexColor("#2e7d52")   # verde — métricas positivas
COLOR_LIGHT     = colors.HexColor("#f0f4f8")   # gris muy claro — filas alternas
COLOR_BORDER    = colors.HexColor("#d0d7de")   # borde de tablas
COLOR_TEXT      = colors.HexColor("#1f2328")   # texto principal
COLOR_SECONDARY = colors.HexColor("#8b5359")   # texto secundario


def _fmt_cop(valor: float) -> str:
    return f"$ {float(valor):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Llama a query_df del proyecto."""
    from utils.database import query_df  # type: ignore
    return query_df(sql, params)


# ── Consultas de datos ────────────────────────────────────────────────────

def _metricas_generales(f_ini: str, f_fin: str) -> dict:
    df = _query(
        """
        SELECT
            COUNT(*)                          AS total_pedidos,
            COALESCE(SUM(total), 0)           AS ingresos_totales,
            COALESCE(AVG(total), 0)           AS ticket_promedio,
            SUM(CASE WHEN estado='cancelado' THEN 1 ELSE 0 END) AS cancelados
        FROM Pedidos
        WHERE date(fecha) BETWEEN date(?) AND date(?)
        """,
        (f_ini, f_fin),
    )
    row = df.iloc[0] if not df.empty else {}
    return {
        "total_pedidos":    int(row.get("total_pedidos", 0)),
        "ingresos_totales": float(row.get("ingresos_totales", 0)),
        "ticket_promedio":  float(row.get("ticket_promedio", 0)),
        "cancelados":       int(row.get("cancelados", 0)),
    }


def _top_productos(f_ini: str, f_fin: str, n: int = 8) -> pd.DataFrame:
    return _query(
        f"""
        SELECT
            p.nombre,
            p.categoria,
            SUM(dp.cantidad)  AS unidades,
            SUM(dp.subtotal)  AS ingreso
        FROM Detalle_Pedido dp
        JOIN Productos p  ON dp.producto_id = p.id
        JOIN Pedidos pe   ON dp.pedido_id   = pe.id
        WHERE date(pe.fecha) BETWEEN date(?) AND date(?)
          AND pe.estado != 'cancelado'
        GROUP BY p.id
        ORDER BY unidades DESC
        LIMIT {n}
        """,
        (f_ini, f_fin),
    )


def _ventas_por_dia(f_ini: str, f_fin: str) -> pd.DataFrame:
    return _query(
        """
        SELECT
            date(fecha)   AS dia,
            COUNT(*)      AS pedidos,
            SUM(total)    AS ventas
        FROM Pedidos
        WHERE date(fecha) BETWEEN date(?) AND date(?)
          AND estado != 'cancelado'
        GROUP BY date(fecha)
        ORDER BY dia
        """,
        (f_ini, f_fin),
    )


def _metodos_pago(f_ini: str, f_fin: str) -> pd.DataFrame:
    return _query(
        """
        SELECT
            pg.metodo_pago,
            COUNT(*)          AS transacciones,
            SUM(pg.monto)     AS total
        FROM Pagos pg
        JOIN Pedidos pe ON pg.pedido_id = pe.id
        WHERE date(pe.fecha) BETWEEN date(?) AND date(?)
        GROUP BY pg.metodo_pago
        ORDER BY total DESC
        """,
        (f_ini, f_fin),
    )


def _top_clientes(f_ini: str, f_fin: str, n: int = 5) -> pd.DataFrame:
    return _query(
        f"""
        SELECT
            c.nombre,
            COUNT(pe.id)      AS pedidos,
            SUM(pe.total)     AS total
        FROM Clientes c
        JOIN Pedidos pe ON c.id = pe.cliente_id
        WHERE date(pe.fecha) BETWEEN date(?) AND date(?)
          AND pe.estado != 'cancelado'
        GROUP BY c.id
        ORDER BY total DESC
        LIMIT {n}
        """,
        (f_ini, f_fin),
    )


# ── Constructores de elementos PDF ────────────────────────────────────────

def _estilos():
    base = getSampleStyleSheet()
    estilos = {
        "titulo": ParagraphStyle(
            "titulo",
            parent=base["Title"],
            fontSize=20,
            textColor=COLOR_PRIMARY,
            spaceAfter=4,
            fontName="Helvetica-Bold",
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo",
            parent=base["Normal"],
            fontSize=10,
            textColor=COLOR_SECONDARY,
            spaceAfter=2,
        ),
        "seccion": ParagraphStyle(
            "seccion",
            parent=base["Heading2"],
            fontSize=12,
            textColor=COLOR_PRIMARY,
            spaceBefore=14,
            spaceAfter=6,
            fontName="Helvetica-Bold",
        ),
        "normal": ParagraphStyle(
            "normal",
            parent=base["Normal"],
            fontSize=9,
            textColor=COLOR_TEXT,
            leading=13,
        ),
        "pie": ParagraphStyle(
            "pie",
            parent=base["Normal"],
            fontSize=8,
            textColor=COLOR_SECONDARY,
            alignment=1,
        ),
    }
    return estilos


def _tabla_metricas(metricas: dict, estilos: dict) -> Table:
    """Fila de 4 tarjetas de KPI."""
    completados = metricas["total_pedidos"] - metricas["cancelados"]
    datos = [
        ["PEDIDOS COMPLETADOS", "INGRESOS TOTALES",   "TICKET PROMEDIO",          "CANCELADOS"],
        [
            str(completados),
            _fmt_cop(metricas["ingresos_totales"]),
            _fmt_cop(metricas["ticket_promedio"]),
            str(metricas["cancelados"]),
        ],
    ]
    ancho_col = [4.5 * cm] * 4
    t = Table(datos, colWidths=ancho_col, rowHeights=[18, 28])
    t.setStyle(TableStyle([
        # Encabezados
        ("BACKGROUND",   (0, 0), (-1, 0), COLOR_PRIMARY),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 7),
        ("ALIGN",        (0, 0), (-1, 0), "CENTER"),
        ("VALIGN",       (0, 0), (-1, 0), "MIDDLE"),
        # Valores
        ("BACKGROUND",   (0, 1), (-1, 1), COLOR_LIGHT),
        ("FONTNAME",     (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 1), (-1, 1), 14),
        ("TEXTCOLOR",    (0, 1), (-1, 1), COLOR_ACCENT),
        ("ALIGN",        (0, 1), (-1, 1), "CENTER"),
        ("VALIGN",       (0, 1), (-1, 1), "MIDDLE"),
        ("TEXTCOLOR",    (3, 1), (3, 1),  colors.HexColor("#c0392b")),
        # Bordes
        ("BOX",          (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID",    (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t


def _tabla_generica(
    df: pd.DataFrame,
    columnas: list[str],
    headers: list[str],
    anchos: list[float],
    fmt_col: dict[str, callable] | None = None,
) -> Table:
    """Construye una tabla con filas alternas."""
    fmt_col = fmt_col or {}
    encabezado = [headers]
    filas = []
    for _, row in df.iterrows():
        fila = []
        for col in columnas:
            val = row.get(col, "")
            if col in fmt_col:
                val = fmt_col[col](val)
            fila.append(str(val))
        filas.append(fila)

    datos = encabezado + filas
    t = Table(datos, colWidths=[a * cm for a in anchos])

    estilo = [
        ("BACKGROUND",  (0, 0), (-1, 0),  COLOR_PRIMARY),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, -1), 8),
        ("ALIGN",       (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_LIGHT]),
        ("BOX",         (0, 0), (-1, -1), 0.4, COLOR_BORDER),
        ("INNERGRID",   (0, 0), (-1, -1), 0.2, COLOR_BORDER),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(estilo))
    return t


def _encabezado_pagina(canvas_obj, doc):
    """Dibuja número de página en el pie."""
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 7)
    canvas_obj.setFillColor(COLOR_SECONDARY)
    canvas_obj.drawRightString(
        doc.pagesize[0] - 1.5 * cm,
        0.8 * cm,
        f"Página {canvas_obj.getPageNumber()}",
    )
    canvas_obj.restoreState()


# ── Función principal ─────────────────────────────────────────────────────

def generar_reporte_pdf(
    fecha_inicio: date,
    fecha_fin: date,
    nombre_negocio: str = "Desayunos Sorpresa Stella",
) -> bytes:
    """
    Genera el reporte PDF completo y retorna los bytes para descarga.

    Parámetros
    ----------
    fecha_inicio    : date de inicio del período
    fecha_fin       : date de fin del período
    nombre_negocio  : nombre que aparece en el encabezado del PDF

    Retorna
    -------
    bytes  — listo para st.download_button con mime="application/pdf"
    """
    f_ini = fecha_inicio.strftime("%Y-%m-%d")
    f_fin = fecha_fin.strftime("%Y-%m-%d")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )

    es = _estilos()
    story = []

    # ── Portada / encabezado ──────────────────────────────────────────────
    story.append(Paragraph(nombre_gitnegocio, es["titulo"]))
    story.append(Paragraph("Reporte de Ventas y Operaciones", es["subtitulo"]))

    rango = (
        f"Período: {fecha_inicio.strftime('%d/%m/%Y')} — {fecha_fin.strftime('%d/%m/%Y')}"
    )
    generado = f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    story.append(Paragraph(f"{rango}    |    {generado}", es["subtitulo"]))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceAfter=10))

    # ── KPIs ──────────────────────────────────────────────────────────────
    metricas = _metricas_generales(f_ini, f_fin)
    story.append(Paragraph("Resumen del período", es["seccion"]))
    story.append(_tabla_metricas(metricas, es))
    story.append(Spacer(1, 10))

    # ── Ventas por día ────────────────────────────────────────────────────
    df_dias = _ventas_por_dia(f_ini, f_fin)
    if not df_dias.empty:
        story.append(Paragraph("Ventas por día", es["seccion"]))
        story.append(
            _tabla_generica(
                df_dias,
                columnas=["dia", "pedidos", "ventas"],
                headers=["Fecha", "Pedidos", "Ventas (COP)"],
                anchos=[5, 3.5, 5.5],
                fmt_col={"ventas": _fmt_cop},
            )
        )
        story.append(Spacer(1, 8))

    # ── Top productos ─────────────────────────────────────────────────────
    df_prod = _top_productos(f_ini, f_fin)
    if not df_prod.empty:
        story.append(Paragraph("Productos más vendidos", es["seccion"]))
        story.append(
            _tabla_generica(
                df_prod,
                columnas=["nombre", "categoria", "unidades", "ingreso"],
                headers=["Producto", "Categoría", "Unidades", "Ingreso (COP)"],
                anchos=[7, 3, 2.5, 4],
                fmt_col={"ingreso": _fmt_cop},
            )
        )
        story.append(Spacer(1, 8))

    # ── Métodos de pago ───────────────────────────────────────────────────
    df_pagos = _metodos_pago(f_ini, f_fin)
    if not df_pagos.empty:
        story.append(Paragraph("Métodos de pago", es["seccion"]))
        story.append(
            _tabla_generica(
                df_pagos,
                columnas=["metodo_pago", "transacciones", "total"],
                headers=["Método", "Transacciones", "Total (COP)"],
                anchos=[5, 4, 5],
                fmt_col={"total": _fmt_cop},
            )
        )
        story.append(Spacer(1, 8))

    # ── Top clientes ──────────────────────────────────────────────────────
    df_cli = _top_clientes(f_ini, f_fin)
    if not df_cli.empty:
        story.append(Paragraph("Clientes destacados", es["seccion"]))
        story.append(
            _tabla_generica(
                df_cli,
                columnas=["nombre", "pedidos", "total"],
                headers=["Cliente", "Pedidos", "Total (COP)"],
                anchos=[7.5, 3, 5],
                fmt_col={"total": _fmt_cop},
            )
        )
        story.append(Spacer(1, 8))

    # ── Pie de documento ──────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER, spaceBefore=14))
    story.append(
        Paragraph(
            f"Documento generado automáticamente por {nombre_negocio} · "
            f"{datetime.now().strftime('%d/%m/%Y %H:%M')}",
            es["pie"],
        )
    )

    doc.build(story, onLaterPages=_encabezado_pagina, onFirstPage=_encabezado_pagina)
    return buffer.getvalue()