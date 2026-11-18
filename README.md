# Bandeja — comprobantes de proveedores leídos con IA y verificados solos

Un almacén recibe por semana decenas de facturas, remitos y presupuestos, en PDF o en el cuerpo de un email. Alguien tiene que pasarlos a una planilla y, con suerte, revisar que las cuentas den.

**Bandeja automatiza ese trabajo:** lee cada comprobante con IA, lo carga en una base de datos, controla los números con reglas fijas y avisa solo lo que hay que mirar.

```
entrada/ (PDF, .eml)  →  modelo de IA gratuito (local)  →  controles automáticos  →  SQLite
                                                                                   ├─ panel de revisión (HTML)
                                                                                   ├─ Excel
                                                                                   └─ resumen semanal por mail
```

**[Ver la demo del panel →](docs/demo/index.html)**: 8 comprobantes de ejemplo ya procesados. Para verla, descargá la carpeta `docs/demo` y abrí `index.html`.

## Qué detecta

| Control | Ejemplo en la demo |
|---|---|
| **Total que no cierra** | La factura dice $123.726, pero las líneas más IVA suman $121.726. |
| **Línea mal calculada** | 24 × $900 da $21.600, pero la línea dice $22.600. |
| **Comprobante duplicado** | Reenviaron por mail una factura que ya se había cargado. |
| **Aumento de precio** | La yerba pasó de $3.900 a $4.500 (+15 %) respecto de la compra anterior. |
| **Proveedor fuera del padrón** | Llegó una factura de un proveedor nuevo. |
| **Datos faltantes** | Factura sin CUIT. |
| **Observaciones de la lectura** | "Precios válidos hasta el 30/11". |

La IA solo transcribe lo que está impreso, errores incluidos. Los controles son código común: cada alerta tiene una explicación concreta y se puede reproducir.

## Probarlo (sin clave de API)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m bandeja demo        # procesa los ejemplos y arma docs/demo/ (panel, Excel y resumen)
python -m pytest -q           # 32 tests
```

El modo demo usa extracciones guardadas en `ejemplos/extracciones/`, con exactamente lo que dice cada comprobante. Así se prueba todo el sistema sin instalar ningún modelo.

## Usarlo con documentos reales

Bandeja usa un **modelo de IA gratuito que corre en la propia PC** con [Ollama](https://ollama.com): no tiene costo por uso, no tiene límites y las facturas no salen de la computadora del negocio.

```bash
ollama pull qwen2.5:7b-instruct                                # una sola vez (~5 GB)
python -m bandeja proveedores padron.csv                       # proveedores habituales (nombre;cuit)
python -m bandeja procesar --entrada entrada --mover procesados
python -m bandeja pendientes                                   # qué falta revisar
python -m bandeja aprobar 12                                   # o: rechazar 12
python -m bandeja reporte --dias 7 --excel semana.xlsx
python -m bandeja panel --salida panel --originales procesados
```

- El texto de los PDF se saca con `pypdf`; de los emails se toman el cuerpo y los PDF adjuntos. Los **PDF escaneados** (imágenes sin texto) se detectan y se dejan para revisar a mano.
- Al modelo se le pide **JSON** con un ejemplo del formato, y la respuesta se **valida** con el esquema de [`bandeja/modelos.py`](bandeja/modelos.py) (Pydantic). Si no es válida, se reintenta una vez diciéndole al modelo qué estuvo mal.
- **Control contra el original**: cada importe que devuelve el modelo se busca en el texto del documento. Si el modelo inventa o "corrige" un número, el comprobante queda marcado para revisar.
- Si el modelo no responde o falla, el archivo **queda en la entrada** para reintentar y se informa el motivo. Nunca se carga a medias.
- Se conecta por la interfaz compatible con OpenAI, así que el modelo se cambia con variables de entorno, sin tocar código:

| Variable | Por defecto | Para qué |
|---|---|---|
| `BANDEJA_MODELO` | `qwen2.5:7b-instruct` | Cualquier modelo de Ollama, por ejemplo `deepseek-r1:8b`. |
| `BANDEJA_URL` | `http://localhost:11434/v1` | Otro servidor compatible con OpenAI. |
| `BANDEJA_API_KEY` | `ollama` | Solo si el servidor pide clave. |
- Cada archivo se identifica por su hash: procesar dos veces la misma carpeta no duplica nada.

### Automatizarlo

En [docs/automatizar.md](docs/automatizar.md) están los ejemplos de `cron` y de envío por mail: procesar todas las mañanas y mandar el resumen los lunes.

## Cómo está hecho

| Archivo | Qué hace |
|---|---|
| `bandeja/leer.py` | Saca el texto de los PDF y de los emails. |
| `bandeja/extraer.py` | Extractor con el modelo de IA y extractor de demo (misma interfaz). |
| `bandeja/validar.py` | Las reglas de control. |
| `bandeja/db.py` | SQLite: documentos, líneas, alertas, padrón e historial de precios. |
| `bandeja/procesar.py` | Recorre la carpeta y une todo. |
| `bandeja/reporte.py` | Resumen, envío por mail y exportación a Excel. |
| `bandeja/panel.py` | Genera el panel como una página estática con los datos adentro. |
| `ejemplos/generar_ejemplos.py` | Crea los comprobantes ficticios (PDF y emails) con errores a propósito. |

**Decisiones:**
- **Separar "leer" de "controlar".** La IA es buena leyendo documentos desprolijos, pero las cuentas las hace el código. Así un error de lectura no tapa un error del proveedor.
- **Pedirle a la IA los números tal como están impresos**, aunque estén mal. Si los "corrigiera", nunca detectaríamos un total mal sumado.
- **El historial de precios sale de las facturas aprobadas o pendientes**, no de las rechazadas, para que un error no contamine las comparaciones.
- **Panel estático**: se abre con doble clic y se puede mandar por mail. No necesita servidor.

## Costos y precisión

**Costo: cero.** El modelo corre en la PC del local. Solo necesita unos 8 GB de RAM; en una PC común sin placa de video tarda alrededor de un minuto por comprobante, y como corre de noche o en segundo plano, no molesta.

**Precisión medida** con `python ejemplos/evaluar.py`, que compara lo que lee el modelo con los datos reales de los 8 comprobantes de ejemplo:

| Versión | Campos del comprobante | Líneas de detalle |
|---|---|---|
| Primera versión de las instrucciones | 50/56 (89 %) | 22/24 |
| Instrucciones ajustadas | 51/56 (91 %) | 23/24 |
| + limpieza del proveedor y control contra el original | **56/56 (100 %)** | **23/24** |

Modelo `qwen2.5:7b-instruct` en una PC sin placa de video: entre 70 y 105 segundos por comprobante.

Cómo se llegó ahí:
- La letra de la factura ("A") quedaba pegada al nombre del proveedor al sacar el texto del PDF. Se resolvió con una regla fija, no pidiéndoselo al modelo.
- En una versión, el modelo "corregía" una línea mal calculada del proveedor. Por eso se agregó un **control contra el original**: cada importe que devuelve el modelo se busca en el renglón del producto, y si no aparece, el comprobante queda marcado para revisar.
- El único error que queda (en una línea leyó cantidad 1 en lugar de 12) también lo detectan los controles, porque 1 × $1.800 no da el subtotal impreso.

Lo que el modelo lee mal no se paga solo: los controles automáticos y la aprobación humana son la red de seguridad.

## Próximos pasos

- Leer los mails directo de la casilla (IMAP) en vez de una carpeta.
- OCR (por ejemplo con Tesseract) para leer los PDF escaneados.
- Conectar con [Despensa](https://github.com/fede-villon/despensa) para que una factura aprobada sume stock y actualice costos.
- Panel con servidor para aprobar desde el celular.

## Sobre el desarrollo

Definí el problema, los controles y el flujo a partir de cómo se trabaja en un comercio chico. Usé asistentes de IA para escribir el código más rápido, y revisé, probé y documenté el resultado. Todos los datos de ejemplo son ficticios.
