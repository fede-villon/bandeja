# Automatizar Bandeja

## Procesar todas las mañanas y mandar el resumen los lunes (cron, Linux)

`crontab -e` y agregar, cambiando la ruta:

```cron
# De lunes a sábado a las 8:00: procesar lo que llegó
0 8 * * 1-6  cd /home/usuario/bandeja && .venv/bin/python -m bandeja procesar --entrada entrada --mover procesados >> logs/bandeja.log 2>&1

# Lunes 9:00: resumen de la semana por mail, con el Excel adjunto
0 9 * * 1    cd /home/usuario/bandeja && .venv/bin/python -m bandeja reporte --dias 7 --excel salida/semana.xlsx --enviar >> logs/bandeja.log 2>&1
```

La clave de la API va en el entorno del cron. Por ejemplo, en la primera línea del crontab:
`ANTHROPIC_API_KEY=...`, o en un archivo con permisos `600` que se carga antes del comando.

En Windows, lo mismo se arma con el Programador de tareas.

## Envío por mail

`reporte --enviar` usa SMTP y toma la configuración de estas variables:

| Variable | Ejemplo |
|---|---|
| `BANDEJA_SMTP_HOST` | `smtp.gmail.com` |
| `BANDEJA_SMTP_PUERTO` | `587` (por defecto) |
| `BANDEJA_SMTP_USUARIO` | la casilla que envía |
| `BANDEJA_SMTP_CLAVE` | contraseña de aplicación (no la clave normal) |
| `BANDEJA_MAIL_PARA` | a quién le llega el resumen |

## Cómo llegan los archivos a `entrada/`

- **A mano:** se guardan los PDF y los mails (`.eml`) en la carpeta.
- **Regla del correo:** muchos clientes de correo pueden guardar los adjuntos de ciertos remitentes en una carpeta.
- **Carpeta sincronizada** (Drive, Dropbox, Syncthing): el dueño la llena desde el celular y Bandeja la procesa en la PC.

## Ante un error

- `✗ archivo: ...` significa que el archivo no se procesó y queda en `entrada/`. Se reintenta en la próxima corrida.
- `Límite de uso de la API alcanzado`: se reintenta solo en la próxima corrida.
- `Sin conexión con la API`: revisar internet y proxy.
- Para ver qué leyó la IA, abrir el documento en el panel → "Datos extraídos (JSON)".
