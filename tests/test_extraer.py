"""Lectura de archivos y llamada al modelo (con un cliente falso: no necesita Ollama)."""
import json
from types import SimpleNamespace

import pytest

from bandeja.cli import EJEMPLOS
from bandeja.extraer import ErrorExtraccion, ExtractorLLM, _json_de, importes_en
from bandeja.leer import SinTexto, texto_de, texto_pdf

ENTRADA = EJEMPLOS / "entrada"
REF = json.loads((EJEMPLOS / "extracciones" / "2026-11-03_litoral_factura_1234.json").read_text(encoding="utf-8"))


def test_pdf_se_lee_como_texto():
    t = texto_de(ENTRADA / "2026-11-11_pradera_factura_0589.pdf")
    assert "0001-00000589" in t and "TOTAL $ 123.726,00" in t


def test_email_con_adjunto_trae_cuerpo_y_pdf():
    t = texto_de(ENTRADA / "2026-11-12_reenvio_pradera_0567.eml")
    assert "reenvío la factura" in t and "[PDF adjunto:" in t and "0001-00000567" in t


def test_email_de_texto():
    assert "Total del remito: $120.000" in texto_de(ENTRADA / "2026-11-05_bebidas_norte_remito.eml")


def test_pdf_sin_texto_se_informa():
    from fpdf import FPDF
    pdf = FPDF(); pdf.add_page()
    with pytest.raises(SinTexto):
        texto_pdf(bytes(pdf.output()), "escaneado.pdf")


def test_json_de_ignora_razonamiento_y_texto_extra():
    assert _json_de('<think>pienso…</think>\nAcá está: {"a": 1} listo') == {"a": 1}
    with pytest.raises(ValueError):
        _json_de("sin json")


class ClienteFalso:
    """Imita client.chat.completions.create y devuelve las respuestas en orden."""
    def __init__(self, *respuestas):
        self.respuestas, self.llamadas = list(respuestas), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._crear))

    def _crear(self, **kw):
        self.llamadas.append(kw)
        contenido, fin = self.respuestas.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=fin, message=SimpleNamespace(content=contenido))])


def test_extraccion_correcta_y_parametros():
    cli = ClienteFalso((json.dumps(REF), "stop"))
    doc = ExtractorLLM("modelo-prueba", cliente=cli).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
    assert doc.total == REF["total"] and len(doc.items) == 4
    kw = cli.llamadas[0]
    assert kw["model"] == "modelo-prueba" and kw["response_format"] == {"type": "json_object"} and kw["temperature"] == 0
    assert "0003-00001234" in kw["messages"][1]["content"]


def test_reintenta_una_vez_si_el_json_es_invalido():
    cli = ClienteFalso(("{no es json", "stop"), (json.dumps(REF), "stop"))
    doc = ExtractorLLM("m", cliente=cli).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
    assert doc.numero == REF["numero"] and len(cli.llamadas) == 2
    assert "no es válido" in cli.llamadas[1]["messages"][-1]["content"]


def test_falla_si_tampoco_sirve_el_segundo_intento():
    cli = ClienteFalso(('{"tipo": "factura"}', "stop"), ('{"tipo": "factura"}', "stop"))
    with pytest.raises(ErrorExtraccion, match="no devolvió datos válidos"):
        ExtractorLLM("m", cliente=cli).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")


def test_respuesta_cortada():
    cli = ClienteFalso(('{"tipo": "fac', "length"))
    with pytest.raises(ErrorExtraccion, match="cortada"):
        ExtractorLLM("m", cliente=cli).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")


def test_saca_la_letra_de_factura_pegada_al_proveedor():
    ref = dict(REF, proveedor="ADistribuidora Del Litoral S.A.")
    doc = ExtractorLLM("m", cliente=ClienteFalso((json.dumps(ref), "stop"))).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
    assert doc.proveedor == "Distribuidora Del Litoral S.A."


def test_lee_importes_con_formato_argentino():
    assert {22600.0, 1100.5, 24.0} <= importes_en("24 x $ 22.600,00 y $ 1.100,50")


def test_importe_corregido_por_el_modelo_se_marca_para_revisar():
    """Si el modelo 'arregla' una línea mal calculada, el importe que devuelve no está en el documento."""
    ref = json.loads((EJEMPLOS / "extracciones" / "2026-11-16_limpieza_total_factura.json").read_text(encoding="utf-8"))
    ref["items"][1]["subtotal"] = 21600   # el original dice 22.600
    doc = ExtractorLLM("m", cliente=ClienteFalso((json.dumps(ref), "stop"))).extraer(ENTRADA / "2026-11-16_limpieza_total_factura.pdf")
    assert "no figuran en el documento" in doc.observaciones and "21600" in doc.observaciones


def test_extraccion_fiel_no_genera_aviso():
    doc = ExtractorLLM("m", cliente=ClienteFalso((json.dumps(REF), "stop"))).extraer(ENTRADA / "2026-11-03_litoral_factura_1234.pdf")
    assert doc.observaciones is None
