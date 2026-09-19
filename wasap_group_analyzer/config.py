import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from loguru import logger
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARAMS_FILE = PROJECT_ROOT / "params.yml"
ENV_FILE = PROJECT_ROOT / ".env"


def load_params() -> dict:
    with PARAMS_FILE.open() as file:
        return yaml.safe_load(file)


def load_salt() -> bytes:
    """Sal secreta para los ids anonimizados, desde `ANON_SALT` en `.env`.

    Sin sal, los ids de 43 nombres conocidos se revierten con fuerza bruta trivial.
    """
    load_dotenv(ENV_FILE)
    salt = os.environ.get("ANON_SALT", "").strip()
    if not salt:
        raise RuntimeError(
            f"Falta ANON_SALT en {ENV_FILE}. Copia .env.example a .env y genera una sal con: "
            "python -c 'import secrets; print(secrets.token_hex(32))'"
        )
    return salt.encode("utf-8")


def load_logging(level: str, log_file: Path, console: bool = False) -> None:
    log_file = PROJECT_ROOT / log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    logger.remove()

    logger.add(
        log_file,
        level=level,
        format=("{time:YYYY-MM-DD HH:mm:ss.SSS} | {level} | {extra[job]} | {message}"),
    )

    if console:
        logger.add(sys.stderr, level=level)
