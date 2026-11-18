"""Mide qué tan bien lee el modelo los comprobantes de ejemplo.

Compara la extracción del modelo con la referencia de ejemplos/extracciones/.

Uso:  python ejemplos/evaluar.py                      (modelo por defecto)
      BANDEJA_MODELO=qwen2.5:7b-instruct python ejemplos/evaluar.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bandeja.extraer import ErrorExtraccion, ExtractorLLM  # noqa: E402
from bandeja.validar import normalizar  # noqa: E402

AQUI = Path(__file__).parent
CAMPOS = ["tipo", "proveedor", "cuit", "numero", "fecha", "total", "impuestos"]


def igual(campo, a, b):
    if campo in ("total", "impuestos"):
        return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1)
    if campo == "proveedor":
        return normalizar(a or "") == normalizar(b or "")
    return a == b


def main():
    ex = ExtractorLLM()
    print(f"Modelo: {ex.modelo}\n")
    aciertos = total = lineas_ok = lineas = marcados = 0
    for ruta in sorted((AQUI / "entrada").iterdir()):
        ref = json.loads((AQUI / "extracciones" / (ruta.stem + ".json")).read_text(encoding="utf-8"))
        t0 = time.time()
        try:
            doc = ex.extraer(ruta).model_dump()
        except ErrorExtraccion as e:
            print(f"✗ {ruta.name}: {e}")
            total += len(CAMPOS); lineas += len(ref["items"])
            continue
        fallas = [c for c in CAMPOS if not igual(c, doc[c], ref[c])]
        aciertos += len(CAMPOS) - len(fallas); total += len(CAMPOS)
        ok = sum(1 for a, b in zip(doc["items"], ref["items"])
                 if abs(a["cantidad"] - b["cantidad"]) < .01 and abs(a["subtotal"] - b["subtotal"]) < 1
                 and abs(a["precio_unitario"] - b["precio_unitario"]) < 1)
        lineas_ok += ok; lineas += len(ref["items"])
        estado = "✓" if not fallas and ok == len(ref["items"]) else "~"
        if doc["observaciones"] and "no figuran" in doc["observaciones"]:
            marcados += 1
            estado += " (marcado para revisar)"
        detalle = ", ".join(f"{c}: {doc[c]!r} (era {ref[c]!r})" for c in fallas)
        print(f"{estado} {ruta.name} [{time.time() - t0:.0f} s] líneas {ok}/{len(ref['items'])}"
              + (f" · {detalle}" if detalle else ""))
    print(f"\nCampos correctos: {aciertos}/{total} ({aciertos / total:.0%}) · líneas correctas: {lineas_ok}/{lineas}"
          f" · comprobantes marcados por el control contra el original: {marcados}")


if __name__ == "__main__":
    main()
