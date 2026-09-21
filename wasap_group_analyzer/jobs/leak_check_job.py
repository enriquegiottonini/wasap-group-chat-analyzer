"""Verificación de fugas: busca nombres reales del chat donde no deberían estar.

Toma los nombres de data/interim/<chat>/bronze.parquet (remitentes y mencionados), más
`anonymize.extra_names` de params.yml (apodos y nombres de terceros), y los
busca, como palabras completas y sin importar mayúsculas ni acentos, en:

- data/interim/<chat>/messages_anon.parquet y members.parquet, y data/processed/<chat>/*.parquet
- notebooks/*.py y notebooks/*.ipynb (código y salidas, sin las imágenes)
- references/ (el diccionario de datos) y README.md

Sale con código 1 si encuentra alguno. Por defecto solo reporta cuántos; con --show los
lista (en la terminal, nunca en el log).

    uv run python -m wasap_group_analyzer.jobs.leak_check_job [--chat SLUG] [--show]
"""

import argparse
from collections.abc import Iterator
import json
from pathlib import Path
import re
import sys

import duckdb
from loguru import logger

from wasap_group_analyzer.anonymize import fold, name_forms, normalize_name
from wasap_group_analyzer.config import (
    PROJECT_ROOT,
    active_chat,
    anonymize_settings,
    load_logging,
    load_params,
)
from wasap_group_analyzer.constants import (
    INTERIM_DIR,
    NOTEBOOKS_DIR,
    PROCESSED_DIR,
    REFERENCES_DIR,
)
from wasap_group_analyzer.jobs.anonymize_job import (
    ANON_FILENAME,
    BRONZE_FILENAME,
    MEMBERS_FILENAME,
    people_names,
)
from wasap_group_analyzer.logging import log_execution


def real_name_forms(bronze_file: Path, settings: dict) -> dict[str, set[str]]:
    """Formas (minúsculas, sin acentos) de los nombres reales, como las enmascara el job."""
    con = duckdb.connect()
    path = str(bronze_file).replace("'", "''")
    con.execute(f"CREATE VIEW bronze AS SELECT * FROM read_parquet('{path}')")
    allow = {normalize_name(name) for name in settings["allow_names"]}
    people = {normalize_name(name) for name in people_names(con)} - allow - {""}
    forms = name_forms(people, settings["min_length"], settings["keep_words"])
    for extra in settings["extra_names"]:
        forms.setdefault(fold(extra), set()).add(extra)
    return forms


# El lema lo inventa el lematizador de spaCy, no lo escribió nadie: una palabra común
# puede tener como lema un nombre ("amada" -> "amado"). Un nombre que sobreviviera al
# enmascarado aparecería igual en la columna `token`, así que no se pierde detección.
# El nombre de un emoji sale del emoji, no del chat: 👲 es "persona con gorro chino" aunque
# "chino" sea un apodo en `extra_names`. Un nombre en el texto aparecería en `content`.
GENERATED_COLUMNS = frozenset({"lemma", "emoji_name"})


def texts(path: Path) -> Iterator[str]:
    """Todo el texto de un archivo que podría llevar un nombre."""
    if path.suffix == ".parquet":
        con = duckdb.connect()
        relation = con.read_parquet(str(path))
        for column, dtype in zip(relation.columns, relation.dtypes):
            if str(dtype) == "VARCHAR" and column not in GENERATED_COLUMNS:
                for (value,) in relation.select(f'"{column}"').fetchall():
                    if value:
                        yield value
    elif path.suffix == ".ipynb":
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for cell in notebook["cells"]:
            yield "".join(cell["source"])
            for output in cell.get("outputs", []):
                if "text" in output:
                    yield "".join(output["text"])
                for mime, data in output.get("data", {}).items():
                    if not mime.startswith("image/"):
                        yield "".join(data) if isinstance(data, list) else str(data)
    else:
        yield path.read_text(encoding="utf-8")


def find_leaks(path: Path, forms: dict[str, set[str]]) -> set[str]:
    r"""Formas de nombre que aparecen en el archivo como palabras completas.

    Las palabras se separan por letras y dígitos, no por `\w`: el guion bajo separa
    (`_nombre_` es el cursivo de WhatsApp) igual que en el enmascarado.
    """
    folded = fold("\n".join(texts(path)))
    words = set(re.findall(r"[^\W_]+", folded))
    hits = {form for form in forms if " " not in form and form in words}
    hits |= {
        form
        for form in forms
        if " " in form and re.search(rf"(?<!\w){re.escape(form)}(?!\w)", folded)
    }
    return hits


def default_targets(chat: str) -> list[Path]:
    targets = [
        INTERIM_DIR / chat / ANON_FILENAME,
        INTERIM_DIR / chat / MEMBERS_FILENAME,
        *sorted((PROCESSED_DIR / chat).glob("*.parquet")),
    ]
    targets += sorted(NOTEBOOKS_DIR.glob("*.py")) + sorted(NOTEBOOKS_DIR.glob("*.ipynb"))
    targets += sorted(path for path in REFERENCES_DIR.rglob("*") if path.is_file())
    targets += [PROJECT_ROOT / "README.md"]
    return [path for path in targets if path.exists()]


@log_execution
def leak_check(bronze_file: Path, targets: list[Path], settings: dict) -> dict[Path, set[str]]:
    forms = real_name_forms(bronze_file, settings)
    results = {path: find_leaks(path, forms) for path in targets}
    for path, hits in results.items():
        logger.info("{}: {} name hits", path.name, len(hits))
    return results


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chat", help="slug del chat (default: CHAT o `chat` de params.yml)")
    parser.add_argument("--show", action="store_true", help="lista los nombres encontrados")
    args = parser.parse_args(argv)

    params = load_params()
    load_logging(
        level=params["logging"]["level"],
        log_file=Path(params["logging"]["file"]),
        console=params["logging"].get("console", False),
    )
    chat = active_chat(params, args.chat)
    bronze_file = INTERIM_DIR / chat / BRONZE_FILENAME
    if not bronze_file.exists():
        sys.exit(f"{bronze_file} not found: run `make anonymize` first")

    results = leak_check(bronze_file, default_targets(chat), anonymize_settings(params))
    leaks = 0
    for path, hits in results.items():
        status = "ok" if not hits else f"{len(hits)} nombre(s)"
        print(f"{status:>12}  {path.relative_to(PROJECT_ROOT)}")
        if hits and args.show:
            print("              " + ", ".join(sorted(hits)))
        leaks += len(hits)
    if leaks:
        sys.exit(f"Leak check failed: {leaks} real-name hit(s). Use SHOW=1 to list them.")
    print("Sin nombres reales en los archivos revisados.")


if __name__ == "__main__":
    main()
