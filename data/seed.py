"""Inserta datos de ejemplo: clientes, productos, pedidos, detalle y pagos."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from utils.database import get_connection, init_db


def seed() -> None:
    init_db()
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.executescript(
            """
            DELETE FROM Pagos;
            DELETE FROM Detalle_Pedido;
            DELETE FROM Pedidos;
            DELETE FROM Productos;
            DELETE FROM Clientes;
            """
        )

        # IDs explícitos: tras borrar filas, AUTOINCREMENT sigue desde el último valor
        # y los pedidos/detalle asumen cliente_id 1–5 y producto_id 1–16.
        clientes = [
            (1, "María Gómez", "whatsapp", "minorista", "2026-01-15"),
            (2, "Restaurante El Rincón", "telegram", "mayorista", "2026-02-01"),
            (3, "Carlos Pérez", "whatsapp", "minorista", "2026-02-20"),
            (4, "Ana Lucía Vargas", "presencial", "minorista", "2026-03-05"),
            (5, "Cafetería Centro", "instagram", "mayorista", "2026-03-18"),
        ]
        cur.executemany(
            """
            INSERT INTO Clientes (id, nombre, canal, tipo_cliente, fecha_registro)
            VALUES (?, ?, ?, ?, ?)
            """,
            clientes,
        )

        productos = [
            (1, "Arepa con huevo y café", 9000, "Desayuno"),
            (2, "Calentao tradicional con huevo", 13000, "Desayuno"),
            (3, "Changua con pan aliñado", 11500, "Desayuno"),
            (4, "Huevos pericos con arepa y chocolate", 14000, "Desayuno"),
            (5, "Avena caliente (mediana)", 4000, "Desayuno"),
            (6, "Combo ejecutivo (calentao, huevo, café, jugo)", 19000, "Combo"),
            (7, "Combo ligero (arepa queso, café, jugo)", 15500, "Combo"),
            (8, "Combo familiar (2 personas)", 34000, "Combo"),
            (9, "Combo americano (tostadas, huevos, café, jugo)", 22500, "Combo"),
            (10, "Arepa de choclo con queso", 5000, "Individual"),
            (11, "Empanada de pollo", 3200, "Individual"),
            (12, "Café tinto", 1800, "Individual"),
            (13, "Café con leche", 3800, "Individual"),
            (14, "Jugo natural en agua", 4800, "Individual"),
            (15, "Jugo natural en leche", 6500, "Individual"),
            (16, "Pandebono (und)", 2200, "Individual"),
        ]
        cur.executemany(
            """
            INSERT INTO Productos (id, nombre, precio_unitario, categoria)
            VALUES (?, ?, ?, ?)
            """,
            productos,
        )

        pedidos = [
            ("PED-20260401-001", 1, "2026-04-01", "pendiente", 22600, "Sin cebolla"),
            ("PED-20260402-001", 2, "2026-04-02", "en_preparacion", 20300, None),
            ("PED-20260402-002", 3, "2026-04-02", "entregado", 19600, "Para llevar"),
            ("PED-20260403-001", 1, "2026-04-03", "entregado", 22500, None),
            ("PED-20260404-001", 4, "2026-04-04", "cancelado", 16400, "Cliente canceló"),
            ("PED-20260404-002", 5, "2026-04-04", "entregado", 34000, "Factura a nombre de empresa"),
            ("PED-20260405-001", 2, "2026-04-05", "pendiente", 22000, "Entregar después de 9 a.m."),
            ("PED-20260406-001", 3, "2026-04-06", "en_preparacion", 17800, None),
            ("PED-20260407-001", 4, "2026-04-07", "entregado", 18000, "Extra arepa"),
            ("PED-20260408-001", 5, "2026-04-08", "entregado", 14800, None),
        ]
        cur.executemany(
            """
            INSERT INTO Pedidos (id, cliente_id, fecha, estado, total, notas)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            pedidos,
        )

        detalle = [
            ("PED-20260401-001", 6, 1, 19000, 19000),
            ("PED-20260401-001", 12, 2, 1800, 3600),
            ("PED-20260402-001", 7, 1, 15500, 15500),
            ("PED-20260402-001", 14, 1, 4800, 4800),
            ("PED-20260402-002", 2, 1, 13000, 13000),
            ("PED-20260402-002", 16, 3, 2200, 6600),
            ("PED-20260403-001", 9, 1, 22500, 22500),
            ("PED-20260404-001", 10, 2, 5000, 10000),
            ("PED-20260404-001", 11, 2, 3200, 6400),
            ("PED-20260404-002", 8, 1, 34000, 34000),
            ("PED-20260405-001", 1, 2, 9000, 18000),
            ("PED-20260405-001", 5, 1, 4000, 4000),
            ("PED-20260406-001", 4, 1, 14000, 14000),
            ("PED-20260406-001", 13, 1, 3800, 3800),
            ("PED-20260407-001", 3, 1, 11500, 11500),
            ("PED-20260407-001", 15, 1, 6500, 6500),
            ("PED-20260408-001", 5, 2, 4000, 8000),
            ("PED-20260408-001", 10, 1, 5000, 5000),
            ("PED-20260408-001", 12, 1, 1800, 1800),
        ]
        cur.executemany(
            """
            INSERT INTO Detalle_Pedido
                (pedido_id, producto_id, cantidad, precio_unitario, subtotal)
            VALUES (?, ?, ?, ?, ?)
            """,
            detalle,
        )

        pagos = [
            (
                "PED-20260401-001",
                22600,
                "efectivo",
                None,
                "2026-04-01",
                "pendiente",
            ),
            (
                "PED-20260402-001",
                20300,
                "transferencia",
                "TRF-240402-001",
                "2026-04-02",
                "confirmado",
            ),
            (
                "PED-20260402-002",
                19600,
                "QR",
                "NEQUI-998877",
                "2026-04-02",
                "confirmado",
            ),
            (
                "PED-20260403-001",
                22500,
                "efectivo",
                None,
                "2026-04-03",
                "confirmado",
            ),
            (
                "PED-20260404-001",
                16400,
                "transferencia",
                "TRF-PEND-4404",
                "2026-04-04",
                "pendiente",
            ),
            (
                "PED-20260404-002",
                20000,
                "transferencia",
                "TRF-EMP-778899",
                "2026-04-04",
                "confirmado",
            ),
            (
                "PED-20260404-002",
                14000,
                "efectivo",
                None,
                "2026-04-04",
                "confirmado",
            ),
            (
                "PED-20260406-001",
                17800,
                "QR",
                "DAV-PLATA-445566",
                "2026-04-06",
                "pendiente",
            ),
            (
                "PED-20260407-001",
                18000,
                "transferencia",
                "TRF-0704-5544",
                "2026-04-07",
                "confirmado",
            ),
            (
                "PED-20260408-001",
                14800,
                "QR",
                "BRE-B-221133",
                "2026-04-08",
                "confirmado",
            ),
        ]
        cur.executemany(
            """
            INSERT INTO Pagos
                (pedido_id, monto, metodo_pago, referencia_pago, fecha, estado)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            pagos,
        )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
