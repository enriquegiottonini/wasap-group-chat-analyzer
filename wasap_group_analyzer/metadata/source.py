from datetime import UTC, date, datetime
import hashlib
from pathlib import Path
import re
import textwrap

from loguru import logger

SOURCE_DESCRIPTION_FILENAME = "FUENTE.txt"


def read_group_name(raw_dir: Path) -> str:
    """Nombre del grupo según la primera línea de FUENTE.txt (la escribe el job de ingesta)."""
    first_line = (raw_dir / SOURCE_DESCRIPTION_FILENAME).read_text(encoding="utf-8").split("\n")[0]
    match = re.search(r'"(.+)"', first_line)
    if not match:
        raise ValueError(f"Group name not found in {raw_dir / SOURCE_DESCRIPTION_FILENAME}")
    return match[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d %H:%M")


def _indented(text: str) -> str:
    # El YAML trae la descripción partida en varias líneas; la reacomodamos a lo ancho.
    return textwrap.fill(
        " ".join(text.split()), width=88, initial_indent="  ", subsequent_indent="  "
    )


def write_source_description(
    raw_dir: Path,
    source: dict,
    export: dict,
    files: list[Path],
    job: str,
) -> Path:
    """Escribe `FUENTE.txt` junto a los datos crudos: de dónde vienen, qué son y cuándo
    se obtuvieron.

    `source` viene de `params.yml` (nombre, url, método, descripción, documentación, uso);
    `export` lo calcula el job a partir del zip (archivo original, grupo, fecha de
    exportación y periodo que cubren los mensajes).
    """
    first: date = export["first_message"]
    last: date = export["last_message"]
    source_line = source["name"] + (f" ({source['url']})" if source.get("url") else "")
    exported_at = f"{export['exported_at']:%Y-%m-%d %H:%M}"
    n_messages = f"{export['n_messages']:,}"

    lines = [
        f'Exportación del grupo de WhatsApp "{export["group"]}"',
        f"Chat en el proyecto: {export['chat']} (carpetas data/*/{export['chat']}/)"
        if export.get("chat")
        else None,
        f"Fuente: {source_line}",
        f"Obtención: {source['method']}" if source.get("method") else None,
        f"Archivo original: {export['original_filename']}",
        f"Exportado: {exported_at} (hora local del celular, según el zip)",
        f"Periodo: {first:%Y-%m-%d} a {last:%Y-%m-%d} ({n_messages} mensajes y avisos del sistema)",
        f"Zona horaria de los mensajes: {source['timezone']} (hora local, sin offset)"
        if source.get("timezone")
        else None,
    ]
    lines = [line for line in lines if line is not None]

    if source.get("description"):
        lines += ["", "Descripción", _indented(source["description"])]
    if source.get("documentation"):
        lines += ["", "Documentación"] + [f"  - {url}" for url in source["documentation"]]
    if source.get("usage"):
        lines += ["", "Uso", _indented(source["usage"])]

    lines += ["", "Archivos (fecha según la fecha del archivo, UTC)"]
    for path in files:
        stats = path.stat()
        lines.append(
            f"  {path.name:<22} {stats.st_size / 1e6:>8.1f} MB   {_utc(stats.st_mtime)}"
            f"   sha256 {sha256(path)}"
        )

    lines += ["", f"Generado por {job} el {_utc(datetime.now(UTC).timestamp())} UTC"]

    destination = raw_dir / SOURCE_DESCRIPTION_FILENAME
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Wrote source description → {}", destination)
    return destination
