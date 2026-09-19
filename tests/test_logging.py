import pytest

from wasap_group_analyzer.config import load_logging
from wasap_group_analyzer.logging import log_execution


def test_log_execution_returns_value_and_logs_start_and_completion(tmp_path):
    log_file = tmp_path / "test.log"
    load_logging(level="INFO", log_file=log_file, console=False)

    @log_execution
    def add(a, b):
        return a + b

    assert add(2, 3) == 5

    log_contents = log_file.read_text()
    assert "Starting" in log_contents
    assert "Completed" in log_contents
    assert (
        "test_log_execution_returns_value_and_logs_start_and_completion.<locals>.add"
        in log_contents
    )


def test_log_execution_logs_failure_and_reraises(tmp_path):
    log_file = tmp_path / "test.log"
    load_logging(level="INFO", log_file=log_file, console=False)

    @log_execution
    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        boom()

    assert "Failed" in log_file.read_text()
