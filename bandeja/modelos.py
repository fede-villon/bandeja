"""Estructura de los datos que se extraen de cada documento."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Item(BaseModel):
    descripcion: str = Field(description="Producto o servicio tal como figura en el documento")
    cantidad: float
    unidad: Optional[str] = Field(default=None, description="unidad, kg, caja, pack, etc.")
    precio_unitario: float = Field(description="Precio por unidad, en pesos, sin símbolo")
    subtotal: float = Field(description="Importe de la línea tal como figura en el documento")


class Documento(BaseModel):
    tipo: Literal["factura", "remito", "pedido", "presupuesto", "otro"]
    proveedor: str = Field(description="Razón social o nombre del proveedor que emite el documento")
    cuit: Optional[str] = Field(default=None, description="CUIT del proveedor con formato XX-XXXXXXXX-X")
    numero: Optional[str] = Field(default=None, description="Número de comprobante, ej. 0001-00001234")
    fecha: Optional[str] = Field(default=None, description="Fecha de emisión en formato AAAA-MM-DD")
    items: list[Item]
    subtotal: Optional[float] = Field(default=None, description="Subtotal antes de impuestos, si figura")
    impuestos: Optional[float] = Field(default=None, description="Suma de IVA y percepciones, si figura")
    total: float = Field(description="Total final del documento tal como figura impreso")
    observaciones: Optional[str] = Field(
        default=None, description="Algo raro o ilegible que convenga revisar a mano; null si no hay nada"
    )
