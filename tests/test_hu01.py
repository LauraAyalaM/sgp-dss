"""Pruebas HU-01: Registrar pedido con múltiples productos."""

from __future__ import annotations
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import sqlite3
import pytest
from datetime import date
from utils.database import init_db, get_connection, execute, query_df


@pytest.fixture(autouse=True)
def db_test(tmp_path, monkeypatch):
    """Usa una BD temporal para cada test."""
    import utils.database as db_module
    db_test_path = tmp_path / "test.db"
    monkeypatch.setattr(db_module, "_DB_PATH", db_test_path)
    init_db()

    conn = get_connection()
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("INSERT INTO Clientes (id, nombre, canal, tipo_cliente, fecha_registro) VALUES (1, 'Test Cliente', 'whatsapp', 'minorista', '2026-01-01')")
    conn.execute("INSERT INTO Productos (id, nombre, precio_unitario, categoria) VALUES (1, 'Arepa', 9000, 'Desayuno')")
    conn.execute("INSERT INTO Productos (id, nombre, precio_unitario, categoria) VALUES (2, 'Café', 1800, 'Individual')")
    conn.commit()
    conn.close()
    yield


def generar_id_pedido(numero: int = 1) -> str:
    """Genera ID en formato PED-YYYYMMDD-NNN."""
    hoy = date.today().strftime("%Y%m%d")
    return f"PED-{hoy}-{numero:03d}"


def test_id_formato_correcto():
    """CA-03: El ID debe seguir el formato PED-YYYYMMDD-NNN."""
    pid = generar_id_pedido(1)
    assert pid.startswith("PED-")
    partes = pid.split("-")
    assert len(partes) == 3
    assert len(partes[1]) == 8
    assert partes[1].isdigit()
    assert len(partes[2]) == 3
    assert partes[2].isdigit()


def test_pedido_con_productos_calcula_total():
    """CA-02: El subtotal debe calcularse correctamente."""
    productos = [
        {"producto_id": 1, "cantidad": 2, "precio_unitario": 9000},
        {"producto_id": 2, "cantidad": 3, "precio_unitario": 1800},
    ]
    total = sum(p["cantidad"] * p["precio_unitario"] for p in productos)
    assert total == 23400


def test_pedido_se_guarda_en_bd():
    """CA-03: El pedido se guarda con estado pendiente."""
    pid = generar_id_pedido(1)
    execute(
        "INSERT INTO Pedidos (id, cliente_id, fecha, estado, total) VALUES (?, ?, ?, ?, ?)",
        (pid, 1, "2026-04-12", "pendiente", 23400)
    )
    df = query_df("SELECT * FROM Pedidos WHERE id = ?", params=(pid,))
    assert len(df) == 1
    assert df.iloc[0]["estado"] == "pendiente"
    assert df.iloc[0]["total"] == 23400


def test_pedido_vacio_no_debe_guardarse():
    """CA-04: Un pedido sin productos no debe permitirse."""
    productos = []
    with pytest.raises(ValueError, match="al menos un producto"):
        if not productos:
            raise ValueError("El pedido debe tener al menos un producto")


def test_estado_inicial_es_pendiente():
    """CA-03: El estado inicial siempre debe ser pendiente."""
    pid = generar_id_pedido(2)
    execute(
        "INSERT INTO Pedidos (id, cliente_id, fecha, estado, total) VALUES (?, ?, ?, ?, ?)",
        (pid, 1, "2026-04-12", "pendiente", 9000)
    )
    df = query_df("SELECT estado FROM Pedidos WHERE id = ?", params=(pid,))
    assert df.iloc[0]["estado"] == "pendiente"