"""Genera el panel de revisión como una página HTML estática (sin servidor)."""
import json
import shutil
from pathlib import Path

from . import db

PLANTILLA = Path(__file__).with_name("plantilla_panel.html")


def generar_panel(con, destino: Path, originales: Path | None = None, demo: bool = False) -> Path:
    """Escribe destino/index.html. Si se pasa `originales`, copia cada comprobante a destino/archivos/."""
    destino.mkdir(parents=True, exist_ok=True)
    docs = db.documentos_completos(con)
    if originales:
        (destino / "archivos").mkdir(exist_ok=True)
        for d in docs:
            origen = originales / d["archivo"]
            if not origen.exists():
                continue
            # Los .eml se descargan en vez de mostrarse: se publican como texto para verlos en el navegador.
            nombre = d["archivo"] + (".txt" if origen.suffix == ".eml" else "")
            shutil.copy(origen, destino / "archivos" / nombre)
            d["original"] = f"archivos/{nombre}"
    datos = json.dumps({"demo": demo, "documentos": docs}, ensure_ascii=False).replace("</", "<\\/")
    html = PLANTILLA.read_text(encoding="utf-8").replace("__DATOS__", datos)
    salida = destino / "index.html"
    salida.write_text(html, encoding="utf-8")
    return salida
