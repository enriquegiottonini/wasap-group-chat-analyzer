"""Anonimización: parsea data/raw/<chat>/_chat.txt y deja en data/interim/<chat>/

- bronze.parquet: una fila por registro, con nombres reales y el texto sin tocar. Es
  para análisis manual en esta máquina (data/ nunca se versiona).
- messages_anon.parquet: la misma tabla anonimizada, que es la entrada de silver.

    uv run python -m wasap_group_analyzer.jobs.anonymize_job [--chat SLUG]
"""

import argparse
from pathlib import Path

import duckdb
from loguru import logger

from wasap_group_analyzer.anonymize import Masker
from wasap_group_analyzer.config import (
    active_chat,
    anonymize_settings,
    load_logging,
    load_params,
    load_salt,
)
from wasap_group_analyzer.constants import INTERIM_DIR, RAW_DIR
from wasap_group_analyzer.logging import log_execution
from wasap_group_analyzer.parsing import FSI, PDI, build_bronze
from wasap_group_analyzer.provenance import read_group_name

CHAT_FILENAME = "_chat.txt"
BRONZE_FILENAME = "bronze.parquet"
ANON_FILENAME = "messages_anon.parquet"


def people_names(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Nombres reales en el chat: remitentes (menos el grupo) y personas mencionadas."""
    rows = con.execute(
        f"""
        SELECT sender FROM bronze WHERE kind <> 'group_notice'
        UNION
        SELECT unnest(regexp_extract_all(body, '@{FSI}([^{PDI}]*){PDI}', 1)) FROM bronze
        """
    ).fetchall()
    return [name for (name,) in rows]


def _copy_to_parquet(con: duckdb.DuckDBPyConnection, query: str, destination: Path) -> None:
    path = str(destination).replace("'", "''")
    con.execute(f"COPY ({query}) TO '{path}' (FORMAT parquet)")
    logger.info("Wrote {}", destination)


@log_execution
def anonymize(
    chat_file: Path, group: str, interim_dir: Path, salt: bytes, settings: dict
) -> tuple[Path, Path]:
    interim_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()

    total = build_bronze(con, chat_file, group)
    logger.info("Parsed {} records from {}", total, chat_file)
    bronze_file = interim_dir / BRONZE_FILENAME
    _copy_to_parquet(con, "SELECT * FROM bronze", bronze_file)

    masker = Masker(people_names(con), salt, **settings)
    logger.info(
        "Masking {} name forms ({} ambiguous)",
        len(masker.forms),
        sum(len(owners) > 1 for owners in masker.forms.values()),
    )
    con.create_function("sender_id", masker.id, ["VARCHAR"], "VARCHAR")
    con.create_function(
        "mask_body", masker.mask_body, ["VARCHAR", "VARCHAR"], "VARCHAR", null_handling="special"
    )

    anon_file = interim_dir / ANON_FILENAME
    _copy_to_parquet(
        con,
        """
        SELECT
            record_no AS message_id,
            timestamp,
            CASE WHEN kind = 'group_notice' THEN NULL ELSE sender_id(sender) END AS sender_id,
            kind,
            mask_body(kind, body) AS body
        FROM bronze
        ORDER BY record_no
        """,
        anon_file,
    )
    return bronze_file, anon_file


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
    raw_dir = RAW_DIR / chat

    bronze_file, anon_file = anonymize(
        chat_file=raw_dir / CHAT_FILENAME,
        group=read_group_name(raw_dir),
        interim_dir=INTERIM_DIR / chat,
        salt=load_salt(),
        settings=anonymize_settings(params),
    )
    print(f"bronze (con nombres reales, solo local) → {bronze_file}")
    print(f"anonimizado → {anon_file}")


if __name__ == "__main__":
    main()
