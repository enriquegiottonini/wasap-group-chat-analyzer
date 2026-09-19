"""Los diccionarios de datos tienen que describir las columnas que existen de verdad."""

from pathlib import Path
import re

import duckdb
import pytest

from tests.chat_fixture import GROUP, write_chat
from wasap_group_analyzer.config import ANONYMIZE_DEFAULTS
from wasap_group_analyzer.jobs import anonymize_job, process_job

REFERENCES = Path(__file__).parent.parent / "references"
DICTIONARIES = {
    "messages.parquet": "diccionario_messages.md",
    "tokens.parquet": "diccionario_tokens.md",
    "emojis.parquet": "diccionario_emojis.md",
    "messages_anon.parquet": "diccionario_messages_anon.md",
    "members.parquet": "diccionario_members.md",
}


def documented_columns(dictionary: Path) -> list[str]:
    """Primera columna de la tabla que va debajo de "## Columnas"."""
    section = dictionary.read_text(encoding="utf-8").split("## Columnas")[1].split("##")[0]
    rows = re.findall(r"^\| *`([^`]+)` *\|", section, re.MULTILINE)
    assert rows, f"{dictionary.name}: no documenta ninguna columna"
    return rows


@pytest.fixture(scope="module")
def datasets(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("pipeline")
    chat_file = write_chat(tmp_path / "raw")
    anonymize_job.anonymize(chat_file, GROUP, tmp_path / "interim", b"sal", ANONYMIZE_DEFAULTS)
    process_job.process(tmp_path / "interim", tmp_path / "processed", "es_core_news_sm")
    return {
        path.name: path
        for layer in ("interim", "processed")
        for path in (tmp_path / layer).glob("*.parquet")
    }


@pytest.mark.parametrize(("dataset", "dictionary"), DICTIONARIES.items())
def test_dictionary_matches_the_dataset_columns(dataset, dictionary, datasets):
    columns = [
        row[0] for row in duckdb.sql(f"DESCRIBE SELECT * FROM '{datasets[dataset]}'").fetchall()
    ]

    assert documented_columns(REFERENCES / dictionary) == columns


def test_every_dataset_has_a_dictionary_listed_in_the_index(datasets):
    index = (REFERENCES / "README.md").read_text(encoding="utf-8")

    for dataset, dictionary in DICTIONARIES.items():
        assert dataset in index, f"{dataset} no aparece en references/README.md"
        assert dictionary in index, f"{dictionary} no aparece en references/README.md"
    assert set(datasets) - {"bronze.parquet"} == set(DICTIONARIES)
