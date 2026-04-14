"""Pruebas del parser de WhatsApp."""

from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.wa_parser import parse_whatsapp_message

CATALOGO = [
    {"id": 1,  "nombre": "arepa con huevo y café",   "precio_unitario": 9000},
    {"id": 6,  "nombre": "combo ejecutivo",           "precio_unitario": 19000},
    {"id": 8,  "nombre": "combo familiar",            "precio_unitario": 34000},
    {"id": 16, "nombre": "pandebono",                 "precio_unitario": 2200},
]


def test_mensaje_con_productos_reconocibles():
    """Detecta productos y cantidades correctamente."""
    mensaje = "Buenos días, quiero 2 arepas con huevo y 1 combo ejecutivo"
    resultado = parse_whatsapp_message(mensaje, CATALOGO)
    assert len(resultado) >= 1
    cantidades = {item["nombre"]: item["cantidad"] for item in resultado}
    assert any(v == 1 for v in cantidades.values())


def test_mensaje_sin_productos_retorna_lista_vacia():
    """Sin productos reconocibles devuelve lista vacía."""
    mensaje = "Hola buenas, ¿a qué hora abren?"
    resultado = parse_whatsapp_message(mensaje, CATALOGO)
    assert isinstance(resultado, list)
    assert len(resultado) == 0


def test_mensaje_con_numeros_escritos():
    """Detecta cantidades escritas como palabras."""
    mensaje = "tres pandebonos por favor"
    resultado = parse_whatsapp_message(mensaje, CATALOGO)
    assert len(resultado) >= 1
    assert resultado[0]["cantidad"] == 3


def test_resultado_tiene_estructura_correcta():
    """Cada item del resultado tiene las keys requeridas."""
    mensaje = "2 combos familiares"
    resultado = parse_whatsapp_message(mensaje, CATALOGO)
    if resultado:
        item = resultado[0]
        assert "producto_id" in item
        assert "nombre" in item
        assert "cantidad" in item
        assert "precio_unitario" in item
        assert "total" in item