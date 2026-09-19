# Diccionario: `members.parquet` (interim)

- **Archivo:** `data/interim/<chat>/members.parquet`
- **Grano:** un miembro que escribió al menos un mensaje. `sender_id` es la llave.
- **Lo genera:** `make anonymize` (`wasap_group_analyzer/jobs/anonymize_job.py`).
- **Para qué sirve:** traduce el id anónimo de `messages_anon.parquet` al alias que se usa
  en silver y en los notebooks.

## Columnas

| Columna | Tipo | Descripción | Ejemplo | Nulos |
|---|---|---|---|---|
| `sender_id` | VARCHAR | Id anónimo del miembro (ver `messages_anon.parquet`). | `5a34656d26` | nunca |
| `alias` | VARCHAR | Nombre de un animal de México, único dentro del chat. | `Ajolote` | nunca |
| `first_message` | TIMESTAMP | Fecha y hora de su primer mensaje en la exportación. | `2024-09-28 14:31:21` | nunca |

## Notas

- Los alias se asignan en el orden de `first_message`: quien escribió primero es el
  primer animal de la lista (`wasap_group_analyzer/aliases.py`). El orden no depende del
  hash, así que una exportación más nueva solo agrega animales al final.
- El job salta cualquier animal que comparta una palabra con el nombre real de algún
  miembro, para que el alias no dé ninguna pista sobre quién es. Esa comprobación solo
  puede hacerse aquí, donde se conocen los nombres reales.
- La exportación empieza a media conversación, así que `first_message` es el primer
  mensaje **dentro de la exportación**, no necesariamente el primero que esa persona
  escribió en el grupo.
- El grupo mismo firma algunos avisos; no es una persona y no aparece en esta tabla.
- Quien solo aparece mencionado y nunca escribió no tiene alias: en silver esas menciones
  quedan como `@[persona]`.
