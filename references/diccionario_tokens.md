# Diccionario: `tokens.parquet` (silver)

- **Archivo:** `data/processed/<chat>/tokens.parquet`
- **Grano:** un token (palabra, número, signo o emoji) dentro de un mensaje. La llave es
  `message_id` + `token_idx`.
- **Lo genera:** `make process` con spaCy (`es_core_news_sm`, sin parser ni NER), sobre el
  `content` de `messages.parquet`.
- **Cobertura:** solo los mensajes con contenido (texto, pies de foto y encuestas). Antes
  de tokenizar se quitan las marcas de anonimización (`@[Alias]`, `[url:dominio]`...) y
  las etiquetas de las encuestas (`POLL:`, `OPTION:`, `(3 votes)`), para que no cuenten
  como palabras.

## Columnas

| Columna | Tipo | Descripción | Ejemplo | Nulos |
|---|---|---|---|---|
| `message_id` | BIGINT | Mensaje al que pertenece el token; une con `messages.parquet`. | `1189` | nunca |
| `token_idx` | BIGINT | Posición del token dentro del mensaje, desde 0. | `2` | nunca |
| `token` | VARCHAR | El token tal como se escribió, en minúsculas. | `tacos` | nunca |
| `lemma` | VARCHAR | Lema en minúsculas (la forma de diccionario). En adjetivos, las formas cortas se unifican con la larga: `buen` queda como `bueno`. | `taco` | nunca |
| `pos` | VARCHAR | Categoría gramatical (etiquetas UPOS de spaCy): `NOUN`, `VERB`, `ADJ`, `ADV`, `PROPN`, `PRON`, `DET`, `ADP`, `PUNCT`, `NUM`... | `NOUN` | nunca |
| `is_alpha` | BOOLEAN | Si el token es una **palabra**: solo letras, con o sin acento. Números, signos, emojis y emoticonos son `false`. | `true` | nunca |
| `is_stop` | BOOLEAN | Si es palabra vacía: la lista de spaCy en español, las muletillas y abreviaturas del chat (`text.CHAT_STOP_WORDS`), cualquier palabra de una sola letra o una risa. | `false` | nunca |
| `is_laugh` | BOOLEAN | Si es una risa: `jaja`, `jejeje`, `jsjsjs`, `xd`, `lol` y variantes. | `false` | nunca |

## Notas

- Para contar palabras: `WHERE is_alpha`. Para palabras con contenido:
  `WHERE is_alpha AND NOT is_stop`. La suma de `is_alpha` por mensaje es `n_words` en
  `messages.parquet`.
- **Para adjetivos (`pos = 'ADJ'`) no conviene filtrar `is_stop`**: la lista de palabras
  vacías de spaCy incluye justo los adjetivos más comunes (*bueno*, *mejor*, *nuevo*,
  *primero*, *grande*). Basta con excluir risas y letras sueltas.
- `es_core_news_sm` se entrenó con noticias, no con chats: comete errores de etiquetado
  con la jerga, los mensajes sin puntuación y las palabras escritas de forma creativa
  (toma como adjetivo algún sustantivo o verbo, y no siempre lematiza el femenino). Es
  una limitación conocida del análisis, no un error de los datos.
