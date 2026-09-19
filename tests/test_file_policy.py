import pytest

from wasap_group_analyzer.policies.file import FilePolicy, OnExists


def test_should_write_when_destination_missing(tmp_path):
    destination = tmp_path / "missing.txt"

    for on_exists in OnExists:
        assert FilePolicy(on_exists=on_exists).should_write(destination) is True


def test_skip_when_destination_exists(tmp_path):
    destination = tmp_path / "existing.txt"
    destination.write_text("data")

    assert FilePolicy(on_exists=OnExists.SKIP).should_write(destination) is False


def test_error_when_destination_exists(tmp_path):
    destination = tmp_path / "existing.txt"
    destination.write_text("data")

    with pytest.raises(FileExistsError):
        FilePolicy(on_exists=OnExists.ERROR).should_write(destination)


def test_overwrite_when_destination_exists(tmp_path):
    destination = tmp_path / "existing.txt"
    destination.write_text("data")

    assert FilePolicy(on_exists=OnExists.OVERWRITE).should_write(destination) is True
