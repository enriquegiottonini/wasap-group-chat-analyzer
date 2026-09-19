import duckdb
import pytest

from tests.chat_fixture import GROUP, KINDS, write_chat
from wasap_group_analyzer.aliases import ANIMALS
from wasap_group_analyzer.anonymize import sender_id
from wasap_group_analyzer.config import ANONYMIZE_DEFAULTS
from wasap_group_analyzer.jobs import anonymize_job as job

SALT = b"sal-de-prueba"


@pytest.fixture
def outputs(tmp_path):
    chat_file = write_chat(tmp_path / "raw")
    return job.anonymize(chat_file, GROUP, tmp_path / "interim", SALT, ANONYMIZE_DEFAULTS)


def read(path):
    return duckdb.sql(f"SELECT * FROM read_parquet('{path}') ORDER BY 1").fetchall()


def test_writes_bronze_with_real_names_and_an_anonymized_copy(outputs):
    bronze_file, anon_file, _ = outputs

    assert bronze_file.name == job.BRONZE_FILENAME
    assert anon_file.name == job.ANON_FILENAME
    assert "Ana López" in {row[2] for row in read(bronze_file)}
    assert len(read(anon_file)) == len(KINDS)


def test_anonymized_rows_keep_order_time_and_kind(outputs):
    bronze_file, anon_file, _ = outputs

    for raw, anon in zip(read(bronze_file), read(anon_file)):
        assert anon[0] == raw[0]  # message_id = record_no
        assert anon[1] == raw[1]  # timestamp
        assert anon[3] == raw[4]  # kind


def test_senders_become_ids_except_the_group(outputs):
    _, anon_file, _ = outputs
    by_kind = {row[3]: row for row in read(anon_file)}

    assert by_kind["group_notice"][2] is None
    assert by_kind["text"][2] == sender_id("Ana López", SALT)
    assert by_kind["attachment"][2] == sender_id("Beto Ruiz", SALT)


def test_no_real_name_survives_in_the_anonymized_copy(outputs):
    _, anon_file, _ = outputs
    text = " ".join(str(value) for row in read(anon_file) for value in row)

    for name in ["Ana", "López", "Beto", "Ruiz", "Carla", "29.1"]:
        assert name not in text


def test_only_content_kinds_keep_a_body(outputs):
    _, anon_file, _ = outputs
    bodies = {row[3]: row[4] for row in read(anon_file)}

    assert bodies["poll"].startswith("POLL:")
    for kind in ["location", "system_notice", "deleted", "view_once", "unavailable", "empty"]:
        assert bodies[kind] is None


def test_members_get_animal_aliases_in_first_message_order(outputs):
    _, _, members_file = outputs
    members = read(members_file)

    assert [row[0] for row in members] == [
        sender_id("Ana López", SALT),
        sender_id("Beto Ruiz", SALT),
    ]
    assert [row[1] for row in members] == list(ANIMALS[:2])
