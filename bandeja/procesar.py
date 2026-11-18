"""Recorre la carpeta de entrada y procesa cada documento nuevo."""
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import db
from .extraer import ErrorExtraccion
from .leer import EXTENSIONES, hash_archivo
from .validar import Alerta, validar


@dataclass
class Resultado:
    archivo: str
    estado: str                      # nuevo | repetido | error
    documento_id: int | None = None
    proveedor: str = ""
    total: float = 0.0
    alertas: list[Alerta] = field(default_factory=list)
    error: str = ""


def procesar_carpeta(con, entrada: Path, extractor, mover_a: Path | None = None) -> list[Resultado]:
    """Procesa en orden alfabético (conviene nombrar los archivos con la fecha adelante)."""
    resultados = []
    for ruta in sorted(p for p in entrada.iterdir() if p.suffix.lower() in EXTENSIONES):
        h = hash_archivo(ruta)
        if db.ya_procesado(con, h):
            resultados.append(Resultado(ruta.name, "repetido"))
            continue
        try:
            doc = extractor.extraer(ruta)
        except ErrorExtraccion as e:
            resultados.append(Resultado(ruta.name, "error", error=str(e)))
            continue  # el archivo queda en la entrada para reintentar
        alertas = validar(
            doc,
            es_duplicado=lambda prov, num: db.buscar_duplicado(con, prov, num),
            ultimo_precio=lambda prov, desc: db.ultimo_precio(con, prov, desc),
            proveedor_conocido=lambda prov, cuit: db.proveedor_conocido(con, prov, cuit),
        )
        doc_id = db.guardar(con, ruta.name, h, doc, alertas, extractor.nombre)
        resultados.append(Resultado(ruta.name, "nuevo", doc_id, doc.proveedor, doc.total, alertas))
        if mover_a:
            mover_a.mkdir(parents=True, exist_ok=True)
            shutil.move(str(ruta), mover_a / ruta.name)
    return resultados
