"""
utils/wa_parser.py
------------------
Parser de mensajes de WhatsApp usando Groq API (llama-3.3-70b, gratuito).

Exporta dos funciones públicas que mantienen compatibilidad con el resto del proyecto:

  parse_whatsapp_message(mensaje, catalogo)
      -> list[dict]   (usada en tests y llamadas directas)

  parse_whatsapp_message_items(mensaje)
      -> dict con keys: badge, mensaje, items
         (usada en 04_Importar_WhatsApp.py)

La API key se lee desde st.secrets["GROQ_API_KEY"] o la variable
de entorno GROQ_API_KEY. Si no esta disponible, el parser cae
graciosamente al modo regex de respaldo.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_NUMEROS_ES: dict[str, int] = {
    "un": 1, "una": 1, "uno": 1,
    "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "veinte": 20, "veintiuno": 21, "veintidos": 22, "veintitres": 23,
    "media": 1, "medio": 1,
}


def _catalogo_desde_db() -> list[dict]:
    try:
        from utils.database import query_df
        df = query_df("SELECT id, nombre, precio_unitario FROM Productos ORDER BY nombre")
        if df.empty:
            return []
        return df.to_dict("records")
    except Exception:
        return []


def _catalogo_como_texto(catalogo: list[dict]) -> str:
    lineas = []
    for p in catalogo:
        pid    = p.get("id", "")
        nom    = p.get("nombre", "")
        precio = p.get("precio_unitario", 0)
        lineas.append(f"  ID:{pid} | {nom} | ${precio:,.0f}")
    return "\n".join(lineas) if lineas else "  (catalogo vacio)"


def _get_api_key() -> str | None:
    try:
        import streamlit as st
        key = st.secrets.get("GROQ_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


def _parsear_cantidad(texto: str) -> int:
    texto = texto.strip().lower()
    if texto.isdigit():
        return int(texto)
    return _NUMEROS_ES.get(texto, 1)


def _fallback_parse(mensaje: str, catalogo: list[dict]) -> list[dict]:
    if not catalogo:
        return []
    resultado: list[dict] = []
    msg_lower = mensaje.lower()
    for prod in catalogo:
        nombre = prod.get("nombre", "").lower()
        if nombre not in msg_lower:
            continue
        idx = msg_lower.find(nombre)
        fragmento = msg_lower[max(0, idx - 20): idx].strip()
        m = re.search(
            r"(\d+|" + "|".join(_NUMEROS_ES.keys()) + r")\s*[xX]\s*$",
            fragmento,
        )
        cantidad = _parsear_cantidad(m.group(1)) if m else 1
        precio = prod.get("precio_unitario", 0)
        resultado.append({
            "producto_id":     prod.get("id"),
            "nombre":          prod.get("nombre"),
            "cantidad":        cantidad,
            "precio_unitario": precio,
            "total":           cantidad * precio,
        })
    return resultado


def _claude_parse(mensaje: str, catalogo: list[dict]) -> list[dict]:
    from groq import Groq

    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY no configurada")

    client = Groq(api_key=api_key)
    catalogo_txt = _catalogo_como_texto(catalogo)

    prompt = (
        "Eres el asistente de un negocio de desayunos y comidas.\n"
        "Tu tarea es interpretar mensajes de clientes de WhatsApp e identificar\n"
        "que productos estan pidiendo, asociando cada item con el catalogo.\n\n"
        f"CATALOGO:\n{catalogo_txt}\n\n"
        f"MENSAJE DEL CLIENTE:\n{mensaje}\n\n"
        "REGLAS:\n"
        "- Interpreta aunque haya errores ortograficos o lenguaje informal.\n"
        "- Asocia cada item con el producto mas cercano del catalogo.\n"
        "- Si no hay pedido claro, devuelve items vacio.\n"
        "- Usa EXACTAMENTE el id, nombre y precio_unitario del catalogo.\n\n"
        "RESPONDE SOLO con JSON, sin texto extra, sin backticks:\n"
        '{"items": [{"producto_id": <id>, "nombre": "<nombre exacto>", '
        '"cantidad": <int>, "precio_unitario": <precio>, "total": <cant*precio>}]}'
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "Responde SOLO con JSON valido. Sin texto. Sin backticks."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=800,
    )

    raw = response.choices[0].message.content.strip()
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    data = json.loads(raw)
    resultado: list[dict] = []
    for item in data.get("items", []):
        pid  = item.get("producto_id")
        nom  = item.get("nombre", "").strip()
        cant = int(item.get("cantidad", 1))
        pu   = float(item.get("precio_unitario", 0))
        if pid and nom and cant > 0:
            resultado.append({
                "producto_id":     pid,
                "nombre":          nom,
                "cantidad":        cant,
                "precio_unitario": pu,
                "total":           cant * pu,
            })
    return resultado


def parse_whatsapp_message(mensaje: str, catalogo: list[dict]) -> list[dict]:
    if not mensaje or not mensaje.strip():
        return []
    try:
        return _claude_parse(mensaje, catalogo)
    except Exception:
        return _fallback_parse(mensaje, catalogo)


def parse_whatsapp_message_items(mensaje: str) -> dict[str, Any]:
    if not mensaje or not mensaje.strip():
        return {"badge": "warning", "mensaje": "El mensaje esta vacio.", "items": []}

    catalogo = _catalogo_desde_db()
    if not catalogo:
        return {
            "badge":   "error",
            "mensaje": "No se pudo cargar el catalogo desde la base de datos.",
            "items":   [],
        }

    uso_ia = False
    try:
        items_raw = _claude_parse(mensaje, catalogo)
        uso_ia = True
    except Exception:
        items_raw = _fallback_parse(mensaje, catalogo)

    if not items_raw:
        return {
            "badge":   "warning",
            "mensaje": "No se detectaron productos del catalogo en el mensaje. Puede editar la tabla manualmente.",
            "items":   [],
        }

    items_ui = [
        {
            "Producto":        it["nombre"],
            "Cantidad":        it["cantidad"],
            "Precio Unitario": it["precio_unitario"],
            "Total":           it["total"],
        }
        for it in items_raw
    ]

    fuente = "IA (Groq)" if uso_ia else "parser de texto"
    return {
        "badge":   "ok",
        "mensaje": f"{len(items_ui)} producto(s) detectado(s) con {fuente}. Revise y confirme.",
        "items":   items_ui,
    }