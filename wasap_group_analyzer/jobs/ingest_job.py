"""Ingesta: copia el zip exportado de WhatsApp a data/raw/<chat>/, lo descomprime y
documenta la fuente en FUENTE.txt.

    uv run python -m wasap_group_analyzer.jobs.ingest_job [--chat SLUG] [--zip RUTA]

Sin --zip, toma el zip del chat activo en `chats` de params.yml. Con --zip, el chat se
llama como el grupo (p. ej. "Los Primos 🏠" → los_primos) salvo que se pase --chat.
"""

import argparse
from datetime import date, datetime
import os
from pathlib import Path
import re
import shutil
import time
import unicodedata
import zipfile

from loguru import logger

from wasap_group_analyzer.config import active_chat, load_logging, load_params, validate_chat
from wasap_group_analyzer.constants import RAW_DIR
from wasap_group_analyzer.logging import log_execution
from wasap_group_analyzer.metadata.source import sha256, write_source_description
from wasap_group_analyzer.policies.file import FilePolicy, OnExists

RAW_ZIP_FILENAME = "whatsapp_chat.zip"

# iOS: "WhatsApp Chat - <grupo>.zip"; Android: "WhatsApp Chat with <grupo>.zip".
GROUP_FROM_FILENAME = re.compile(r"^WhatsApp Chat (?:- |with )(?P<group>.+)\.zip$")

# Solo la fecha del encabezado "[dd/mm/aa, ..." (con o sin la marca U+200E al inicio);
# el parseo completo de cada mensaje es trabajo del job de anonimización.
MESSAGE_DATE = re.compile(r"^\u200e?\[(\d{2})/(\d{2})/(\d{2}), ")


def group_name(export_zip: Path) -> str:
    match = GROUP_FROM_FILENAME.match(export_zip.name)
    return match["group"] if match else export_zip.stem


def slugify(name: str) -> str:
    """Nombre de grupo → slug de carpeta: sin acentos ni emojis, en minúsculas y con _."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_name.lower()).strip("_")
    if not slug:
        raise ValueError(f"Cannot derive a chat slug from {name!r}; pass --chat")
    return slug


def resolve_export(params: dict, chat: str | None, export_zip: Path | None) -> tuple[str, Path]:
    """Qué chat se ingesta y de qué zip: `--zip` explícito o el zip registrado en `chats`."""
    if export_zip:
        return (validate_chat(chat) if chat else slugify(group_name(export_zip))), export_zip

    chat = active_chat(params, chat)
    chats = params.get("chats") or {}
    if chat not in chats:
        raise KeyError(f"Chat {chat!r} is not in `chats` of params.yml (known: {list(chats)})")
    return chat, Path(chats[chat]).expanduser()


def extract_zip(zip_file: Path, destination: Path, policy: FilePolicy) -> list[Path]:
    """Extrae todos los archivos del zip en `destination` y devuelve sus rutas.

    Revisa antes todas las rutas (zip-slip) y deja a cada archivo la fecha que trae en el
    zip, que es la de la exportación y no la de la extracción.
    """
    root = destination.resolve()
    extracted = []
    with zipfile.ZipFile(zip_file) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        for member in members:
            if root not in (root / member.filename).resolve().parents:
                raise ValueError(f"Unsafe path in zip: {member.filename}")

        for member in members:
            target = destination / member.filename
            if policy.should_write(target):
                archive.extract(member, destination)
                exported = time.mktime((*member.date_time, 0, 0, -1))
                os.utime(target, (exported, exported))
                logger.info("Extracted {} → {}", member.filename, target)
            else:
                logger.info("Skipped existing {}", target)
            extracted.append(target)
    return extracted


def find_chat_file(files: list[Path]) -> Path:
    texts = [path for path in files if path.suffix == ".txt"]
    if len(texts) != 1:
        raise ValueError(f"Expected exactly one chat .txt in the export, found {texts}")
    return texts[0]


def message_date_range(chat_file: Path) -> tuple[date, date, int]:
    """Primera y última fecha de mensaje y número de mensajes (líneas con encabezado)."""
    dates = []
    with chat_file.open(encoding="utf-8") as file:
        for line in file:
            match = MESSAGE_DATE.match(line)
            if match:
                day, month, year = (int(part) for part in match.groups())
                dates.append(date(2000 + year, month, day))
    if not dates:
        raise ValueError(f"No WhatsApp message headers found in {chat_file}")
    return min(dates), max(dates), len(dates)


@log_execution
def ingest(chat: str, export_zip: Path, raw_dir: Path, source: dict, on_exists: OnExists) -> Path:
    if not export_zip.is_file():
        raise FileNotFoundError(f"WhatsApp export not found: {export_zip}")

    raw_dir.mkdir(parents=True, exist_ok=True)
    policy = FilePolicy(on_exists=on_exists)

    raw_zip = raw_dir / RAW_ZIP_FILENAME
    if policy.should_write(raw_zip):
        # copy2 conserva la fecha del archivo: la de la descarga/exportación, no la de hoy.
        shutil.copy2(export_zip, raw_zip)
        logger.info("Copied {} → {}", export_zip, raw_zip)
    elif sha256(raw_zip) != sha256(export_zip):
        logger.warning(
            "{} differs from {} and was kept; use on_exists=overwrite to replace it",
            raw_zip,
            export_zip,
        )

    files = extract_zip(raw_zip, raw_dir, policy)
    chat_file = find_chat_file(files)
    first, last, n_messages = message_date_range(chat_file)
    with zipfile.ZipFile(raw_zip) as archive:
        # El zip guarda la hora local de quien lo creó, sin zona horaria.
        exported_at = datetime(*archive.getinfo(chat_file.name).date_time)  # noqa: DTZ001

    return write_source_description(
        raw_dir=raw_dir,
        source=source,
        export={
            "chat": chat,
            "original_filename": export_zip.name,
            "group": group_name(export_zip),
            "exported_at": exported_at,
            "first_message": first,
            "last_message": last,
            "n_messages": n_messages,
        },
        files=[raw_zip, *files],
        job=Path(__file__).stem,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chat", help="slug del chat (default: CHAT o `chat` de params.yml)")
    parser.add_argument("--zip", type=Path, help="zip exportado (default: el de `chats`)")
    parser.add_argument("--on-exists", choices=[policy.value for policy in OnExists])
    args = parser.parse_args(argv)

    params = load_params()
    load_logging(
        level=params["logging"]["level"],
        log_file=Path(params["logging"]["file"]),
        console=params["logging"].get("console", False),
    )
    source = params["source"]
    try:
        chat, export_zip = resolve_export(params, args.chat, args.zip and args.zip.expanduser())
    except (KeyError, ValueError, RuntimeError) as error:
        parser.error(str(error).strip('"'))

    written = ingest(
        chat=chat,
        export_zip=export_zip,
        raw_dir=RAW_DIR / chat,
        source=source,
        on_exists=OnExists(args.on_exists or source["on_exists"]),
    )
    print(f"FUENTE → {written}")


if __name__ == "__main__":
    main()
