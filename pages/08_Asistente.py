"""Asistente IA — Chatbot de consultas del negocio."""

from __future__ import annotations

import os
from datetime import date

import streamlit as st

from utils.database import init_db, query_df

st.set_page_config(page_title="Asistente IA", layout="wide")

if not st.session_state.get("autenticado"):
    st.switch_page("app.py")

init_db()


# ── API Key ────────────────────────────────────────────────────────────────────

def _get_groq_key() -> str | None:
    try:
        key = st.secrets.get("GROQ_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


# ── Contexto completo del negocio ──────────────────────────────────────────────

def _obtener_contexto_negocio() -> str:
    hoy = date.today().isoformat()
    ctx = f"Hoy es {hoy}. Negocio: Desayunos Sorpresa Stella (desayunos a domicilio, Colombia).\n\n"

    def _safe(fn):
        try:
            return fn()
        except Exception as e:
            return f"(no disponible: {e})"

    # 1. Resumen general de pedidos
    def resumen_general():
        df = query_df("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN estado='pendiente'  THEN 1 ELSE 0 END) AS pendientes,
                SUM(CASE WHEN estado='entregado'  THEN 1 ELSE 0 END) AS entregados,
                SUM(CASE WHEN estado='cancelado'  THEN 1 ELSE 0 END) AS cancelados,
                COALESCE(SUM(CASE WHEN estado!='cancelado' THEN total ELSE 0 END),0) AS ventas_totales
            FROM Pedidos
        """)
        if df.empty:
            return "Sin pedidos registrados."
        r = df.iloc[0]
        return (
            f"- Total pedidos: {int(r['total'])}\n"
            f"- Pendientes: {int(r['pendientes'])} | Entregados: {int(r['entregados'])} | Cancelados: {int(r['cancelados'])}\n"
            f"- Ventas totales (sin cancelados): ${float(r['ventas_totales']):,.0f} COP"
        )

    # 2. Pedidos de hoy
    def pedidos_hoy():
        df = query_df("""
            SELECT COUNT(*) AS total, COALESCE(SUM(total),0) AS ventas
            FROM Pedidos WHERE date(fecha) = date('now') AND estado != 'cancelado'
        """)
        if df.empty:
            return "Sin pedidos hoy."
        r = df.iloc[0]
        return f"- Pedidos hoy: {int(r['total'])} | Ventas hoy: ${float(r['ventas']):,.0f} COP"

    # 3. Pedidos últimos 7 días
    def pedidos_semana():
        df = query_df("""
            SELECT COUNT(*) AS total, COALESCE(SUM(total),0) AS ventas
            FROM Pedidos WHERE date(fecha) >= date('now','-7 days') AND estado != 'cancelado'
        """)
        if df.empty:
            return "Sin datos."
        r = df.iloc[0]
        return f"- Pedidos (7 días): {int(r['total'])} | Ventas: ${float(r['ventas']):,.0f} COP"

    # 4. Pedidos últimos 30 días
    def pedidos_mes():
        df = query_df("""
            SELECT COUNT(*) AS total, COALESCE(SUM(total),0) AS ventas
            FROM Pedidos WHERE date(fecha) >= date('now','-30 days') AND estado != 'cancelado'
        """)
        if df.empty:
            return "Sin datos."
        r = df.iloc[0]
        return f"- Pedidos (30 días): {int(r['total'])} | Ventas: ${float(r['ventas']):,.0f} COP"

    # 5. Ventas por mes histórico
    def ventas_por_mes():
        df = query_df("""
            SELECT strftime('%Y-%m', fecha) AS mes,
                   COUNT(*) AS pedidos,
                   COALESCE(SUM(total),0) AS ventas
            FROM Pedidos WHERE estado != 'cancelado'
            GROUP BY mes ORDER BY mes DESC LIMIT 12
        """)
        if df.empty:
            return "Sin datos."
        lineas = [
            f"  {r['mes']}: {int(r['pedidos'])} pedidos — ${float(r['ventas']):,.0f} COP"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 6. Todos los productos con ventas
    def productos_ventas():
        df = query_df("""
            SELECT p.nombre, p.categoria, p.precio_unitario,
                   COALESCE(SUM(dp.cantidad),0) AS cantidad_vendida,
                   COALESCE(SUM(dp.subtotal),0) AS ingreso
            FROM Productos p
            LEFT JOIN Detalle_Pedido dp ON dp.producto_id = p.id
            LEFT JOIN Pedidos pe ON dp.pedido_id = pe.id AND pe.estado != 'cancelado'
            GROUP BY p.id ORDER BY cantidad_vendida DESC
        """)
        if df.empty:
            return "Sin productos."
        lineas = [
            f"  - {r['nombre']} (cat: {r['categoria']}) | precio: ${float(r['precio_unitario']):,.0f} | "
            f"vendido: {int(r['cantidad_vendida'])} uds | ingreso: ${float(r['ingreso']):,.0f} COP"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 7. Todos los clientes con historial
    def clientes_historial():
        df = query_df("""
            SELECT c.nombre, c.canal, c.tipo_cliente, c.fecha_registro,
                   COUNT(p.id) AS pedidos,
                   COALESCE(SUM(CASE WHEN p.estado!='cancelado' THEN p.total ELSE 0 END),0) AS monto_total,
                   MAX(p.fecha) AS ultimo_pedido
            FROM Clientes c
            LEFT JOIN Pedidos p ON c.id = p.cliente_id
            GROUP BY c.id ORDER BY monto_total DESC
        """)
        if df.empty:
            return "Sin clientes."
        lineas = [
            f"  - {r['nombre']} | canal: {r['canal']} | tipo: {r['tipo_cliente']} | "
            f"pedidos: {int(r['pedidos'])} | total gastado: ${float(r['monto_total']):,.0f} COP | "
            f"último pedido: {r['ultimo_pedido']} | registrado: {r['fecha_registro']}"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 8. Clientes con pagos pendientes (deudores)
    def clientes_deudores():
        df = query_df("""
            SELECT c.nombre,
                   COUNT(pa.id) AS n_pagos_pendientes,
                   COALESCE(SUM(pa.monto),0) AS deuda_total
            FROM Pagos pa
            JOIN Pedidos pe ON pa.pedido_id = pe.id
            JOIN Clientes c ON pe.cliente_id = c.id
            WHERE pa.estado = 'pendiente'
            GROUP BY c.id ORDER BY deuda_total DESC
        """)
        if df.empty:
            return "Ningún cliente con pagos pendientes."
        lineas = [
            f"  - {r['nombre']}: {int(r['n_pagos_pendientes'])} pago(s) pendiente(s) — debe ${float(r['deuda_total']):,.0f} COP"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 9. Detalle de pagos pendientes por pedido
    def pagos_pendientes_detalle():
        df = query_df("""
            SELECT c.nombre AS cliente, pa.pedido_id, pa.monto, pa.metodo_pago, pa.fecha
            FROM Pagos pa
            JOIN Pedidos pe ON pa.pedido_id = pe.id
            JOIN Clientes c ON pe.cliente_id = c.id
            WHERE pa.estado = 'pendiente'
            ORDER BY pa.monto DESC
        """)
        if df.empty:
            return "No hay pagos pendientes."
        lineas = [
            f"  - {r['cliente']} | pedido {r['pedido_id']} | ${float(r['monto']):,.0f} COP | "
            f"método: {r['metodo_pago']} | fecha: {r['fecha']}"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 10. Pagos confirmados por método
    def pagos_por_metodo():
        df = query_df("""
            SELECT metodo_pago,
                   COUNT(*) AS cantidad,
                   COALESCE(SUM(monto),0) AS total
            FROM Pagos WHERE estado = 'confirmado'
            GROUP BY metodo_pago ORDER BY total DESC
        """)
        if df.empty:
            return "Sin pagos confirmados."
        lineas = [
            f"  - {r['metodo_pago']}: {int(r['cantidad'])} pagos — ${float(r['total']):,.0f} COP"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 11. Pedidos pendientes de entrega
    def pedidos_pendientes():
        df = query_df("""
            SELECT pe.id, c.nombre AS cliente, pe.fecha, pe.total
            FROM Pedidos pe
            JOIN Clientes c ON pe.cliente_id = c.id
            WHERE pe.estado = 'pendiente'
            ORDER BY pe.fecha ASC
        """)
        if df.empty:
            return "No hay pedidos pendientes de entrega."
        lineas = [
            f"  - Pedido {r['id']} | {r['cliente']} | ${float(r['total']):,.0f} COP | fecha: {r['fecha']}"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 12. Pedidos cancelados recientes
    def pedidos_cancelados():
        df = query_df("""
            SELECT pe.id, c.nombre AS cliente, pe.fecha, pe.total, pe.notas
            FROM Pedidos pe
            JOIN Clientes c ON pe.cliente_id = c.id
            WHERE pe.estado = 'cancelado'
            ORDER BY pe.fecha DESC LIMIT 10
        """)
        if df.empty:
            return "No hay pedidos cancelados."
        lineas = [
            f"  - Pedido {r['id']} | {r['cliente']} | ${float(r['total']):,.0f} COP | fecha: {r['fecha']}"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 13. Productos sin ventas
    def productos_sin_ventas():
        df = query_df("""
            SELECT p.nombre, p.categoria, p.precio_unitario
            FROM Productos p
            LEFT JOIN Detalle_Pedido dp ON dp.producto_id = p.id
            WHERE dp.id IS NULL
        """)
        if df.empty:
            return "Todos los productos tienen al menos una venta."
        lineas = [
            f"  - {r['nombre']} (${float(r['precio_unitario']):,.0f})"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # 14. Ticket promedio
    def ticket_promedio():
        df = query_df("""
            SELECT ROUND(AVG(total), 0) AS ticket FROM Pedidos WHERE estado != 'cancelado'
        """)
        if df.empty or df.iloc[0]["ticket"] is None:
            return "Sin datos."
        return f"- Ticket promedio por pedido: ${float(df.iloc[0]['ticket']):,.0f} COP"

    # 15. Clientes inactivos (sin pedidos en 30+ días)
    def clientes_inactivos():
        df = query_df("""
            SELECT c.nombre, MAX(p.fecha) AS ultimo_pedido
            FROM Clientes c
            JOIN Pedidos p ON c.id = p.cliente_id
            GROUP BY c.id
            HAVING date(MAX(p.fecha)) < date('now', '-30 days')
            ORDER BY ultimo_pedido ASC
        """)
        if df.empty:
            return "Todos los clientes han pedido en los últimos 30 días."
        lineas = [
            f"  - {r['nombre']} | último pedido: {r['ultimo_pedido']}"
            for _, r in df.iterrows()
        ]
        return "\n".join(lineas)

    # Armar contexto completo
    secciones = [
        ("RESUMEN GENERAL DE PEDIDOS", resumen_general),
        ("PEDIDOS HOY", pedidos_hoy),
        ("PEDIDOS ÚLTIMOS 7 DÍAS", pedidos_semana),
        ("PEDIDOS ÚLTIMOS 30 DÍAS", pedidos_mes),
        ("VENTAS POR MES (histórico)", ventas_por_mes),
        ("TODOS LOS PRODUCTOS CON VENTAS", productos_ventas),
        ("TODOS LOS CLIENTES CON HISTORIAL", clientes_historial),
        ("CLIENTES CON PAGOS PENDIENTES (DEUDORES)", clientes_deudores),
        ("DETALLE DE PAGOS PENDIENTES POR PEDIDO", pagos_pendientes_detalle),
        ("PAGOS CONFIRMADOS POR MÉTODO", pagos_por_metodo),
        ("PEDIDOS PENDIENTES DE ENTREGA", pedidos_pendientes),
        ("PEDIDOS CANCELADOS (últimos 10)", pedidos_cancelados),
        ("PRODUCTOS SIN VENTAS", productos_sin_ventas),
        ("TICKET PROMEDIO", ticket_promedio),
        ("CLIENTES INACTIVOS (sin pedidos en 30+ días)", clientes_inactivos),
    ]

    for titulo, fn in secciones:
        ctx += f"{titulo}:\n{_safe(fn)}\n\n"

    return ctx


# ── Llamada a Groq ─────────────────────────────────────────────────────────────

def _responder(historial: list[dict], contexto: str) -> str:
    api_key = _get_groq_key()
    if not api_key:
        return "⚠️ GROQ_API_KEY no configurada. Agrega la clave en `.streamlit/secrets.toml`."

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        system_prompt = (
            "Eres el asistente inteligente de 'Desayunos Sorpresa Stella', "
            "un negocio colombiano de desayunos a domicilio.\n"
            "Tienes acceso completo a los datos reales del negocio en el contexto.\n\n"
            "REGLAS:\n"
            "- Responde SIEMPRE en español, claro y directo.\n"
            "- Usa SIEMPRE los datos del contexto para dar cifras y nombres reales.\n"
            "- Nunca inventes datos. Si no está en el contexto, dilo honestamente.\n"
            "- Sé conciso: máximo 5 puntos o 3 párrafos cortos.\n"
            "- Si detectas algo preocupante (deudores, pedidos sin entregar, caída de ventas), menciónalo.\n"
            "- Usa emojis con moderación.\n\n"
            f"DATOS ACTUALES DEL NEGOCIO:\n{contexto}"
        )

        # Limitar historial a últimos 10 mensajes para cuidar tokens
        historial_reciente = historial[-10:]
        messages = [{"role": "system", "content": system_prompt}] + historial_reciente

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.3,
            max_tokens=700,
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"❌ Error al consultar la IA: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.title("🤖 Asistente Stella")
st.caption("Pregúntame sobre pedidos, ventas, clientes, pagos o cualquier dato del negocio.")

# Inicializar estado
if "chat_historial" not in st.session_state:
    st.session_state["chat_historial"] = []
if "chat_contexto" not in st.session_state:
    st.session_state["chat_contexto"] = _obtener_contexto_negocio()

# Botón actualizar datos
col_titulo, col_btn = st.columns([4, 1])
with col_btn:
    if st.button("🔄 Actualizar datos", help="Recarga los datos reales del negocio"):
        st.session_state["chat_contexto"] = _obtener_contexto_negocio()
        st.toast("Datos actualizados ✅")

st.divider()

# Sugerencias rápidas
st.markdown("**💡 Preguntas frecuentes:**")
sugerencias = [
    "¿Quién me debe plata?",
    "¿Cuánto vendí esta semana?",
    "¿Qué productos vendo más?",
    "¿Qué pedidos están pendientes?",
    "¿Cuál fue mi mejor mes?",
    "¿Qué clientes no han pedido en un mes?",
]
cols = st.columns(len(sugerencias))
for i, sug in enumerate(sugerencias):
    with cols[i]:
        if st.button(sug, key=f"sug_{i}", use_container_width=True):
            st.session_state["_input_externo"] = sug

st.divider()

# Historial del chat
for msg in st.session_state["chat_historial"]:
    avatar = "🤖" if msg["role"] == "assistant" else None
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# Input
input_externo = st.session_state.pop("_input_externo", None)
pregunta = st.chat_input("Escribe tu pregunta aquí...") or input_externo

if pregunta:
    with st.chat_message("user"):
        st.markdown(pregunta)
    st.session_state["chat_historial"].append({"role": "user", "content": pregunta})

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Analizando..."):
            respuesta = _responder(
                st.session_state["chat_historial"],
                st.session_state["chat_contexto"],
            )
        st.markdown(respuesta)
    st.session_state["chat_historial"].append({"role": "assistant", "content": respuesta})

# Limpiar conversación
if st.session_state["chat_historial"]:
    st.divider()
    if st.button("🗑️ Limpiar conversación"):
        st.session_state["chat_historial"] = []
        st.rerun()