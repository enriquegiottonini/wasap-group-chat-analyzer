"""Los diccionarios de datos tienen que describir las columnas que existen de verdad."""

import json

import duckdb
import pytest

from tests.chat_fixture import GROUP, write_chat
from wasap_group_analyzer.config import ANONYMIZE_DEFAULTS
from wasap_group_analyzer.jobs import anonymize_job, process_job
from wasap_group_analyzer.metadata import dictionary


@pytest.fixture(scope="module")
def processed(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("pipeline")
    chat_file = write_chat(tmp_path / "raw")
    anonymize_job.anonymize(chat_file, GROUP, tmp_path / "interim", b"sal", ANONYMIZE_DEFAULTS)
    process_job.process(tmp_path / "interim", tmp_path / "processed", "es_core_news_sm")
    return tmp_path / "processed"


@pytest.fixture(scope="module")
def dictionaries(processed, tmp_path_factory):
    written = dictionary.build_dictionaries(processed, tmp_path_factory.mktemp("references"))
    return {
        path.stem.removeprefix("diccionario_"): json.loads(path.read_text("utf-8"))
        for path in written
    }


def test_every_column_is_documented_and_nothing_else(processed):
    for dataset, descriptions in dictionary.DESCRIPTIONS.items():
        columns = duckdb.sql(f"DESCRIBE SELECT * FROM '{processed / dataset}.parquet'").fetchall()

        assert list(descriptions) == [row[0] for row in columns], dataset
        assert all(description.strip() for description in descriptions.values()), dataset


def test_one_json_per_dataset(dictionaries):
    assert set(dictionaries) == set(dictionary.DESCRIPTIONS)

    for dataset, documented in dictionaries.items():
        assert documented["dataset"] == dataset
        assert documented["una_fila_es"] == dictionary.ROWS[dataset]
        assert documented["archivo"].endswith(f"{dataset}.parquet")
        assert documented["generado"]["comando"] == "make dictionary"


def test_each_column_carries_its_profile_and_description(dictionaries):
    for dataset, documented in dictionaries.items():
        descriptions = dictionary.DESCRIPTIONS[dataset]

        assert [column["nombre"] for column in documented["columnas"]] == list(descriptions)
        for column in documented["columnas"]:
            assert column["descripcion"] == descriptions[column["nombre"]]
            assert column["tipo"] and column["nulos_pct"] >= 0 and column["distintos"] >= 0


def test_text_columns_never_publish_their_range(dictionaries):
    """El mínimo y el máximo de una columna de texto serían mensajes reales."""
    for documented in dictionaries.values():
        text_columns = [c for c in documented["columnas"] if c["tipo"] == "VARCHAR"]

        assert all(column["rango"] is None for column in text_columns)
        assert not text_columns or documented["nota"]
    assert any(
        column["rango"]
        for documented in dictionaries.values()
        for column in documented["columnas"]
    )


def test_build_dictionaries_fails_when_a_column_is_undocumented(processed, tmp_path, monkeypatch):
    monkeypatch.setitem(dictionary.DESCRIPTIONS, "emojis", {"emoji": "solo una columna"})

    with pytest.raises(ValueError, match="sin describir"):
        dictionary.build_dictionaries(processed, tmp_path)
