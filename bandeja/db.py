"""Almacenamiento en SQLite: documentos, líneas, alertas e historial de precios."""
import json
import sqlite3
from pathlib import Path

from .modelos import Documento
from .validar import Alerta, normalizar

ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id           INTEGER PRIMARY KEY,
    archivo      TEXT NOT NULL,
    hash         TEXT NOT NULL UNIQUE,          -- evita procesar dos veces el mismo archivo
    tipo         TEXT NOT NULL,
    proveedor    TEXT NOT NULL,
    cuit         TEXT,
    numero       TEXT,
    fecha        TEXT,
    total        REAL NOT NULL,
    impuestos    REAL,
    estado       TEXT NOT NULL DEFAULT 'pendiente' CHECK (estado IN ('pendiente', 'aprobado', 'rechazado')),
    procesado    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    extractor    TEXT NOT NULL,                 -- 'claude:<modelo>' o 'demo'
    datos_json   TEXT NOT NULL                  -- lo extraído, completo, para auditoría
);
CREATE TABLE IF NOT EXISTS items (
    id               INTEGER PRIMARY KEY,
    documento_id     INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    descripcion      TEXT NOT NULL,
    clave            TEXT NOT NULL,             -- descripción normalizada para comparar precios
    cantidad         REAL NOT NULL,
    unidad           TEXT,
    precio_unitario  REAL NOT NULL,
    subtotal         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS alertas (
    id            INTEGER PRIMARY KEY,
    documento_id  INTEGER NOT NULL REFERENCES documentos(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL,
    gravedad      TEXT NOT NULL,
    mensaje       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS proveedores (       -- padrón de proveedores habituales
    id      INTEGER PRIMARY KEY,
    nombre  TEXT NOT NULL UNIQUE COLLATE NOCASE,
    cuit    TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_items_clave ON items(clave);
CREATE INDEX IF NOT EXISTS idx_doc_prov_num ON documentos(proveedor, numero);
"""


def conectar(ruta: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    return con


def ya_procesado(con, hash_archivo: str) -> bool:
    return con.execute("SELECT 1 FROM documentos WHERE hash = ?", (hash_archivo,)).fetchone() is not None


def buscar_duplicado(con, proveedor: str, numero: str):
    fila = con.execute(
        "SELECT id FROM documentos WHERE lower(proveedor) = lower(?) AND numero = ? AND estado != 'rechazado'",
        (proveedor, numero),
    ).fetchone()
    return fila["id"] if fila else None


def ultimo_precio(con, proveedor: str, descripcion: str):
    fila = con.execute(
        """SELECT i.precio_unitario FROM items i JOIN documentos d ON d.id = i.documento_id
           WHERE lower(d.proveedor) = lower(?) AND i.clave = ? AND d.estado != 'rechazado'
             AND d.tipo IN ('factura', 'remito')
           ORDER BY COALESCE(d.fecha, d.procesado) DESC, d.id DESC LIMIT 1""",
        (proveedor, normalizar(descripcion)),
    ).fetchone()
    return fila["precio_unitario"] if fila else None


def proveedor_conocido(con, proveedor: str, cuit: str | None = None) -> bool:
    """Conocido si está en el padrón (por nombre o CUIT) o si ya se le aprobó algún comprobante."""
    return con.execute(
        """SELECT 1 FROM proveedores WHERE nombre = ? OR (cuit IS NOT NULL AND cuit = ?)
           UNION SELECT 1 FROM documentos WHERE lower(proveedor) = lower(?) AND estado = 'aprobado' LIMIT 1""",
        (proveedor, cuit, proveedor),
    ).fetchone() is not None


def agregar_proveedor(con, nombre: str, cuit: str | None = None) -> None:
    with con:
        con.execute("INSERT OR IGNORE INTO proveedores (nombre, cuit) VALUES (?, ?)", (nombre, cuit or None))


def cargar_padron(con, ruta) -> int:
    """Carga un CSV `nombre;cuit` (con encabezado)."""
    import csv
    with open(ruta, encoding="utf-8") as f:
        filas = [(r["nombre"].strip(), (r.get("cuit") or "").strip() or None) for r in csv.DictReader(f, delimiter=";")]
    for nombre, cuit in filas:
        agregar_proveedor(con, nombre, cuit)
    return len(filas)


def guardar(con, archivo: str, hash_archivo: str, doc: Documento, alertas: list[Alerta], extractor: str) -> int:
    with con:  # transacción: o se guarda todo o nada
        cur = con.execute(
            """INSERT INTO documentos (archivo, hash, tipo, proveedor, cuit, numero, fecha, total, impuestos,
               extractor, datos_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (archivo, hash_archivo, doc.tipo, doc.proveedor, doc.cuit, doc.numero, doc.fecha, doc.total,
             doc.impuestos, extractor, doc.model_dump_json()),
        )
        doc_id = cur.lastrowid
        con.executemany(
            """INSERT INTO items (documento_id, descripcion, clave, cantidad, unidad, precio_unitario, subtotal)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(doc_id, it.descripcion, normalizar(it.descripcion), it.cantidad, it.unidad, it.precio_unitario,
              it.subtotal) for it in doc.items],
        )
        con.executemany(
            "INSERT INTO alertas (documento_id, tipo, gravedad, mensaje) VALUES (?, ?, ?, ?)",
            [(doc_id, a.tipo, a.gravedad, a.mensaje) for a in alertas],
        )
    return doc_id


def cambiar_estado(con, doc_id: int, estado: str) -> bool:
    with con:
        cur = con.execute("UPDATE documentos SET estado = ? WHERE id = ?", (estado, doc_id))
    return cur.rowcount == 1


def documentos_completos(con) -> list[dict]:
    """Todo junto, listo para el panel o la exportación."""
    docs = []
    for d in con.execute("SELECT * FROM documentos ORDER BY COALESCE(fecha, procesado), id"):
        fila = dict(d)
        fila["datos"] = json.loads(fila.pop("datos_json"))
        fila["items"] = [dict(i) for i in con.execute(
            "SELECT descripcion, cantidad, unidad, precio_unitario, subtotal FROM items WHERE documento_id = ?",
            (d["id"],))]
        fila["alertas"] = [dict(a) for a in con.execute(
            "SELECT tipo, gravedad, mensaje FROM alertas WHERE documento_id = ? ORDER BY id", (d["id"],))]
        docs.append(fila)
    return docs
