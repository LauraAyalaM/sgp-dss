"""Gestión de la base de datos SQLite (sqlite3 + pandas)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional, Sequence, Union

import pandas as pd

Params = Optional[Union[Sequence[Any], dict[str, Any]]]

_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sgp.db"


def get_connection() -> sqlite3.Connection:
    """Abre una conexión SQLite con claves foráneas activadas."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Crea las tablas si no existen."""
    ddl = """
    CREATE TABLE IF NOT EXISTS Clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        canal TEXT,
        tipo_cliente TEXT,
        fecha_registro TEXT
    );

    CREATE TABLE IF NOT EXISTS Productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        precio_unitario REAL NOT NULL,
        categoria TEXT
    );

    CREATE TABLE IF NOT EXISTS Pedidos (
        id TEXT PRIMARY KEY,
        cliente_id INTEGER NOT NULL REFERENCES Clientes(id),
        fecha TEXT NOT NULL,
        estado TEXT NOT NULL CHECK (
            estado IN ('pendiente', 'en_preparacion', 'entregado', 'cancelado')
        ),
        total REAL NOT NULL,
        notas TEXT
    );

    CREATE TABLE IF NOT EXISTS Detalle_Pedido (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id TEXT NOT NULL REFERENCES Pedidos(id),
        producto_id INTEGER NOT NULL REFERENCES Productos(id),
        cantidad REAL NOT NULL,
        precio_unitario REAL NOT NULL,
        subtotal REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS Pagos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id TEXT NOT NULL REFERENCES Pedidos(id),
        monto REAL NOT NULL,
        metodo_pago TEXT NOT NULL CHECK (
            metodo_pago IN ('efectivo', 'transferencia', 'QR')
        ),
        referencia_pago TEXT,
        fecha TEXT NOT NULL,
        estado TEXT NOT NULL CHECK (estado IN ('pendiente', 'confirmado'))
    );

    CREATE TABLE IF NOT EXISTS Cierre_Caja (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL UNIQUE,
        total_ventas REAL NOT NULL,
        total_pagos_recibidos REAL NOT NULL,
        total_pendiente REAL NOT NULL,
        total_pedidos INTEGER NOT NULL,
        pedidos_entregados INTEGER NOT NULL,
        pedidos_cancelados INTEGER NOT NULL
    );
    """
    conn = get_connection()
    try:
        conn.executescript(ddl)
        cur = conn.execute("PRAGMA table_info(Pedidos)")
        cols = [row[1] for row in cur.fetchall()]
        if "estado_importacion" not in cols:
            conn.execute(
                "ALTER TABLE Pedidos ADD COLUMN estado_importacion TEXT"
            )
        conn.commit()
    finally:
        conn.close()


def query_df(sql: str, params: Params = None) -> pd.DataFrame:
    """Ejecuta una consulta SQL y devuelve un DataFrame."""
    conn = get_connection()
    try:
        return pd.read_sql(sql, conn, params=params)
    finally:
        conn.close()


def execute(sql: str, params: Params = None) -> int:
    """Ejecuta INSERT/UPDATE/DELETE y devuelve el número de filas afectadas."""
    conn = get_connection()
    try:
        cur = conn.execute(sql, () if params is None else params)
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
