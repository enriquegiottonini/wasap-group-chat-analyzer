"""Parseo del chat exportado por WhatsApp (iOS) a una tabla de registros, con DuckDB.

Es la lógica que explora `notebooks/01_eda_bronze.py`, en la versión que corre el job.
El archivo separa los mensajes con CRLF y usa LF solo dentro de un mensaje, así que cada
registro (texto entre dos CRLF) es un mensaje completo con su encabezado:

    [dd/mm/aa, h:mm:ss a.m.] Remitente: cuerpo
"""

from pathlib import Path

import duckdb

# Caracteres invisibles que mete WhatsApp (ver la sección 4 del EDA bronze).
LRM = "\u200e"  # left-to-right mark: antes de adjuntos omitidos y avisos
NNBSP = "\u202f"  # narrow no-break space: entre la hora y a.m./p.m.
FSI = "\u2068"  # first strong isolate: abre el nombre en una mención @
PDI = "\u2069"  # pop directional isolate: lo cierra

# Tipos de registro. `message_type` en silver parte de estos mismos códigos.
KINDS = (
    "text",
    "attachment",
    "poll",
    "location",
    "view_once",
    "deleted",
    "unavailable",
    "system_notice",
    "group_notice",
    "empty",
)

# Las expresiones regulares evitan `\` y llaves para ser idénticas a las del notebook,
# donde marimo guarda el SQL como f-string: [0-9] por \d, [.] por \., [[] y []] por
# corchetes literales.
BRONZE_SQL = f"""
WITH records AS (
    SELECT i AS record_no, records[i] AS record
    FROM (
        SELECT string_split(content, chr(13) || chr(10)) AS records
        FROM read_text($chat_file)
    ) AS t, range(1, len(records) + 1) AS r(i)
),
parts AS (
    SELECT
        record_no,
        regexp_extract(record, '^{LRM}?[[]([^]]*)[]] ', 1) AS header,
        regexp_extract(record, '^[^]]*[]] ([^:]+?):( |$)', 1) AS sender,
        regexp_replace(record, '^[^]]*[]] [^:]+?:( |$)', '') AS body
    FROM records
    WHERE record <> ''
),
parsed AS (
    SELECT
        *,
        try_strptime(
            replace(replace(replace(header, '{NNBSP}', ' '), 'a.m.', 'AM'), 'p.m.', 'PM'),
            '%d/%m/%y, %I:%M:%S %p'
        ) AS ts
    FROM parts
)
SELECT
    record_no,
    ts AS timestamp,
    sender,
    body,
    CASE
        WHEN sender = $group THEN 'group_notice'
        WHEN body = '' THEN 'empty'
        WHEN regexp_matches(body, '{LRM}[A-Za-z ]+ omitted') THEN 'attachment'
        WHEN regexp_matches(body, '^{LRM}?POLL:') THEN 'poll'
        WHEN starts_with(body, '{LRM}Location: ') THEN 'location'
        WHEN starts_with(body, '{LRM}You received a view once') THEN 'view_once'
        WHEN regexp_matches(body, '^{LRM}(This message was deleted|You deleted this message)')
            THEN 'deleted'
        WHEN regexp_matches(body, '^{LRM}(Waiting for this message|This message can.t be displayed)')
            THEN 'unavailable'
        WHEN starts_with(body, '{LRM}') THEN 'system_notice'
        ELSE 'text'
    END AS kind
FROM parsed
ORDER BY record_no
"""


def build_bronze(
    con: duckdb.DuckDBPyConnection, chat_file: Path, group: str, table: str = "bronze"
) -> int:
    """Crea `table` en `con` con una fila por registro del chat y devuelve cuántas son.

    Columnas: record_no, timestamp (hora local, sin zona), sender (nombre real), body
    (sin tocar) y kind. Falla si algún registro no tiene encabezado o fecha legible: eso
    significa que el formato de exportación no es el esperado (p. ej. Android).
    """
    con.execute(
        f'CREATE OR REPLACE TABLE "{table}" AS {BRONZE_SQL}',
        {"chat_file": str(chat_file), "group": group},
    )
    total, unparsed = con.execute(
        f"SELECT count(*), count(*) FILTER (timestamp IS NULL OR sender = '') FROM \"{table}\""
    ).fetchone()
    if unparsed:
        raise ValueError(
            f"{unparsed} of {total} records in {chat_file} have no parseable header; "
            "is this an iOS export?"
        )
    return total
