import os
from pathlib import Path
import re
import sys

from dotenv import load_dotenv
from loguru import logger
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PARAMS_FILE = PROJECT_ROOT / "params.yml"
ENV_FILE = PROJECT_ROOT / ".env"

# Un chat se identifica por un slug que también es el nombre de su carpeta en data/*/.
CHAT_SLUG = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def load_params() -> dict:
    with PARAMS_FILE.open() as file:
        return yaml.safe_load(file)


def validate_chat(chat: str) -> str:
    if not CHAT_SLUG.match(chat):
        raise ValueError(f"Invalid chat slug {chat!r}: use lowercase letters, digits and _")
    return chat


def active_chat(params: dict, chat: str | None = None) -> str:
    """Chat con el que trabajan jobs y notebooks.

    En orden: el argumento explícito (`--chat`), la variable de entorno `CHAT` (así
    `make ... CHAT=x` llega también a los notebooks) y `chat` en params.yml.
    """
    chat = chat or os.environ.get("CHAT") or params.get("chat")
    if not chat:
        raise RuntimeError("No chat selected: set `chat` in params.yml or pass CHAT=<slug>")
    return validate_chat(chat)


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
