from datetime import datetime

import duckdb
import pytest

from tests.chat_fixture import GROUP, KINDS, NNBSP, write_chat
from wasap_group_analyzer.parsing import build_bronze


@pytest.fixture
def bronze(tmp_path):
    con = duckdb.connect()
    total = build_bronze(con, write_chat(tmp_path), GROUP)
    return con, total


def rows(con):
    return con.execute("SELECT record_no, timestamp, sender, body, kind FROM bronze").fetchall()


def test_one_row_per_crlf_record_even_with_multiline_messages(bronze):
    con, total = bronze

    assert total == len(KINDS)
    multiline = rows(con)[2]
    assert multiline[3] == "línea uno\nlínea dos"


def test_classifies_every_record_kind(bronze):
    con, _ = bronze

    assert [row[4] for row in rows(con)] == KINDS


def test_parses_12_hour_clock_with_narrow_space(bronze):
    con, _ = bronze
    timestamps = [row[1] for row in rows(con)]

    assert timestamps[0] == datetime(2025, 2, 1, 9, 5, 0)
    assert timestamps[2] == datetime(2025, 2, 1, 12, 30, 0)  # 12:30 p.m. es mediodía
    assert timestamps[3] == datetime(2025, 2, 2, 0, 5, 0)  # 12:05 a.m. es medianoche


def test_keeps_sender_as_written_and_body_after_the_colon(bronze):
    con, _ = bronze
    first, second = rows(con)[:2]

    assert first[2] == "Ana López"
    assert second[2] == f"~{NNBSP}Beto Ruiz"
    assert first[3].startswith("hola @")


def test_rejects_non_ios_exports(tmp_path):
    android = tmp_path / "_chat.txt"
    android.write_text("01/02/2025, 09:05 - Ana: hola\r\n", encoding="utf-8", newline="")

    with pytest.raises(ValueError, match="iOS export"):
        build_bronze(duckdb.connect(), android, GROUP)
