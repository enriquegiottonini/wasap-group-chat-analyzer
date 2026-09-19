# Diccionarios de datos

Un diccionario por cada conjunto de datos que genera el pipeline. Los archivos viven en
`data/<capa>/<chat>/`, donde `<chat>` es el slug del chat (`chats` en `params.yml`).
Ningún archivo de `data/` se versiona: aquí solo se documenta su contenido.

| Conjunto | Archivo | Grano | Lo genera | Diccionario |
|---|---|---|---|---|
| Mensajes (silver) | `data/processed/<chat>/messages.parquet` | un mensaje | `make process` | [diccionario_messages.md](diccionario_messages.md) |
| Tokens (silver) | `data/processed/<chat>/tokens.parquet` | un token de un mensaje | `make process` | [diccionario_tokens.md](diccionario_tokens.md) |
| Emojis (silver) | `data/processed/<chat>/emojis.parquet` | un emoji usado en un mensaje | `make process` | [diccionario_emojis.md](diccionario_emojis.md) |
| Mensajes anonimizados (interim) | `data/interim/<chat>/messages_anon.parquet` | un registro del chat | `make anonymize` | [diccionario_messages_anon.md](diccionario_messages_anon.md) |
| Miembros (interim) | `data/interim/<chat>/members.parquet` | un miembro del grupo | `make anonymize` | [diccionario_members.md](diccionario_members.md) |

Las tres tablas de silver se unen por `message_id`: el remitente, la fecha y el tipo de
un token o de un emoji se obtienen uniendo con `messages`, para que cada dato viva en una
sola tabla.

```sql
SELECT m.sender, count(*) AS palabras
FROM 'data/processed/baketon_city/tokens.parquet' AS t
JOIN 'data/processed/baketon_city/messages.parquet' AS m USING (message_id)
WHERE t.is_alpha AND NOT t.is_stop
GROUP BY m.sender
ORDER BY palabras DESC;
```

## De dónde salen

`data/raw/<chat>/` guarda la exportación original de WhatsApp (el zip, `_chat.txt` y
`FUENTE.txt` con su procedencia). `make anonymize` la parsea y escribe también
`data/interim/<chat>/bronze.parquet`: los mismos registros **con los nombres reales y el
texto sin tocar**, para análisis manual en la máquina donde están los datos. No tiene
diccionario aquí porque no es un conjunto publicable; sus columnas son las de
`messages_anon` con `sender` (nombre real) en vez de `sender_id`, y `record_no` en vez de
`message_id`.

## Anonimización

Los nombres nunca salen de `raw/` ni de `bronze.parquet`. En todo lo demás:

- Cada miembro es un alias: el nombre de un animal de México ("Ajolote", "Jaguar"), en el
  orden en que escribió por primera vez.
- Dentro del texto, los datos personales se sustituyen por marcas:

| Marca | Qué reemplaza |
|---|---|
| `@[Ajolote]` | una mención a un miembro |
| `[Ajolote]` | el nombre de un miembro escrito en el texto |
| `[nombre]` | un nombre que comparten varios miembros, o un apodo de `extra_names` |
| `[url:dominio]` | un enlace, del que solo se conserva el dominio |
| `[correo]` | una dirección de correo |
| `[numero]` | un número de 8 dígitos o más (teléfono, cuenta, tarjeta, folio) |
| `@Meta AI` | se conserva: es un bot, no una persona |

`make leak-check` revisa que ningún nombre real aparezca en estos conjuntos, en los
notebooks exportados ni en estas referencias.
