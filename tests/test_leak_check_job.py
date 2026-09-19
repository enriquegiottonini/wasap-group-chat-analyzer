import json

import pytest

from tests.chat_fixture import GROUP, write_chat
from wasap_group_analyzer.config import ANONYMIZE_DEFAULTS
from wasap_group_analyzer.jobs import anonymize_job
from wasap_group_analyzer.jobs import leak_check_job as job


@pytest.fixture
def interim(tmp_path):
    chat_file = write_chat(tmp_path / "raw")
    return anonymize_job.anonymize(
        chat_file, GROUP, tmp_path / "interim", b"sal", ANONYMIZE_DEFAULTS
    )


def write_notebook(path, source, outputs):
    notebook = {"cells": [{"cell_type": "code", "source": [source], "outputs": outputs}]}
    path.write_text(json.dumps(notebook), encoding="utf-8")
    return path


def test_the_anonymized_copy_has_no_leaks(interim):
    bronze_file, anon_file = interim

    results = job.leak_check(bronze_file, [anon_file], ANONYMIZE_DEFAULTS)

    assert results == {anon_file: set()}


def test_finds_names_in_text_files_whatever_the_accents(interim, tmp_path):
    bronze_file, _ = interim
    leaky = tmp_path / "leaky.md"
    leaky.write_text("Saludos a ANA y a Lopez", encoding="utf-8")
    clean = tmp_path / "clean.md"
    clean.write_text("Saludos a Anabel", encoding="utf-8")

    results = job.leak_check(bronze_file, [leaky, clean], ANONYMIZE_DEFAULTS)

    assert results[leaky] == {"ana", "lopez"}
    assert results[clean] == set()


def test_scans_notebook_code_and_outputs_but_not_images(interim, tmp_path):
    bronze_file, _ = interim
    image_only = write_notebook(
        tmp_path / "image.ipynb", "x = 1", [{"data": {"image/png": "Beto Ruiz"}}]
    )
    html_output = write_notebook(
        tmp_path / "html.ipynb", "x = 1", [{"data": {"text/html": "<td>Beto</td>"}}]
    )

    results = job.leak_check(bronze_file, [image_only, html_output], ANONYMIZE_DEFAULTS)

    assert results[image_only] == set()
    assert results[html_output] == {"beto"}


def test_allowed_names_are_not_leaks(interim, tmp_path):
    bronze_file, _ = interim
    notes = tmp_path / "notes.md"
    notes.write_text("Ana López", encoding="utf-8")
    settings = {**ANONYMIZE_DEFAULTS, "allow_names": ["Ana López"]}

    assert job.leak_check(bronze_file, [notes], settings)[notes] == set()
