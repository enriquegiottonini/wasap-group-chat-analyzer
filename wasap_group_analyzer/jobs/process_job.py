"""Silver: convierte data/interim/<chat>/ en los conjuntos tidy de data/processed/<chat>/

- messages.parquet: una fila por mensaje, con el alias del remitente, su tipo, el texto
  legible y sus conteos.
- tokens.parquet: una fila por token del texto (spaCy), con lema, categoría gramatical y
  si es palabra, vacía o risa.
- emojis.parquet: una fila por emoji usado.

Las reglas (tipo de mensaje, qué es contenido, qué es palabra) están en
`wasap_group_analyzer/text.py` y se justifican en `notebooks/02_eda_silver.py`.

    uv run python -m wasap_group_analyzer.jobs.process_job [--chat SLUG]
"""

import argparse
from collections import Counter
from pathlib import Path

import duckdb
from loguru import logger
import polars as pl

from wasap_group_analyzer.config import active_chat, load_logging, load_params
from wasap_group_analyzer.constants import INTERIM_DIR, PROCESSED_DIR
from wasap_group_analyzer.jobs.anonymize_job import ANON_FILENAME, MEMBERS_FILENAME
from wasap_group_analyzer.logging import log_execution
from wasap_group_analyzer.text import (
    clean_content,
    emoji_name,
    extract_emojis,
    is_edited,
    load_nlp,
    message_type,
    text_for_words,
    tokenize,
)

MESSAGES_FILENAME = "messages.parquet"
TOKENS_FILENAME = "tokens.parquet"
EMOJIS_FILENAME = "emojis.parquet"

MESSAGE_COLUMNS = (
    "message_id",
    "timestamp",
    "sender",
    "message_type",
    "content",
    "is_edited",
    "n_words",
    "n_emojis",
    "n_mentions",
    "has_url",
)
TOKEN_COLUMNS = (
    "message_id",
    "token_idx",
    "token",
    "lemma",
    "pos",
    "is_alpha",
    "is_stop",
    "is_laugh",
)
EMOJI_COLUMNS = ("message_id", "emoji_idx", "emoji", "emoji_name")

# Tipos explícitos: si un chat no tiene emojis, el parquet vacío igual queda bien tipado.
TOKEN_SCHEMA = {
    "message_id": pl.Int64,
    "token_idx": pl.Int64,
    "token": pl.String,
    "lemma": pl.String,
    "pos": pl.String,
    "is_alpha": pl.Boolean,
    "is_stop": pl.Boolean,
    "is_laugh": pl.Boolean,
}
EMOJI_SCHEMA = {
    "message_id": pl.Int64,
    "emoji_idx": pl.Int64,
    "emoji": pl.String,
    "emoji_name": pl.String,
}


def read_interim(interim_dir: Path) -> tuple[list[tuple], dict[str, str]]:
    """Mensajes anonimizados (en orden) y el alias de cada miembro."""
    con = duckdb.connect()
    for name, filename in (("messages_anon", ANON_FILENAME), ("members", MEMBERS_FILENAME)):
        path = str(interim_dir / filename).replace("'", "''")
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")

    messages = con.execute(
        """
        SELECT m.message_id, m.timestamp, members.alias, m.kind, m.body
        FROM messages_anon AS m
        LEFT JOIN members USING (sender_id)
        ORDER BY m.message_id
        """
    ).fetchall()
    aliases = dict(con.execute("SELECT sender_id, alias FROM members").fetchall())
    return messages, aliases


def build_tables(
    messages: list[tuple], aliases: dict[str, str], model: str
) -> dict[str, pl.DataFrame]:
    """Las tres tablas de silver a partir de los mensajes anonimizados."""
    contents = [clean_content(kind, body, aliases) for _, _, _, kind, body in messages]

    emoji_rows = {column: [] for column in EMOJI_COLUMNS}
    for (message_id, *_), content in zip(messages, contents):
        for emoji_idx, symbol in enumerate(extract_emojis(content)):
            emoji_rows["message_id"].append(message_id)
            emoji_rows["emoji_idx"].append(emoji_idx)
            emoji_rows["emoji"].append(symbol)
            emoji_rows["emoji_name"].append(emoji_name(symbol))
    logger.info("Found {} emojis", len(emoji_rows["message_id"]))

    with_text = [
        (message_id, content)
        for (message_id, *_), content in zip(messages, contents)
        if content is not None
    ]
    nlp = load_nlp(model)
    token_rows = {column: [] for column in TOKEN_COLUMNS}
    words = dict.fromkeys((message_id for message_id, _ in with_text), 0)
    logger.info("Tagging {} messages with {}", len(with_text), model)
    for (message_id, _), tokens in zip(
        with_text, tokenize(nlp, (text_for_words(content) for _, content in with_text))
    ):
        for token in tokens:
            token_rows["message_id"].append(message_id)
            for column in TOKEN_COLUMNS[1:]:
                token_rows[column].append(token[column])
        words[message_id] = sum(token["is_alpha"] for token in tokens)
    logger.info("Found {} tokens", len(token_rows["message_id"]))

    n_emojis = Counter(emoji_rows["message_id"])

    return {
        MESSAGES_FILENAME: pl.DataFrame(
            {
                "message_id": [message_id for message_id, *_ in messages],
                "timestamp": [timestamp for _, timestamp, *_ in messages],
                "sender": [alias for _, _, alias, *_ in messages],
                "message_type": [message_type(kind, body) for *_, kind, body in messages],
                "content": contents,
                "is_edited": [is_edited(body) for *_, body in messages],
                "n_words": [words.get(message_id, 0) for message_id, *_ in messages],
                "n_emojis": [n_emojis.get(message_id, 0) for message_id, *_ in messages],
                "n_mentions": [content.count("@[") if content else 0 for content in contents],
                "has_url": [bool(content) and "[url:" in content for content in contents],
            },
            schema_overrides={"n_words": pl.Int64, "n_emojis": pl.Int64, "n_mentions": pl.Int64},
        ),
        TOKENS_FILENAME: pl.DataFrame(token_rows, schema=TOKEN_SCHEMA),
        EMOJIS_FILENAME: pl.DataFrame(emoji_rows, schema=EMOJI_SCHEMA),
    }


@log_execution
def process(interim_dir: Path, processed_dir: Path, model: str) -> dict[str, Path]:
    messages, aliases = read_interim(interim_dir)
    logger.info("Read {} messages and {} members", len(messages), len(aliases))

    tables = build_tables(messages, aliases, model)

    processed_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    written = {}
    for filename, table in tables.items():
        destination = processed_dir / filename
        path = str(destination).replace("'", "''")
        con.register("table_to_write", table)
        con.execute(f"COPY (SELECT * FROM table_to_write) TO '{path}' (FORMAT parquet)")
        logger.info("Wrote {} rows → {}", len(table), destination)
        written[filename] = destination
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chat", help="slug del chat (default: CHAT o `chat` de params.yml)")
    args = parser.parse_args(argv)

    params = load_params()
    load_logging(
        level=params["logging"]["level"],
        log_file=Path(params["logging"]["file"]),
        console=params["logging"].get("console", False),
    )
    chat = active_chat(params, args.chat)

    written = process(
        interim_dir=INTERIM_DIR / chat,
        processed_dir=PROCESSED_DIR / chat,
        model=params["nlp"]["model"],
    )
    for destination in written.values():
        print(f"silver → {destination}")


if __name__ == "__main__":
    main()
