# Diccionario: `emojis.parquet` (silver)

- **Archivo:** `data/processed/<chat>/emojis.parquet`
- **Grano:** un emoji usado en un mensaje. La llave es `message_id` + `emoji_idx`.
- **Lo genera:** `make process` con la librería `emoji`, sobre el `content` de
  `messages.parquet`.

## Columnas

| Columna | Tipo | Descripción | Ejemplo | Nulos |
|---|---|---|---|---|
| `message_id` | BIGINT | Mensaje en el que aparece el emoji; une con `messages.parquet`. | `1189` | nunca |
| `emoji_idx` | BIGINT | Posición del emoji dentro del mensaje, desde 0. | `0` | nunca |
| `emoji` | VARCHAR | El emoji completo, tal como se escribió. | `😂` | nunca |
| `emoji_name` | VARCHAR | Su nombre en español, según la librería `emoji`. | `cara llorando de risa` | nunca |

## Notas

- Una secuencia cuenta como **un solo** emoji: los que llevan tono de piel (👍🏽) y los que
  unen varios símbolos con ZWJ (las familias, por ejemplo). El tono de piel forma parte
  tanto de `emoji` como de `emoji_name`, así que 👍 y 👍🏽 son emojis distintos.
- Los emoticonos de texto (`:)`, `xD`, `:(`) **no** son emojis: aparecen en
  `tokens.parquet` como tokens normales (`xd` además cuenta como risa).
- El número de filas de un mensaje coincide con su `n_emojis` en `messages.parquet`.
- Los emojis que van dentro de un sticker no existen aquí: al exportar sin archivos,
  WhatsApp no manda el sticker, solo su marcador.
