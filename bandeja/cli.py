"""Línea de comandos: python -m bandeja <comando>."""
import argparse
import shutil
import sys
from datetime import date
from pathlib import Path

from . import db
from .extraer import ExtractorClaude, ExtractorDemo
from .formato import pesos
from .panel import generar_panel
from .procesar import procesar_carpeta
from .reporte import enviar_por_mail, exportar_excel, resumen, resumen_texto

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLOS = RAIZ / "ejemplos"
ICONO = {"alta": "‼", "media": "!", "info": "·"}


def _imprimir(resultados):
    for r in resultados:
        if r.estado == "repetido":
            print(f"  = {r.archivo}: ya procesado")
        elif r.estado == "error":
            print(f"  ✗ {r.archivo}: {r.error}")
        else:
            print(f"  ✓ {r.archivo} → #{r.documento_id} {r.proveedor} {pesos(r.total)}")
            for a in r.alertas:
                print(f"      {ICONO[a.gravedad]} {a.mensaje}")
    nuevos = sum(r.estado == "nuevo" for r in resultados)
    errores = sum(r.estado == "error" for r in resultados)
    print(f"\n{nuevos} nuevos, {errores} con error.")


def main(argv=None):
    p = argparse.ArgumentParser(prog="bandeja", description="Lee comprobantes de proveedores con IA y los verifica.")
    p.add_argument("--db", default="bandeja.sqlite", help="archivo de base de datos (default: bandeja.sqlite)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("procesar", help="procesa los documentos nuevos de una carpeta")
    s.add_argument("--entrada", default="entrada")
    s.add_argument("--mover", metavar="CARPETA", help="mover cada archivo procesado a esta carpeta")
    s.add_argument("--demo", action="store_true", help="usar extracciones de ejemplo en vez de la API")
    s.add_argument("--modelo", help="modelo de Claude (default: claude-opus-5-5 o BANDEJA_MODELO)")

    s = sub.add_parser("proveedores", help="carga el padrón de proveedores habituales desde un CSV nombre;cuit")
    s.add_argument("csv")

    sub.add_parser("pendientes", help="lista lo que falta revisar")
    for nombre in ("aprobar", "rechazar"):
        s = sub.add_parser(nombre, help=f"{nombre} un documento por su número")
        s.add_argument("id", type=int)

    s = sub.add_parser("reporte", help="resumen de los últimos días")
    s.add_argument("--dias", type=int, default=7)
    s.add_argument("--hasta", type=date.fromisoformat, help="fecha final AAAA-MM-DD (default: hoy)")
    s.add_argument("--excel", metavar="ARCHIVO", help="adjuntar exportación a Excel")
    s.add_argument("--enviar", action="store_true", help="mandar el resumen por mail (ver README)")

    s = sub.add_parser("exportar", help="exporta todo a Excel")
    s.add_argument("archivo", nargs="?", default="bandeja.xlsx")

    s = sub.add_parser("panel", help="genera el panel de revisión (HTML estático)")
    s.add_argument("--salida", default="panel")
    s.add_argument("--originales", help="carpeta con los archivos originales, para enlazarlos")

    s = sub.add_parser("demo", help="arma la demo completa con los ejemplos (sin API)")
    s.add_argument("--salida", default=str(RAIZ / "docs" / "demo"))

    a = p.parse_args(argv)

    if a.cmd == "demo":
        salida = Path(a.salida)
        if salida.exists():
            shutil.rmtree(salida)
        salida.mkdir(parents=True)
        con = db.conectar(":memory:")
        db.cargar_padron(con, EJEMPLOS / "proveedores.csv")
        print("Procesando ejemplos (modo demo):")
        _imprimir(procesar_carpeta(con, EJEMPLOS / "entrada", ExtractorDemo(EJEMPLOS / "extracciones")))
        exportar_excel(con, salida / "bandeja.xlsx")
        ultima = max(d["fecha"] for d in db.documentos_completos(con) if d["fecha"])
        (salida / "resumen.txt").write_text(resumen_texto(resumen(con, date.fromisoformat(ultima), 14)) + "\n",
                                            encoding="utf-8")
        generar_panel(con, salida, originales=EJEMPLOS / "entrada", demo=True)
        print(f"\nDemo lista en {salida}/index.html (más bandeja.xlsx y resumen.txt)")
        return 0

    con = db.conectar(a.db)

    if a.cmd == "proveedores":
        print(f"{db.cargar_padron(con, a.csv)} proveedores en el padrón.")
    elif a.cmd == "procesar":
        extractor = ExtractorDemo(EJEMPLOS / "extracciones") if a.demo else ExtractorClaude(a.modelo)
        _imprimir(procesar_carpeta(con, Path(a.entrada), extractor, Path(a.mover) if a.mover else None))
    elif a.cmd == "pendientes":
        docs = [d for d in db.documentos_completos(con) if d["estado"] == "pendiente"]
        for d in docs:
            marcas = "".join(ICONO[x["gravedad"]] for x in d["alertas"])
            print(f"#{d['id']:<4} {d['fecha'] or '—':10}  {d['proveedor'][:32]:32} {pesos(d['total']):>14}  {marcas}")
        print(f"\n{len(docs)} pendientes.")
    elif a.cmd in ("aprobar", "rechazar"):
        ok = db.cambiar_estado(con, a.id, "aprobado" if a.cmd == "aprobar" else "rechazado")
        print("Listo." if ok else f"No existe el documento #{a.id}.")
        return 0 if ok else 1
    elif a.cmd == "reporte":
        texto = resumen_texto(resumen(con, a.hasta, a.dias))
        print(texto)
        adjunto = exportar_excel(con, Path(a.excel)) if a.excel else None
        if a.enviar:
            enviar_por_mail("Resumen de compras", texto, adjunto)
            print("\nEnviado por mail.")
    elif a.cmd == "exportar":
        print(f"Exportado a {exportar_excel(con, Path(a.archivo))}")
    elif a.cmd == "panel":
        print(f"Panel en {generar_panel(con, Path(a.salida), Path(a.originales) if a.originales else None)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
