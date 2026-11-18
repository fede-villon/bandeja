# Bandeja — comprobantes de proveedores leídos con IA y verificados solos

Un almacén recibe por semana decenas de facturas, remitos y presupuestos, en PDF o en el cuerpo de un email. Alguien tiene que pasarlos a una planilla y, con suerte, revisar que las cuentas den.

**Bandeja automatiza ese trabajo:** lee cada comprobante con IA, lo carga en una base de datos, controla los números con reglas fijas y avisa solo lo que hay que mirar.

```
entrada/ (PDF, .eml)  →  Claude extrae los datos  →  controles automáticos  →  SQLite
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
python -m pytest -q           # 25 tests
```

El modo demo usa extracciones guardadas en `ejemplos/extracciones/`, con exactamente lo que dice cada comprobante. Así se prueba todo el sistema sin gastar ni tener clave.

## Usarlo con documentos reales

```bash
export ANTHROPIC_API_KEY=...                                   # o `ant auth login`
python -m bandeja proveedores padron.csv                       # proveedores habituales (nombre;cuit)
python -m bandeja procesar --entrada entrada --mover procesados
python -m bandeja pendientes                                   # qué falta revisar
python -m bandeja aprobar 12                                   # o: rechazar 12
python -m bandeja reporte --dias 7 --excel semana.xlsx
python -m bandeja panel --salida panel --originales procesados
```

- Usa **Claude** (`claude-opus-5-5`, se cambia con `BANDEJA_MODELO`) con **salida estructurada**: la respuesta siempre respeta el esquema de [`bandeja/modelos.py`](bandeja/modelos.py), así no hay que interpretar texto libre.
- Los PDF se mandan tal cual (Claude también lee escaneos). De los emails se toman el cuerpo y los PDF adjuntos.
- Si el modelo no procesa un documento o la API falla, el archivo **queda en la entrada** para reintentar y se informa el motivo. Nunca se carga a medias.
- Tiene activado el respaldo automático de la API: si el modelo rechaza un pedido, la misma llamada lo reintenta con otro modelo.
- Cada archivo se identifica por su hash: procesar dos veces la misma carpeta no duplica nada.

### Automatizarlo

En [docs/automatizar.md](docs/automatizar.md) están los ejemplos de `cron` y de envío por mail: procesar todas las mañanas y mandar el resumen los lunes.

## Cómo está hecho

| Archivo | Qué hace |
|---|---|
| `bandeja/leer.py` | Convierte PDF y emails en bloques para la API. |
| `bandeja/extraer.py` | Extractor con Claude y extractor de demo (misma interfaz). |
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

## Costos

Cada comprobante es una llamada a la API. Con `claude-opus-5-5`, una factura de 1 o 2 páginas cuesta del orden de unos pocos centavos de dólar. Es un valor estimado: el costo real depende del largo del documento.

## Próximos pasos

- Leer los mails directo de la casilla (IMAP) en vez de una carpeta.
- Conectar con [Despensa](https://github.com/fede-villon/despensa) para que una factura aprobada sume stock y actualice costos.
- Panel con servidor para aprobar desde el celular.

## Sobre el desarrollo

Definí el problema, los controles y el flujo a partir de cómo se trabaja en un comercio chico. Usé asistentes de IA para escribir el código más rápido, y revisé, probé y documenté el resultado. Todos los datos de ejemplo son ficticios.
