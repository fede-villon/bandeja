"""Genera los comprobantes ficticios de ejemplo y sus extracciones de referencia.

Uso:  python ejemplos/generar_ejemplos.py

Crea en ejemplos/entrada/ facturas en PDF y emails (.eml), y en ejemplos/extracciones/
el JSON que describe lo que está impreso en cada uno (incluidos los errores puestos a
propósito). Ese JSON lo usa el modo demo y sirve para comparar contra la extracción real.
Todos los datos son inventados.
"""
import json
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime
from pathlib import Path

from fpdf import FPDF

AQUI = Path(__file__).parent
ENTRADA, EXTRACCIONES = AQUI / "entrada", AQUI / "extracciones"
CLIENTE = "Almacén Doña Marta · Av. San Martín 1450 · Concepción del Uruguay"

LITORAL = ("Distribuidora Del Litoral S.A.", "30-71234567-8", "pedidos@dellitoral.example")
PRADERA = ("Lácteos La Pradera S.R.L.", "30-70987654-3", "facturacion@lapradera.example")
NORTE = ("Bebidas Norte", None, "ventas@bebidasnorte.example")
DON_JULIO = ("Panificados Don Julio", None, "donjulio.panificados@example.com")
LIMPIEZA = ("Limpieza Total S.R.L.", None, "admin@limpiezatotal.example")


def item(desc, cant, precio, unidad="unidad", subtotal=None):
    return {"descripcion": desc, "cantidad": cant, "unidad": unidad, "precio_unitario": precio,
            "subtotal": subtotal if subtotal is not None else round(cant * precio, 2)}


def doc(tipo, prov, numero, fecha, items, iva=True, total=None, observaciones=None):
    sub = round(sum(i["subtotal"] for i in items), 2)
    imp = round(sub * 0.21, 2) if iva else None
    return {"tipo": tipo, "proveedor": prov[0], "cuit": prov[1], "numero": numero, "fecha": fecha,
            "items": items, "subtotal": sub if iva else None, "impuestos": imp,
            "total": total if total is not None else round(sub + (imp or 0), 2), "observaciones": observaciones}


def p(n):
    return f"$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pdf_factura(d, ruta: Path):
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.set_auto_page_break(False)
    pdf.set_draw_color(60, 60, 60)
    # Encabezado
    pdf.rect(10, 10, 190, 42)
    pdf.line(105, 10, 105, 52)
    pdf.set_xy(98, 12); pdf.set_font("Helvetica", "B", 22); pdf.cell(14, 14, "A", border=1, align="C")
    pdf.set_xy(14, 14); pdf.set_font("Helvetica", "B", 15); pdf.cell(85, 8, d["proveedor"])
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(14, 24); pdf.multi_cell(80, 4.5, "Responsable Inscripto\nRuta 14 km 128 · Entre Ríos\n"
                                       + (f"CUIT: {d['cuit']}" if d["cuit"] else "CUIT: (no informado)"))
    pdf.set_xy(115, 14); pdf.set_font("Helvetica", "B", 14); pdf.cell(80, 8, "FACTURA")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(115, 24); pdf.cell(80, 6, f"N° {d['numero']}")
    fecha = datetime.fromisoformat(d["fecha"]).strftime("%d/%m/%Y")
    pdf.set_xy(115, 31); pdf.cell(80, 6, f"Fecha de emisión: {fecha}")
    pdf.set_xy(115, 38); pdf.cell(80, 6, "Condición de venta: Cuenta corriente 15 días")
    pdf.set_xy(10, 56); pdf.set_font("Helvetica", "", 9); pdf.cell(190, 7, "Cliente: " + CLIENTE, border=1)
    # Tabla
    y = 68
    pdf.set_xy(10, y); pdf.set_font("Helvetica", "B", 9); pdf.set_fill_color(235, 235, 235)
    for texto, ancho, al in (("Descripción", 92, "L"), ("Cant.", 18, "R"), ("Unidad", 22, "L"),
                             ("Precio unit.", 29, "R"), ("Importe", 29, "R")):
        pdf.cell(ancho, 7, texto, border=1, align=al, fill=True)
    pdf.set_font("Helvetica", "", 9)
    for it in d["items"]:
        y += 7
        pdf.set_xy(10, y)
        pdf.cell(92, 7, it["descripcion"], border=1)
        pdf.cell(18, 7, f"{it['cantidad']:g}", border=1, align="R")
        pdf.cell(22, 7, it["unidad"], border=1)
        pdf.cell(29, 7, p(it["precio_unitario"]), border=1, align="R")
        pdf.cell(29, 7, p(it["subtotal"]), border=1, align="R")
    # Totales
    y += 14
    for etiqueta, valor, negrita in (("Subtotal", d["subtotal"], False), ("IVA 21 %", d["impuestos"], False),
                                     ("TOTAL", d["total"], True)):
        pdf.set_xy(132, y); pdf.set_font("Helvetica", "B" if negrita else "", 11 if negrita else 9)
        pdf.cell(39, 7, etiqueta, border=1); pdf.cell(29, 7, p(valor), border=1, align="R")
        y += 7
    pdf.set_xy(10, 280); pdf.set_font("Helvetica", "I", 7)
    pdf.cell(190, 4, "Documento ficticio generado para la demo de Bandeja. No válido como comprobante.", align="C")
    pdf.output(str(ruta))


def eml(ruta: Path, de, asunto, fecha, cuerpo, adjunto: Path | None = None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = f"{de[0]} <{de[2]}>", "compras@almacendonamarta.example", asunto
    m["Date"] = format_datetime(datetime.fromisoformat(fecha + "T09:30:00-03:00"))
    m.set_content(cuerpo)
    if adjunto:
        m.add_attachment(adjunto.read_bytes(), maintype="application", subtype="pdf", filename=adjunto.name)
    ruta.write_bytes(bytes(m))


def main():
    ENTRADA.mkdir(parents=True, exist_ok=True)
    EXTRACCIONES.mkdir(parents=True, exist_ok=True)
    for viejo in list(ENTRADA.iterdir()) + list(EXTRACCIONES.iterdir()):
        viejo.unlink()

    docs = {}

    # 1. Factura normal
    docs["2026-11-03_litoral_factura_1234"] = d1 = doc("factura", LITORAL, "0003-00001234", "2026-11-03", [
        item("Yerba mate 1 kg", 24, 3900), item("Azúcar 1 kg", 30, 1100),
        item("Fideos tallarín 500 g", 40, 950), item("Aceite girasol 1,5 L", 12, 2600)])
    pdf_factura(d1, ENTRADA / "2026-11-03_litoral_factura_1234.pdf")

    # 2. Factura normal
    docs["2026-11-04_pradera_factura_0567"] = d2 = doc("factura", PRADERA, "0001-00000567", "2026-11-04", [
        item("Leche entera 1 L", 48, 900), item("Yogur bebible 1 L", 12, 1300), item("Manteca 200 g", 20, 1600)])
    pdf_factura(d2, ENTRADA / "2026-11-04_pradera_factura_0567.pdf")

    # 3. Remito que llega como texto en el cuerpo de un email
    d3 = doc("remito", NORTE, "0002-00004410", "2026-11-05", [
        item("Gaseosa cola 2,25 L", 24, 2100, "botella"), item("Agua mineral 2 L", 24, 700, "botella"),
        item("Cerveza lata 473 ml", 48, 1100, "lata")], iva=False)
    docs["2026-11-05_bebidas_norte_remito"] = d3
    eml(ENTRADA / "2026-11-05_bebidas_norte_remito.eml", NORTE, "Remito 0002-00004410 - entrega jueves",
        "2026-11-05",
        "Hola Marta, te paso el detalle de lo que te dejamos hoy (remito 0002-00004410):\n\n"
        "- 24 botellas de gaseosa cola 2,25 L a $2.100 c/u = $50.400\n"
        "- 24 botellas de agua mineral 2 L a $700 c/u = $16.800\n"
        "- 48 latas de cerveza 473 ml a $1.100 c/u = $52.800\n\n"
        "Total del remito: $120.000. La factura te llega a fin de mes.\n\nSaludos,\nRaúl - Bebidas Norte")

    # 4. Aumento de precio: la yerba pasa de $3.900 a $4.500 (+15 %); el azúcar sube menos del umbral
    docs["2026-11-10_litoral_factura_1301"] = d4 = doc("factura", LITORAL, "0003-00001301", "2026-11-10", [
        item("Yerba mate 1 kg", 24, 4500), item("Azúcar 1 kg", 30, 1150), item("Café molido 250 g", 12, 3200)])
    pdf_factura(d4, ENTRADA / "2026-11-10_litoral_factura_1301.pdf")

    # 5. Total mal sumado: el total impreso tiene $2.000 de más
    d5 = doc("factura", PRADERA, "0001-00000589", "2026-11-11", [
        item("Leche entera 1 L", 48, 900), item("Queso cremoso 1 kg", 5, 6200, "kg"),
        item("Crema de leche 200 ml", 24, 1100)])
    d5["total"] = round(d5["total"] + 2000, 2)
    docs["2026-11-11_pradera_factura_0589"] = d5
    pdf_factura(d5, ENTRADA / "2026-11-11_pradera_factura_0589.pdf")

    # 6. Duplicado: reenvían por mail la factura 567 que ya había llegado
    docs["2026-11-12_reenvio_pradera_0567"] = d2
    eml(ENTRADA / "2026-11-12_reenvio_pradera_0567.eml", PRADERA, "Reenvío factura 567", "2026-11-12",
        "Buen día, te reenvío la factura 0001-00000567 por si no te había llegado.\n\nAdministración - La Pradera",
        adjunto=ENTRADA / "2026-11-04_pradera_factura_0567.pdf")

    # 7. Presupuesto de un proveedor nuevo, con condición de validez
    d7 = doc("presupuesto", DON_JULIO, None, "2026-11-13", [
        item("Pan francés", 30, 1600, "kg"), item("Facturas", 10, 3100, "docena")], iva=False,
        observaciones="Precios válidos hasta el 30/11/2026; entrega diaria antes de las 7.")
    docs["2026-11-13_don_julio_presupuesto"] = d7
    eml(ENTRADA / "2026-11-13_don_julio_presupuesto.eml", DON_JULIO, "Presupuesto pan y facturas", "2026-11-13",
        "Hola, como hablamos te paso precios para empezar a trabajar:\n\n"
        "Pan francés: $1.600 el kilo (calculamos unos 30 kg por semana = $48.000)\n"
        "Facturas: $3.100 la docena (10 docenas = $31.000)\n\n"
        "Total estimado semanal: $79.000.\n"
        "Precios válidos hasta el 30/11/2026. Entregamos todos los días antes de las 7.\n\nJulio")

    # 8. Proveedor nuevo, sin CUIT y con una línea mal calculada (24 × $900 = $21.600, dice $22.600)
    d8 = doc("factura", LIMPIEZA, "0005-00000088", "2026-11-16", [
        item("Lavandina 1 L", 24, 600), item("Detergente 500 ml", 24, 900, subtotal=22600),
        item("Papel higiénico x4", 12, 1800, "pack")])
    docs["2026-11-16_limpieza_total_factura"] = d8
    pdf_factura(d8, ENTRADA / "2026-11-16_limpieza_total_factura.pdf")

    for nombre, datos in docs.items():
        (EXTRACCIONES / f"{nombre}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
    print(f"{len(docs)} comprobantes generados en {ENTRADA}")


if __name__ == "__main__":
    main()
