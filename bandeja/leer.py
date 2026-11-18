"""Convierte cada archivo de entrada en bloques de contenido para la API de Claude.

- PDF: se manda tal cual (Claude lee PDFs nativamente, incluidos escaneados).
- Email (.eml): el cuerpo como texto y cada PDF adjunto como documento.
- Texto (.txt): como texto.
"""
import base64
import email
import hashlib
from email import policy
from pathlib import Path

EXTENSIONES = {".pdf", ".eml", ".txt"}


def hash_archivo(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _pdf(datos: bytes, titulo: str) -> dict:
    return {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(datos).decode()},
        "title": titulo,
    }


def bloques_de(ruta: Path) -> list[dict]:
    ext = ruta.suffix.lower()
    if ext == ".pdf":
        return [_pdf(ruta.read_bytes(), ruta.name)]
    if ext == ".txt":
        return [{"type": "text", "text": ruta.read_text(encoding="utf-8")}]
    if ext == ".eml":
        msg = email.message_from_bytes(ruta.read_bytes(), policy=policy.default)
        cuerpo = msg.get_body(preferencelist=("plain", "html"))
        texto = cuerpo.get_content() if cuerpo else ""
        encabezado = f"De: {msg['From']}\nAsunto: {msg['Subject']}\nFecha: {msg['Date']}\n\n"
        bloques = []
        for adj in msg.iter_attachments():
            if adj.get_content_type() == "application/pdf":
                bloques.append(_pdf(adj.get_content(), adj.get_filename() or "adjunto.pdf"))
        bloques.append({"type": "text", "text": "Email recibido:\n" + encabezado + texto})
        return bloques
    raise ValueError(f"Formato no soportado: {ruta.name}")
