# Diccionario: `messages.parquet` (silver)

- **Archivo:** `data/processed/<chat>/messages.parquet`
- **Grano:** un mensaje del chat, incluidos adjuntos y avisos. `message_id` es la llave.
- **Lo genera:** `make process` (`wasap_group_analyzer/jobs/process_job.py`), a partir de
  `data/interim/<chat>/messages_anon.parquet` y `members.parquet`.
- **Orden:** por `message_id`, que es el orden del archivo exportado.

## Columnas

| Columna | Tipo | Descripción | Ejemplo | Nulos |
|---|---|---|---|---|
| `message_id` | BIGINT | Posición del mensaje en el archivo exportado, desde 1. Llave primaria y llave de unión con `tokens` y `emojis`. | `1189` | nunca |
| `timestamp` | TIMESTAMP | Fecha y hora local del celular que exportó, sin zona horaria (ver `FUENTE.txt`). | `2025-02-01 09:05:00` | nunca |
| `sender` | VARCHAR | Alias del remitente: el nombre de un animal. | `Ajolote` | en los avisos del grupo (`group_notice`) |
| `message_type` | VARCHAR | Qué es el mensaje. Valores: `text`, `sticker`, `image`, `audio`, `video`, `gif`, `video_note`, `document`, `contact`, `poll`, `location`, `view_once`, `deleted`, `unavailable`, `system_notice`, `group_notice`, `empty`. | `sticker` | nunca |
| `content` | VARCHAR | Texto que escribió la persona, ya anonimizado y sin marcas invisibles: el mensaje, el pie de foto de un adjunto o la encuesta completa. | `nos vemos mañana @[Jaguar] 😂` | cuando el mensaje no trae texto (sticker, audio, aviso, ubicación...) |
| `is_edited` | BOOLEAN | Si WhatsApp marcó el mensaje como editado. | `false` | nunca |
| `n_words` | BIGINT | Palabras del contenido: tokens alfabéticos según spaCy (ver `tokens.parquet`). `0` si no hay texto. | `4` | nunca |
| `n_emojis` | BIGINT | Emojis del contenido; coincide con el número de filas de este mensaje en `emojis.parquet`. | `1` | nunca |
| `n_mentions` | BIGINT | Menciones a miembros (`@[Alias]`) en el contenido. | `1` | nunca |
| `has_url` | BOOLEAN | Si el contenido trae al menos un enlace (`[url:dominio]`). | `false` | nunca |

## Notas

- **Mensajes de texto**: solo `message_type = 'text'`. Los pies de foto (`image`, `video`,
  `gif`, `document`) y las encuestas también traen texto y sus palabras cuentan en
  `tokens`, pero no son mensajes de texto.
- Los mensajes **no** están siempre en orden cronológico estricto: hay unos pocos
  registros que llegaron tarde al celular. Para análisis de tiempo, ordenar por
  `timestamp` y no por `message_id`.
- `view_once`, `deleted` y `unavailable` son mensajes cuyo contenido WhatsApp no exporta;
  se conservan como fila para no perder que existieron.
- Las marcas de anonimización del contenido (`@[Alias]`, `[nombre]`, `[url:dominio]`,
  `[correo]`, `[numero]`) están documentadas en [README.md](README.md).
