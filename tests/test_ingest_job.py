import hashlib
from pathlib import Path
import zipfile

import pytest

from wasap_group_analyzer.jobs import ingest_job as job
from wasap_group_analyzer.metadata.source import SOURCE_DESCRIPTION_FILENAME
from wasap_group_analyzer.policies.file import OnExists

# Chat sintético con las rarezas del formato de iOS: CRLF, U+200E, U+202F y una
# línea de continuación. Nunca usar mensajes reales en las pruebas.
CHAT = (
    "[28/09/24, 2:31:21\u202fp.m.] Ana: hola\r\n"
    "\u200e[28/09/24, 2:36:51\u202fp.m.] Beto: \u200esticker omitted\r\n"
    "[29/09/24, 9:05:00\u202fa.m.] Ana: primera línea\r\n"
    "segunda línea\r\n"
)

SOURCE = {
    "name": "WhatsApp (Meta Platforms, Inc.)",
    "url": "https://www.whatsapp.com",
    "timezone": "America/Hermosillo",
    "method": "Exportar chat → Sin archivos.",
    "description": "Historial del grupo\n  en texto plano.",
    "documentation": ["https://faq.whatsapp.com/1180414079177245/"],
    "usage": "Solo fines académicos.",
}


def make_export(tmp_path, members=None, name="WhatsApp Chat - Grupo Prueba 🏢.zip"):
    export_zip = tmp_path / "downloads" / name
    export_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(export_zip, "w") as archive:
        for member, content in (members or {"_chat.txt": CHAT}).items():
            info = zipfile.ZipInfo(member, date_time=(2026, 9, 18, 17, 37, 0))
            archive.writestr(info, content)
    return export_zip


def test_ingest_copies_extracts_and_documents_the_export(tmp_path):
    export_zip = make_export(tmp_path)
    raw_dir = tmp_path / "raw"

    written = job.ingest("grupo_prueba", export_zip, raw_dir, SOURCE, OnExists.SKIP)

    raw_zip = raw_dir / job.RAW_ZIP_FILENAME
    assert raw_zip.read_bytes() == export_zip.read_bytes()
    assert (raw_dir / "_chat.txt").read_text(encoding="utf-8", newline="") == CHAT
    assert written == raw_dir / SOURCE_DESCRIPTION_FILENAME

    text = written.read_text(encoding="utf-8")
    assert text.startswith('Exportación del grupo de WhatsApp "Grupo Prueba 🏢"\n')
    assert "Chat en el proyecto: grupo_prueba (carpetas data/*/grupo_prueba/)" in text
    assert "Fuente: WhatsApp (Meta Platforms, Inc.) (https://www.whatsapp.com)" in text
    assert "Obtención: Exportar chat → Sin archivos." in text
    assert "Archivo original: WhatsApp Chat - Grupo Prueba 🏢.zip" in text
    assert "Exportado: 2026-09-18 17:37" in text
    assert "Periodo: 2024-09-28 a 2024-09-29 (3 mensajes y avisos del sistema)" in text
    assert "Zona horaria de los mensajes: America/Hermosillo" in text
    assert "  Historial del grupo en texto plano." in text
    assert "  - https://faq.whatsapp.com/1180414079177245/" in text
    assert "  Solo fines académicos." in text
    assert hashlib.sha256(export_zip.read_bytes()).hexdigest() in text
    assert "_chat.txt" in text
    assert "Generado por ingest_job" in text


def test_ingest_skip_keeps_existing_raw_zip(tmp_path):
    raw_dir = tmp_path / "raw"
    job.ingest("grupo_prueba", make_export(tmp_path), raw_dir, SOURCE, OnExists.SKIP)
    first_copy = (raw_dir / job.RAW_ZIP_FILENAME).read_bytes()

    newer = make_export(tmp_path, {"_chat.txt": CHAT + CHAT})
    job.ingest("grupo_prueba", newer, raw_dir, SOURCE, OnExists.SKIP)

    assert (raw_dir / job.RAW_ZIP_FILENAME).read_bytes() == first_copy


def test_ingest_overwrite_replaces_raw_zip_and_chat(tmp_path):
    raw_dir = tmp_path / "raw"
    job.ingest("grupo_prueba", make_export(tmp_path), raw_dir, SOURCE, OnExists.SKIP)

    newer = make_export(tmp_path, {"_chat.txt": CHAT + CHAT})
    written = job.ingest("grupo_prueba", newer, raw_dir, SOURCE, OnExists.OVERWRITE)

    assert (raw_dir / "_chat.txt").read_text(encoding="utf-8", newline="") == CHAT + CHAT
    assert "(6 mensajes y avisos del sistema)" in written.read_text(encoding="utf-8")


def test_ingest_rejects_zip_slip(tmp_path):
    export_zip = make_export(tmp_path, {"_chat.txt": CHAT, "../evil.txt": "x"})
    raw_dir = tmp_path / "raw"

    with pytest.raises(ValueError, match="Unsafe path"):
        job.ingest("grupo_prueba", export_zip, raw_dir, SOURCE, OnExists.SKIP)

    assert not (tmp_path / "evil.txt").exists()
    assert not (raw_dir / "_chat.txt").exists()


def test_ingest_fails_when_export_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        job.ingest("x", tmp_path / "nope.zip", tmp_path / "raw", SOURCE, OnExists.SKIP)


def test_group_name_supports_ios_and_android_filenames(tmp_path):
    assert job.group_name(tmp_path / "WhatsApp Chat - Los Primos.zip") == "Los Primos"
    assert job.group_name(tmp_path / "WhatsApp Chat with Los Primos.zip") == "Los Primos"
    assert job.group_name(tmp_path / "export.zip") == "export"


def test_slugify_drops_accents_emoji_and_punctuation():
    assert job.slugify("Baketon City 🏢😈💋") == "baketon_city"
    assert job.slugify("Los Primos — Año 2025!") == "los_primos_ano_2025"
    with pytest.raises(ValueError, match="--chat"):
        job.slugify("🏢😈💋")


def test_resolve_export_uses_registered_zip_of_active_chat(tmp_path, monkeypatch):
    monkeypatch.delenv("CHAT", raising=False)
    params = {"chat": "primos", "chats": {"primos": "~/primos.zip", "tios": "/tmp/tios.zip"}}

    chat, export_zip = job.resolve_export(params, chat=None, export_zip=None)
    assert chat == "primos"
    assert export_zip == Path("~/primos.zip").expanduser()

    assert job.resolve_export(params, chat="tios", export_zip=None) == (
        "tios",
        Path("/tmp/tios.zip"),
    )

    with pytest.raises(KeyError, match="known"):
        job.resolve_export(params, chat="otro", export_zip=None)


def test_resolve_export_names_an_explicit_zip_after_its_group(tmp_path):
    export_zip = tmp_path / "WhatsApp Chat - Los Primos 🏠.zip"

    assert job.resolve_export({}, chat=None, export_zip=export_zip) == ("los_primos", export_zip)
    assert job.resolve_export({}, chat="primos", export_zip=export_zip) == ("primos", export_zip)
    with pytest.raises(ValueError, match="Invalid chat slug"):
        job.resolve_export({}, chat="../fuera", export_zip=export_zip)
