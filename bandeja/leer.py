"""Convierte cada archivo de entrada en texto para el modelo.

- PDF: se extrae el texto con pypdf. Los PDF escaneados (imágenes, sin texto)
  no se pueden leer así: se informa para revisarlos a mano.
- Email (.eml): encabezado, cuerpo y el texto de cada PDF adjunto.
- Texto (.txt): tal cual.
"""
import email
import hashlib
import io
from email import policy
from pathlib import Path

from pypdf import PdfReader

EXTENSIONES = {".pdf", ".eml", ".txt"}
MINIMO_TEXTO = 40   # menos que esto en un PDF = probablemente escaneado


class SinTexto(Exception):
    """El archivo no tiene texto legible (por ejemplo, un PDF escaneado)."""


def hash_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def texto_pdf(datos: bytes, nombre: str) -> str:
    lector = PdfReader(io.BytesIO(datos))
    texto = "\n".join((p.extract_text() or "") for p in lector.pages).strip()
    if len(texto) < MINIMO_TEXTO:
        raise SinTexto(f"{nombre} no tiene texto (¿está escaneado?): revisalo a mano.")
    return texto


def texto_de(ruta: Path) -> str:
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        return f"[Documento PDF: {ruta.name}]\n" + texto_pdf(ruta.read_bytes(), ruta.name)
    if ext == ".txt":
        return ruta.read_text(encoding="utf-8")
    if ext == ".eml":
        msg = email.message_from_bytes(ruta.read_bytes(), policy=policy.default)
        cuerpo = msg.get_body(preferencelist=("plain", "html"))
        partes = [f"[Email]\nDe: {msg['From']}\nAsunto: {msg['Subject']}\nFecha: {msg['Date']}\n\n"
                  + (cuerpo.get_content() if cuerpo else "")]
        for adj in msg.iter_attachments():
            if adj.get_content_type() == "application/pdf":
                nombre = adj.get_filename() or "adjunto.pdf"
                partes.append(f"[PDF adjunto: {nombre}]\n" + texto_pdf(adj.get_content(), nombre))
        return "\n\n".join(partes)
    raise ValueError(f"Formato no soportado: {ruta.name}")
