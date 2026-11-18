"""Resumen periódico y exportación a Excel."""
import os
import smtplib
from collections import defaultdict
from datetime import date, timedelta
from email.message import EmailMessage
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import db
from .formato import pesos

MONEDA = '"$"#,##0.00'


def resumen(con, hasta: date | None = None, dias: int = 7) -> dict:
    hasta = hasta or date.today()
    desde = hasta - timedelta(days=dias - 1)
    docs = [d for d in db.documentos_completos(con)
            if d["fecha"] and desde.isoformat() <= d["fecha"] <= hasta.isoformat()]
    gasto = defaultdict(float)
    for d in docs:
        es_dup = any(a["tipo"] == "duplicado" for a in d["alertas"])
        if d["tipo"] in ("factura", "remito") and d["estado"] != "rechazado" and not es_dup:
            gasto[d["proveedor"]] += d["total"]
    alertas = [(d, a) for d in docs for a in d["alertas"] if a["gravedad"] in ("alta", "media")]
    return {
        "desde": desde, "hasta": hasta, "documentos": len(docs),
        "gasto": dict(sorted(gasto.items(), key=lambda kv: -kv[1])),
        "total": sum(gasto.values()),
        "pendientes": [d for d in docs if d["estado"] == "pendiente"],
        "alertas": alertas,
    }


def resumen_texto(r: dict) -> str:
    l = [f"Resumen de compras del {r['desde']:%d/%m} al {r['hasta']:%d/%m/%Y}", ""]
    l.append(f"Documentos recibidos: {r['documentos']}")
    l.append(f"Total comprado: {pesos(r['total'])}")
    l.append("")
    l.append("Por proveedor:")
    for prov, monto in r["gasto"].items():
        l.append(f"  · {prov}: {pesos(monto)}")
    l.append("")
    if r["alertas"]:
        l.append(f"Para revisar ({len(r['alertas'])}):")
        for d, a in r["alertas"]:
            marca = "‼" if a["gravedad"] == "alta" else "·"
            l.append(f"  {marca} #{d['id']} {d['proveedor']}: {a['mensaje']}")
    else:
        l.append("Sin alertas.")
    l.append("")
    l.append(f"Pendientes de aprobar: {len(r['pendientes'])}")
    return "\n".join(l)


def enviar_por_mail(asunto: str, cuerpo: str, adjunto: Path | None = None) -> None:
    """Envía el resumen por SMTP. Se configura con variables de entorno (ver README)."""
    host, usuario = os.environ["BANDEJA_SMTP_HOST"], os.environ["BANDEJA_SMTP_USUARIO"]
    clave, para = os.environ["BANDEJA_SMTP_CLAVE"], os.environ["BANDEJA_MAIL_PARA"]
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = asunto, usuario, para
    msg.set_content(cuerpo)
    if adjunto:
        msg.add_attachment(adjunto.read_bytes(), maintype="application",
                           subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=adjunto.name)
    with smtplib.SMTP(host, int(os.environ.get("BANDEJA_SMTP_PUERTO", "587"))) as s:
        s.starttls()
        s.login(usuario, clave)
        s.send_message(msg)


def exportar_excel(con, destino: Path) -> Path:
    docs = db.documentos_completos(con)
    wb = Workbook()

    def hoja(titulo, encabezado, filas, monedas=(), anchos=None):
        ws = wb.create_sheet(titulo)
        ws.append(encabezado)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="2B3A67")
            c.alignment = Alignment(vertical="center")
        for f in filas:
            ws.append(f)
        for col in monedas:
            for celda in ws[get_column_letter(col)][1:]:
                celda.number_format = MONEDA
        for i, ancho in enumerate(anchos or [], start=1):
            ws.column_dimensions[get_column_letter(i)].width = ancho
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    hoja("Documentos",
         ["ID", "Fecha", "Tipo", "Proveedor", "CUIT", "Número", "Total", "Estado", "Alertas", "Archivo"],
         [(d["id"], d["fecha"], d["tipo"], d["proveedor"], d["cuit"], d["numero"], d["total"], d["estado"],
           len(d["alertas"]), d["archivo"]) for d in docs],
         monedas=(7,), anchos=[6, 12, 12, 30, 16, 18, 14, 12, 9, 40])
    hoja("Líneas",
         ["Documento", "Fecha", "Proveedor", "Descripción", "Cantidad", "Unidad", "Precio unitario", "Subtotal"],
         [(d["id"], d["fecha"], d["proveedor"], i["descripcion"], i["cantidad"], i["unidad"], i["precio_unitario"],
           i["subtotal"]) for d in docs for i in d["items"]],
         monedas=(7, 8), anchos=[11, 12, 30, 34, 10, 10, 16, 14])
    hoja("Alertas",
         ["Documento", "Proveedor", "Gravedad", "Tipo", "Detalle"],
         [(d["id"], d["proveedor"], a["gravedad"], a["tipo"], a["mensaje"]) for d in docs for a in d["alertas"]],
         anchos=[11, 30, 10, 16, 90])
    del wb["Sheet"]
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
