# Diccionario: `messages_anon.parquet` (interim)

- **Archivo:** `data/interim/<chat>/messages_anon.parquet`
- **Grano:** un registro del chat exportado (un mensaje o un aviso). `message_id` es la
  llave.
- **Lo genera:** `make anonymize` (`wasap_group_analyzer/jobs/anonymize_job.py`) a partir
  de `data/raw/<chat>/_chat.txt`.
- **Para qué sirve:** es el paso intermedio entre el texto crudo y silver: ya no tiene
  nombres reales, pero todavía conserva el texto tal como lo mandó WhatsApp (marcadores
  de adjunto, sufijo de edición, marcas invisibles). Es transitorio: se puede borrar y
  regenerar con `make anonymize`.

## Columnas

| Columna | Tipo | Descripción | Ejemplo | Nulos |
|---|---|---|---|---|
| `message_id` | BIGINT | Posición del registro en el archivo exportado, desde 1. | `1189` | nunca |
| `timestamp` | TIMESTAMP | Fecha y hora local del celular que exportó, sin zona horaria. | `2025-02-01 09:05:00` | nunca |
| `sender_id` | VARCHAR | Id anónimo del remitente: hash `blake2b` de su nombre con la sal secreta de `.env` (10 caracteres hex). Une con `members.parquet`. | `5a34656d26` | en los avisos que firma el grupo |
| `kind` | VARCHAR | Tipo de registro, con todos los adjuntos juntos: `text`, `attachment`, `poll`, `location`, `view_once`, `deleted`, `unavailable`, `system_notice`, `group_notice`, `empty`. En silver, `attachment` se separa por tipo de adjunto. | `attachment` | nunca |
| `body` | VARCHAR | Texto del mensaje ya enmascarado, tal como venía: con el marcador del adjunto, el sufijo de edición y las marcas invisibles de WhatsApp. | `foto de [5a34656d26] ‹U+200E›image omitted` | en los tipos sin contenido (avisos, ubicaciones, eliminados, una sola vista, no disponibles, vacíos) |

## Notas

- En `body`, los ids de los miembros aparecen como `@[5a34656d26]` (mención) o
  `[5a34656d26]` (nombre escrito en el texto); en silver se cambian por el alias del
  miembro. Las demás marcas (`[nombre]`, `[url:dominio]`, `[correo]`, `[numero]`) están
  en [README.md](README.md).
- El texto de los avisos se descarta por completo, porque trae nombres reales ("X added
  Y", "deleted by admin X"); de las ubicaciones se descartan las coordenadas. Del
  registro solo queda su `kind`.
- Los ids no se pueden revertir sin la sal (`ANON_SALT` en `.env`, fuera de git), aunque
  se conozca la lista de miembros.
