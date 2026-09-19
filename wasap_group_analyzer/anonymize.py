"""Anonimización: ids estables y no reversibles para los nombres del chat."""

import hashlib
import re
import unicodedata

# WhatsApp antepone "~" + espacio angosto (U+202F) a los contactos que el celular no tiene
# guardados, y en las menciones escribe "@\u2068~Nombre\u2069" sin el espacio. También aparecen
# marcas de dirección (U+200E) y espacios duros. Todo eso se quita antes del hash para que
# "~ Ana López" (remitente) y "~Ana López" (mención) den el mismo id.
_INVISIBLE = re.compile(r"[\u200e\u2068\u2069]")
_SPACES = re.compile(r"[\s\u00a0\u202f]+")

SENDER_ID_BYTES = 5  # 10 caracteres hex: de sobra para ~50 remitentes sin colisiones


def normalize_name(name: str) -> str:
    name = unicodedata.normalize("NFC", _INVISIBLE.sub("", name))
    return _SPACES.sub(" ", name).strip().lstrip("~").strip()


def sender_id(name: str, salt: bytes) -> str:
    """Id anónimo de un nombre: blake2b con llave secreta sobre el nombre normalizado.

    Sin la sal (ANON_SALT en .env) no se puede recalcular ni revertir por fuerza bruta,
    aunque la lista de posibles nombres sea corta.
    """
    digest = hashlib.blake2b(
        normalize_name(name).encode("utf-8"), key=salt, digest_size=SENDER_ID_BYTES
    )
    return digest.hexdigest()
