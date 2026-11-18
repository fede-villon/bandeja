"""Extracción de datos de facturas, remitos y pedidos.

Dos implementaciones con la misma interfaz:
- ExtractorLLM: usa un modelo de lenguaje gratuito a través de la interfaz
  compatible con OpenAI. Por defecto, un modelo que corre en la propia PC con
  Ollama (gratis, sin límites y sin mandar las facturas a internet). Con las
  variables de entorno se puede apuntar a otro servidor compatible.
- ExtractorDemo: devuelve extracciones guardadas en `ejemplos/extracciones/`.
  Sirve para probar el sistema y correr los tests sin instalar nada.
"""
import json
import os
import re
from pathlib import Path

from pydantic import ValidationError

from .leer import SinTexto, texto_de
from .modelos import Documento

URL_POR_DEFECTO = "http://localhost:11434/v1"     # Ollama en la misma PC
MODELO_POR_DEFECTO = "qwen2.5:7b-instruct"   # medido con ejemplos/evaluar.py; ver README

EJEMPLO = {
    "tipo": "factura", "proveedor": "Distribuidora Ejemplo S.A.", "cuit": "30-12345678-9",
    "numero": "0001-00000123", "fecha": "2026-11-03",
    "items": [{"descripcion": "Yerba mate 1 kg", "cantidad": 10, "unidad": "unidad",
               "precio_unitario": 3900, "subtotal": 39000}],
    "subtotal": 39000, "impuestos": 8190, "total": 47190, "observaciones": None,
}

SISTEMA = f"""Sos un asistente administrativo de un almacén de barrio en Argentina. Recibís el texto de \
comprobantes de proveedores (facturas, remitos, pedidos, presupuestos) y devolvés sus datos en JSON.

Respondé solo con un objeto JSON con exactamente estas claves (ejemplo):
{json.dumps(EJEMPLO, ensure_ascii=False)}

Reglas:
- "tipo" es uno de: factura, remito, pedido, presupuesto, otro.
- Copiá cada importe exactamente como está impreso, aunque las cuentas no den. NO corrijas subtotales ni \
totales mal calculados: el sistema verifica las sumas por su cuenta y necesita los números originales para \
detectar errores del proveedor.
- "total" es el importe final del comprobante (en un presupuesto, el total estimado que figura).
- En las facturas argentinas la letra del comprobante (A, B o C) suele quedar pegada al nombre del proveedor \
en el texto (por ejemplo "ADistribuidora…"): no la incluyas en "proveedor".
- Importes como número sin símbolo ni separador de miles (12.500,50 → 12500.5).
- Fechas en formato AAAA-MM-DD.
- Si un dato no figura, usá null. No lo inventes ni lo calcules.
- En "observaciones" anotá solo algo que una persona tendría que mirar (condiciones de pago o de validez \
inusuales, texto confuso). Si no hay nada, null."""


class ErrorExtraccion(Exception):
    pass


def _json_de(texto: str) -> dict:
    """Saca el objeto JSON de la respuesta (los modelos de razonamiento pueden agregar <think>…</think>)."""
    texto = re.sub(r"<think>.*?</think>", "", texto or "", flags=re.S).strip()
    inicio, fin = texto.find("{"), texto.rfind("}")
    if inicio == -1 or fin <= inicio:
        raise ValueError("la respuesta no trae JSON")
    return json.loads(texto[inicio:fin + 1])


# Letra del tipo de factura (A, B, C) que pypdf deja pegada al nombre: "ADistribuidora…" → "Distribuidora…"
LETRA_PEGADA = re.compile(r"^[ABC](?=[A-ZÁÉÍÓÚÑ][a-záéíóúñ])")
IMPORTE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+,\d{1,2}|\d+")


def importes_en(texto: str) -> set[float]:
    """Todos los números que aparecen en el texto, leídos con formato argentino (12.500,50)."""
    return {float(m.replace(".", "").replace(",", ".")) for m in IMPORTE.findall(texto)}


def _renglones_de(descripcion: str, texto: str) -> str:
    """Renglones del documento que mencionan el producto (o todo el texto si no se encuentran)."""
    palabras = [p for p in re.findall(r"\w+", descripcion.lower()) if len(p) > 2][:2]
    renglones = [r for r in texto.splitlines() if palabras and all(p in r.lower() for p in palabras)]
    return "\n".join(renglones) or texto


def no_figuran(doc: Documento, texto: str) -> list[str]:
    """Importes que el modelo devolvió pero que no están en el documento (posible error de lectura o "corrección").

    Cada importe de una línea se busca en el renglón de ese producto; el total, en todo el documento.
    """
    esta = lambda v, en: v is None or any(abs(v - p) < 0.01 for p in importes_en(en))
    faltan = []
    for it in doc.items:
        donde = _renglones_de(it.descripcion, texto)
        faltan += [f"«{it.descripcion}» {etiqueta} {v:g}"
                   for etiqueta, v in (("subtotal", it.subtotal), ("precio", it.precio_unitario)) if not esta(v, donde)]
    if not esta(doc.total, texto):
        faltan.append(f"total {doc.total:g}")
    return faltan


class ExtractorLLM:
    def __init__(self, modelo: str | None = None, cliente=None):
        if cliente is None:
            import openai  # solo hace falta en modo real

            self.openai = openai
            cliente = openai.OpenAI(
                base_url=os.environ.get("BANDEJA_URL", URL_POR_DEFECTO),
                api_key=os.environ.get("BANDEJA_API_KEY", "ollama"),   # Ollama no pide clave
                timeout=float(os.environ.get("BANDEJA_TIMEOUT", "300")),
            )
        else:
            self.openai = None
        self.cliente = cliente
        self.modelo = modelo or os.environ.get("BANDEJA_MODELO", MODELO_POR_DEFECTO)
        self.nombre = f"llm:{self.modelo}"

    def _pedir(self, mensajes):
        try:
            r = self.cliente.chat.completions.create(
                model=self.modelo, messages=mensajes, temperature=0,
                response_format={"type": "json_object"}, max_tokens=2000,
            )
        except Exception as e:  # errores de red o del servidor del modelo
            if self.openai and isinstance(e, self.openai.APIConnectionError):
                raise ErrorExtraccion("No hay conexión con el modelo. ¿Está abierto Ollama? (ollama serve)") from e
            if self.openai and isinstance(e, self.openai.NotFoundError):
                raise ErrorExtraccion(f"El modelo «{self.modelo}» no está instalado: ollama pull {self.modelo}") from e
            if self.openai and isinstance(e, self.openai.APIStatusError):
                raise ErrorExtraccion(f"El servidor del modelo respondió {e.status_code}.") from e
            raise
        opcion = r.choices[0]
        if opcion.finish_reason == "length":
            raise ErrorExtraccion("La respuesta quedó cortada; revisalo a mano.")
        return opcion.message.content or ""

    def extraer(self, ruta: Path) -> Documento:
        try:
            texto = texto_de(ruta)
        except SinTexto as e:
            raise ErrorExtraccion(str(e)) from e
        mensajes = [{"role": "system", "content": SISTEMA},
                    {"role": "user", "content": "Transcribí este comprobante a JSON:\n\n" + texto}]
        # Los modelos chicos a veces se equivocan en el formato: un reintento, avisándole el error.
        for intento in range(2):
            respuesta = self._pedir(mensajes)
            try:
                doc = Documento.model_validate(_json_de(respuesta))
                return self._controlar(doc, texto)
            except (ValueError, ValidationError) as e:
                if intento == 1:
                    raise ErrorExtraccion("El modelo no devolvió datos válidos; revisalo a mano.") from e
                mensajes += [{"role": "assistant", "content": respuesta},
                             {"role": "user", "content": f"El JSON no es válido ({str(e)[:300]}). "
                                                         "Devolvé solo el objeto JSON corregido, con las claves del ejemplo."}]


    @staticmethod
    def _controlar(doc: Documento, texto: str) -> Documento:
        doc.proveedor = LETRA_PEGADA.sub("", doc.proveedor.strip())
        faltan = no_figuran(doc, texto)
        if faltan:
            aviso = "Estos importes no figuran en el documento, revisar contra el original: " + "; ".join(faltan)
            doc.observaciones = f"{doc.observaciones} · {aviso}" if doc.observaciones else aviso
        return doc


class ExtractorDemo:
    nombre = "demo"

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta

    def extraer(self, ruta: Path) -> Documento:
        guardado = self.carpeta / (ruta.stem + ".json")
        if not guardado.exists():
            raise ErrorExtraccion(f"No hay extracción de demo para {ruta.name}.")
        return Documento.model_validate(json.loads(guardado.read_text(encoding="utf-8")))
