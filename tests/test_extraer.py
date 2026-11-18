"""Lectura de archivos y llamada a la API (con un cliente falso: no gasta ni necesita clave)."""
import json
from types import SimpleNamespace

import anthropic
import pytest

from bandeja.cli import EJEMPLOS
from bandeja.extraer import ErrorExtraccion, ExtractorClaude
from bandeja.leer import bloques_de
from bandeja.modelos import Documento

ENTRADA = EJEMPLOS / "entrada"


def test_pdf_va_como_documento():
    (b,) = bloques_de(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
    assert b["type"] == "document" and b["source"]["media_type"] == "application/pdf"


def test_email_con_adjunto_trae_el_pdf_y_el_texto():
    bloques = bloques_de(ENTRADA / "2026-11-12_reenvio_pradera_0567.eml")
    assert [b["type"] for b in bloques] == ["document", "text"]
    assert "reenvío la factura" in bloques[1]["text"]


def test_email_de_texto():
    (b,) = bloques_de(ENTRADA / "2026-11-05_bebidas_norte_remito.eml")
    assert "Total del remito: $120.000" in b["text"]


class ClienteFalso:
    def __init__(self, respuesta):
        self.respuesta, self.llamadas = respuesta, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._parse))

    def _parse(self, **kw):
        self.llamadas.append(kw)
        return self.respuesta


def extractor_con(respuesta):
    ex = ExtractorClaude.__new__(ExtractorClaude)
    ex.anthropic, ex.modelo, ex.nombre = anthropic, "claude-opus-5-5", "claude:claude-opus-5-5"
    ex.cliente = ClienteFalso(respuesta)
    return ex


def test_extraccion_correcta_y_parametros_de_la_llamada():
    esperado = Documento.model_validate(json.loads(
        (EJEMPLOS / "extracciones" / "2026-11-03_litoral_factura_1234.json").read_text(encoding="utf-8")))
    ex = extractor_con(SimpleNamespace(stop_reason="end_turn", parsed_output=esperado))
    assert ex.extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf") == esperado
    kw = ex.cliente.llamadas[0]
    assert kw["model"] == "claude-opus-5-5" and kw["output_format"] is Documento
    assert kw["messages"][0]["content"][0]["type"] == "document"


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_respuesta_rechazada_o_incompleta(stop):
    ex = extractor_con(SimpleNamespace(stop_reason=stop, parsed_output=None))
    with pytest.raises(ErrorExtraccion):
        ex.extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
