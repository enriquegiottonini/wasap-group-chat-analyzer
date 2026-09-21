# Referencias

Un diccionario de datos por cada conjunto tidy de `data/processed/<chat>/`, en JSON:

- [`diccionario_messages.json`](diccionario_messages.json): una fila por mensaje.
- [`diccionario_tokens.json`](diccionario_tokens.json): una fila por token de un mensaje.
- [`diccionario_emojis.json`](diccionario_emojis.json): una fila por emoji usado.

Cada uno dice qué representa una fila del conjunto, cuántas filas tiene y, por columna,
su tipo, porcentaje de nulos, valores distintos, rango y una descripción.

Los genera `make dictionary`: el perfil lo calcula DuckDB (`SUMMARIZE`) y las
descripciones viven en `wasap_group_analyzer/metadata/dictionary.py`, que falla si una
columna no está descrita. En las columnas de texto el rango es `null` a propósito: su
mínimo y su máximo serían mensajes reales.

Los tres conjuntos se unen por `message_id`: el remitente, la fecha y el tipo de un token
o de un emoji salen de `messages`.

`data/raw/` (la exportación original, con su `FUENTE.txt`) y `data/interim/` (los mensajes
parseados y anonimizados, más el alias de cada miembro) son pasos intermedios que se
regeneran con `make data`; el notebook `01_eda_bronze` explica qué hay en ellos y qué se
conserva.
