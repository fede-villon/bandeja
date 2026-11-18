"""Controles automáticos sobre lo extraído.

La IA lee el documento; estas reglas (código común, sin IA) deciden si algo no
cierra. Así una alerta siempre tiene una explicación concreta y reproducible.
"""
from dataclasses import dataclass
from typing import Callable, Optional

from .formato import cantidad, pesos
from .modelos import Documento

TOLERANCIA_PESOS = 1.0          # diferencias de redondeo aceptadas
UMBRAL_AUMENTO = 0.10           # avisar si un precio sube más de 10 %


@dataclass
class Alerta:
    tipo: str        # total | linea | duplicado | aumento | proveedor_nuevo | dato_faltante | revisar
    gravedad: str    # alta | media | info
    mensaje: str


def normalizar(texto: str) -> str:
    return " ".join(texto.lower().replace(".", " ").split())


def validar(
    doc: Documento,
    *,
    es_duplicado: Callable[[str, str], Optional[int]],
    ultimo_precio: Callable[[str, str], Optional[float]],
    proveedor_conocido: Callable[[str, Optional[str]], bool],
) -> list[Alerta]:
    """Devuelve las alertas del documento. Las funciones consultan el historial guardado."""
    alertas: list[Alerta] = []

    # 1. Cada línea: cantidad × precio = subtotal
    for it in doc.items:
        esperado = round(it.cantidad * it.precio_unitario, 2)
        if abs(esperado - it.subtotal) > TOLERANCIA_PESOS:
            alertas.append(Alerta("linea", "media",
                f"«{it.descripcion}»: {cantidad(it.cantidad)} × {pesos(it.precio_unitario)} da {pesos(esperado)}, "
                f"pero la línea dice {pesos(it.subtotal)}."))

    # 2. Suma de líneas (+ impuestos) = total
    suma = round(sum(it.subtotal for it in doc.items), 2)
    esperado_total = round(suma + (doc.impuestos or 0), 2)
    if abs(esperado_total - doc.total) > TOLERANCIA_PESOS:
        dif = doc.total - esperado_total
        alertas.append(Alerta("total", "alta",
            f"El total impreso es {pesos(doc.total)} pero las líneas{' más impuestos' if doc.impuestos else ''} "
            f"suman {pesos(esperado_total)} (diferencia de {'+' if dif > 0 else '-'}{pesos(abs(dif))})."))

    # 3. Documento repetido (mismo proveedor y número)
    if doc.numero:
        previo = es_duplicado(doc.proveedor, doc.numero)
        if previo is not None:
            alertas.append(Alerta("duplicado", "alta",
                f"El comprobante {doc.numero} de {doc.proveedor} ya se cargó (documento #{previo}). "
                "No pagarlo dos veces."))

    # 4. Aumentos de precio respecto de la última compra al mismo proveedor
    if doc.tipo in ("factura", "remito", "presupuesto"):
        for it in doc.items:
            anterior = ultimo_precio(doc.proveedor, it.descripcion)
            if anterior and it.precio_unitario > anterior * (1 + UMBRAL_AUMENTO):
                pct = (it.precio_unitario / anterior - 1) * 100
                alertas.append(Alerta("aumento", "media",
                    f"«{it.descripcion}» subió {pct:.0f} %: de {pesos(anterior)} a {pesos(it.precio_unitario)}."))

    # 5. Proveedor que no está en el padrón (ni por nombre ni por CUIT)
    if not proveedor_conocido(doc.proveedor, doc.cuit):
        alertas.append(Alerta("proveedor_nuevo", "info",
            f"«{doc.proveedor}» no está en el padrón de proveedores. Verificá que sea real antes de pagar."))

    # 6. Datos que faltan
    faltan = [n for n, v in (("número", doc.numero), ("fecha", doc.fecha), ("CUIT", doc.cuit)) if not v]
    if faltan and doc.tipo == "factura":
        alertas.append(Alerta("dato_faltante", "media", f"A la factura le falta: {', '.join(faltan)}."))

    # 7. Lo que la propia extracción marcó como dudoso
    if doc.observaciones:
        alertas.append(Alerta("revisar", "info", f"Observación de la lectura: {doc.observaciones}"))

    return alertas
