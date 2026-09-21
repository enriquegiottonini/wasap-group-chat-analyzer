"""Diccionario de datos: un archivo JSON por cada conjunto tidy.

Lo único escrito a mano son las descripciones de abajo; el tipo, los nulos, los valores
distintos y el rango los calcula DuckDB con SUMMARIZE al generar los archivos.

    uv run python -m wasap_group_analyzer.metadata.dictionary [--chat SLUG]
"""

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path

import duckdb
from loguru import logger

from wasap_group_analyzer.config import PROJECT_ROOT, active_chat, load_logging, load_params
from wasap_group_analyzer.constants import PROCESSED_DIR, REFERENCES_DIR
from wasap_group_analyzer.logging import log_execution

# SUMMARIZE reporta el mínimo y el máximo de cada columna: en las de texto eso serían
# mensajes reales, así que el rango solo se publica para los tipos que no son texto.
TEXT_TYPE = "VARCHAR"
TEXT_RANGE_NOTE = (
    "El rango de las columnas de texto no se publica: su mínimo y su máximo serían "
    "mensajes reales del chat."
)

# Qué representa una fila de cada conjunto (la "granularidad" de la tabla).
ROWS = {
    "messages": "un mensaje del chat, incluidos adjuntos y avisos",
    "tokens": "un token (palabra, número, signo o emoji) dentro de un mensaje",
    "emojis": "un emoji usado en un mensaje",
}

DESCRIPTIONS = {
    "messages": {
        "message_id": "Orden del registro en la exportación, desde 1; llave primaria y unión con tokens y emojis",
        "timestamp": "Fecha y hora local del celular que exportó, sin zona horaria",
        "sender": "Alias del miembro (un animal); vacío en los avisos que firma el grupo",
        "message_type": "text, sticker, image, audio, video, gif, video_note, document, contact, poll, location, view_once, deleted, unavailable, system_notice, group_notice o empty",
        "content": "Texto que escribió la persona, anonimizado: el mensaje, el pie de foto o la encuesta; vacío si el mensaje no trae texto",
        "is_edited": "Si WhatsApp marcó el mensaje como editado",
        "n_words": "Palabras del contenido: tokens alfabéticos; 0 si no hay texto",
        "n_emojis": "Emojis del contenido; es el número de filas de este mensaje en emojis",
        "n_mentions": "Menciones a miembros (@[Alias]) en el contenido",
        "has_url": "Si el contenido trae al menos un enlace ([url:dominio])",
    },
    "tokens": {
        "message_id": "Mensaje al que pertenece el token; une con messages",
        "token_idx": "Posición del token dentro del mensaje, desde 0",
        "token": "El token tal como se escribió, en minúsculas",
        "lemma": "Lema en minúsculas; en adjetivos las formas cortas se unifican con la larga (buen: bueno)",
        "pos": "Categoría gramatical UPOS de spaCy (NOUN, VERB, ADJ...); el modelo se entrenó con noticias y se equivoca con la jerga del chat",
        "is_alpha": "Si el token es una palabra: solo letras; números, signos y emojis son false",
        "is_stop": "Palabra vacía: lista de spaCy, muletilla del chat, letra sola o risa; para contar adjetivos no conviene filtrar por aquí, porque spaCy considera vacíos a bueno, mejor o nuevo",
        "is_laugh": "Si es una risa: jaja, jejeje, jsjsjs, xd, lol y variantes",
    },
    "emojis": {
        "message_id": "Mensaje en el que aparece el emoji; une con messages",
        "emoji_idx": "Posición del emoji dentro del mensaje, desde 0",
        "emoji": "El emoji completo; una secuencia con tono de piel o unida con ZWJ cuenta como uno solo",
        "emoji_name": "Nombre del emoji en español",
    },
}


def profile(con: duckdb.DuckDBPyConnection, parquet: Path) -> tuple[int, list[dict]]:
    """Filas del parquet y, por columna, su tipo, nulos, valores distintos y rango."""
    path = str(parquet).replace("'", "''")
    columns = con.execute(
        f"""
        SELECT column_name, column_type, null_percentage, min, max
        FROM (SUMMARIZE SELECT * FROM read_parquet('{path}'))
        """
    ).fetchall()

    # `approx_unique` de SUMMARIZE es una estimación (HyperLogLog): en un diccionario de
    # datos el conteo exacto importa, p. ej. para ver que una llave no se repite.
    counts = ", ".join(f'count(DISTINCT "{name}")' for name, *_ in columns)
    n_rows, *distinct = con.execute(
        f"SELECT count(*), {counts} FROM read_parquet('{path}')"
    ).fetchone()

    return n_rows, [
        {
            "column_name": name,
            "type": column_type,
            # Una tabla vacía no tiene nulos ni rango que reportar.
            "nulls_pct": float(nulls) if nulls is not None else 0.0,
            "n_distinct": unique,
            "value_range": ""
            if column_type == TEXT_TYPE or minimum is None
            else f"{minimum} – {maximum}",
        }
        for (name, column_type, nulls, minimum, maximum), unique in zip(columns, distinct)
    ]


def document(dataset: str, parquet: Path, n_rows: int, columns: list[dict]) -> dict:
    """El diccionario de un conjunto, listo para escribirse como JSON."""
    descriptions = DESCRIPTIONS[dataset]
    shown = parquet.relative_to(PROJECT_ROOT) if parquet.is_relative_to(PROJECT_ROOT) else parquet
    documented = {
        "dataset": dataset,
        "archivo": str(shown),
        "una_fila_es": ROWS[dataset],
        "filas": n_rows,
        "columnas": [
            {
                "nombre": column["column_name"],
                "tipo": column["type"],
                "nulos_pct": column["nulls_pct"],
                "distintos": column["n_distinct"],
                "rango": column["value_range"] or None,
                "descripcion": descriptions[column["column_name"]],
            }
            for column in columns
        ],
        "generado": {
            "fecha": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            "comando": "make dictionary",
            "perfil": "SUMMARIZE de DuckDB;",
        },
    }
    if any(column["type"] == TEXT_TYPE for column in columns):
        documented["nota"] = TEXT_RANGE_NOTE
    return documented


@log_execution
def build_dictionaries(processed_dir: Path, references_dir: Path) -> list[Path]:
    """Escribe un diccionario por conjunto y devuelve las rutas.

    Falla si una columna no está descrita, o si se describe una que ya no existe: es lo
    que evita que el diccionario se quede atrás cuando cambian los datos.
    """
    con = duckdb.connect()
    references_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for dataset, descriptions in DESCRIPTIONS.items():
        parquet = processed_dir / f"{dataset}.parquet"
        if not parquet.exists():
            raise FileNotFoundError(f"{parquet} not found: run `make process` first")

        n_rows, columns = profile(con, parquet)
        undocumented = {column["column_name"] for column in columns} - set(descriptions)
        missing = set(descriptions) - {column["column_name"] for column in columns}
        if undocumented or missing:
            raise ValueError(
                f"{dataset}: columnas sin describir: {sorted(undocumented)}; "
                f"descritas pero inexistentes: {sorted(missing)}"
            )

        destination = references_dir / f"diccionario_{dataset}.json"
        documented = document(dataset, parquet, n_rows, columns)
        destination.write_text(
            json.dumps(documented, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        logger.info("Documented {} columns → {}", len(columns), destination)
        written.append(destination)
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

    for destination in build_dictionaries(PROCESSED_DIR / chat, REFERENCES_DIR):
        print(f"diccionario → {destination.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
