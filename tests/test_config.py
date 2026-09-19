from loguru import logger
import pytest

from wasap_group_analyzer import config


def test_load_params_parses_yaml_file(tmp_path, monkeypatch):
    params_file = tmp_path / "params.yml"
    params_file.write_text("logging:\n  level: INFO\nsource:\n  export_zip: chat.zip\n")
    monkeypatch.setattr(config, "PARAMS_FILE", params_file)

    params = config.load_params()

    assert params == {"logging": {"level": "INFO"}, "source": {"export_zip": "chat.zip"}}


def test_load_logging_writes_to_configured_file(tmp_path):
    log_file = tmp_path / "nested" / "test.log"

    config.load_logging(level="INFO", log_file=log_file, console=False)
    with logger.contextualize(job="test"):
        logger.info("hello from test")

    assert log_file.exists()
    assert "hello from test" in log_file.read_text()


def test_load_salt_reads_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ANON_SALT=abc123\n")
    monkeypatch.setattr(config, "ENV_FILE", env_file)
    monkeypatch.delenv("ANON_SALT", raising=False)

    assert config.load_salt() == b"abc123"


def test_load_salt_fails_loudly_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.delenv("ANON_SALT", raising=False)

    with pytest.raises(RuntimeError, match="ANON_SALT"):
        config.load_salt()
