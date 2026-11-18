"""Recorrido completo con los comprobantes de ejemplo (sin API)."""
import json
from datetime import date
from pathlib import Path

import pytest
from openpyxl import load_workbook

from bandeja import db
from bandeja.cli import EJEMPLOS, main
from bandeja.extraer import ExtractorDemo
from bandeja.panel import generar_panel
from bandeja.procesar import procesar_carpeta
from bandeja.reporte import exportar_excel, resumen

ESPERADO = {
    "2026-11-03_litoral_factura_1234.pdf": [],
    "2026-11-04_pradera_factura_0567.pdf": [],
    "2026-11-05_bebidas_norte_remito.eml": [],
    "2026-11-10_litoral_factura_1301.pdf": ["aumento"],
    "2026-11-11_pradera_factura_0589.pdf": ["total"],
    "2026-11-12_reenvio_pradera_0567.eml": ["duplicado"],
    "2026-11-13_don_julio_presupuesto.eml": ["proveedor_nuevo", "revisar"],
    "2026-11-16_limpieza_total_factura.pdf": ["linea", "proveedor_nuevo", "dato_faltante"],
}


@pytest.fixture
def con():
    c = db.conectar(":memory:")
    db.cargar_padron(c, EJEMPLOS / "proveedores.csv")
    return c


@pytest.fixture
def procesado(con):
    resultados = procesar_carpeta(con, EJEMPLOS / "entrada", ExtractorDemo(EJEMPLOS / "extracciones"))
    return con, resultados


def test_cada_ejemplo_dispara_las_alertas_esperadas(procesado):
    _, resultados = procesado
    assert {r.archivo: [a.tipo for a in r.alertas] for r in resultados} == ESPERADO


def test_no_procesa_dos_veces_el_mismo_archivo(procesado):
    con, _ = procesado
    otra_vez = procesar_carpeta(con, EJEMPLOS / "entrada", ExtractorDemo(EJEMPLOS / "extracciones"))
    assert {r.estado for r in otra_vez} == {"repetido"}


def test_resumen_no_suma_duplicados_ni_presupuestos(procesado):
    con, _ = procesado
    r = resumen(con, date(2026, 11, 16), 14)
    assert r["documentos"] == 8
    assert r["total"] == pytest.approx(236918 + 109868 + 120000 + 218889 + 123726 + 70906)
    assert "Panificados Don Julio" not in r["gasto"]


def test_aprobar_y_rechazar(procesado):
    con, _ = procesado
    assert db.cambiar_estado(con, 1, "aprobado")
    assert db.cambiar_estado(con, 6, "rechazado")
    assert not db.cambiar_estado(con, 999, "aprobado")
    estados = {d["id"]: d["estado"] for d in db.documentos_completos(con)}
    assert estados[1] == "aprobado" and estados[6] == "rechazado"


def test_proveedor_aprobado_deja_de_ser_nuevo(con):
    assert not db.proveedor_conocido(con, "Limpieza Total S.R.L.")
    procesar_carpeta(con, EJEMPLOS / "entrada", ExtractorDemo(EJEMPLOS / "extracciones"))
    db.cambiar_estado(con, 8, "aprobado")
    assert db.proveedor_conocido(con, "Limpieza Total S.R.L.")


def test_excel_tiene_las_tres_hojas(procesado, tmp_path):
    con, _ = procesado
    wb = load_workbook(exportar_excel(con, tmp_path / "x.xlsx"))
    assert wb.sheetnames == ["Documentos", "Líneas", "Alertas"]
    assert wb["Documentos"].max_row == 9           # encabezado + 8
    assert wb["Alertas"].max_row == 1 + sum(len(v) for v in ESPERADO.values())


def test_panel_embebe_los_datos_sin_romper_el_html(procesado, tmp_path):
    con, _ = procesado
    html = generar_panel(con, tmp_path, originales=EJEMPLOS / "entrada", demo=True).read_text(encoding="utf-8")
    bloque = html.split('<script id="datos" type="application/json">')[1].split("</script>")[0]
    datos = json.loads(bloque)
    assert len(datos["documentos"]) == 8 and datos["demo"] is True
    assert (tmp_path / "archivos" / "2026-11-05_bebidas_norte_remito.eml.txt").exists()


def test_comando_demo(tmp_path, capsys):
    assert main(["demo", "--salida", str(tmp_path / "demo")]) == 0
    assert (tmp_path / "demo" / "index.html").exists()
    assert "Total comprado: $880.307,00" in (tmp_path / "demo" / "resumen.txt").read_text(encoding="utf-8")
