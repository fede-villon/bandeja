"""Extracción de datos de facturas, remitos y pedidos.

Dos implementaciones con la misma interfaz:
- ExtractorClaude: usa la API de Claude con salida estructurada (la respuesta
  siempre respeta el esquema de `Documento`).
- ExtractorDemo: devuelve extracciones guardadas en `ejemplos/extracciones/`.
  Sirve para probar el sistema y correr los tests sin clave ni costo.
"""
import json
import os
from pathlib import Path

from .leer import bloques_de
from .modelos import Documento

MODELO_POR_DEFECTO = "claude-opus-5-5"

SISTEMA = """Sos un asistente administrativo de un almacén de barrio en Argentina. Recibís comprobantes de \
proveedores (facturas, remitos, pedidos, presupuestos), en PDF o por email, y transcribís sus datos.

Reglas:
- Copiá los importes exactamente como están impresos, aunque las cuentas no den: el sistema verifica las \
sumas por su cuenta y necesita los números originales para detectar errores.
- Los importes van en pesos, como número sin símbolo ni separador de miles (12.500,50 → 12500.5).
- Fechas en formato AAAA-MM-DD.
- Si un dato no figura, dejalo en null. No lo inventes ni lo calcules.
- En `observaciones` anotá solo algo que una persona tendría que mirar (texto ilegible, tachaduras, \
condiciones de pago inusuales). Si no hay nada, null."""


class ErrorExtraccion(Exception):
    pass


class ExtractorClaude:
    def __init__(self, modelo: str | None = None):
        import anthropic  # solo hace falta en modo real

        self.anthropic = anthropic
        self.cliente = anthropic.Anthropic()  # toma ANTHROPIC_API_KEY o el perfil de `ant auth login`
        self.modelo = modelo or os.environ.get("BANDEJA_MODELO", MODELO_POR_DEFECTO)
        self.nombre = f"claude:{self.modelo}"

    def extraer(self, ruta: Path) -> Documento:
        contenido = bloques_de(ruta) + [{"type": "text", "text": "Transcribí los datos de este comprobante."}]
        try:
            respuesta = self.cliente.beta.messages.parse(
                model=self.modelo,
                max_tokens=16000,
                system=SISTEMA,
                messages=[{"role": "user", "content": contenido}],
                output_format=Documento,
                output_config={"effort": "medium"},
                # Si el modelo rechaza el pedido, la API lo reintenta sola con un modelo alternativo.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except self.anthropic.RateLimitError as e:
            raise ErrorExtraccion("Límite de uso de la API alcanzado; reintentar más tarde.") from e
        except self.anthropic.APIStatusError as e:
            raise ErrorExtraccion(f"La API respondió {e.status_code}: {e.message}") from e
        except self.anthropic.APIConnectionError as e:
            raise ErrorExtraccion("Sin conexión con la API.") from e

        if respuesta.stop_reason == "refusal":
            raise ErrorExtraccion("El modelo no procesó este documento; revisarlo a mano.")
        if respuesta.stop_reason == "max_tokens" or respuesta.parsed_output is None:
            raise ErrorExtraccion("La respuesta quedó incompleta; revisarlo a mano.")
        return respuesta.parsed_output


class ExtractorDemo:
    nombre = "demo"

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta

    def extraer(self, ruta: Path) -> Documento:
        guardado = self.carpeta / (ruta.stem + ".json")
        if not guardado.exists():
            raise ErrorExtraccion(f"No hay extracción de demo para {ruta.name}.")
        return Documento.model_validate(json.loads(guardado.read_text(encoding="utf-8")))
