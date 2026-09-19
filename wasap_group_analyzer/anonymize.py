"""Anonimización: ids estables y no reversibles para los nombres del chat, y enmascarado
del contenido de los mensajes."""

from collections.abc import Iterable
from functools import cache
import hashlib
import re
import unicodedata
from urllib.parse import urlsplit

from wasap_group_analyzer.parsing import FSI, PDI

# WhatsApp antepone "~" + espacio angosto (U+202F) a los contactos que el celular no tiene
# guardados, y en las menciones escribe "@<U+2068>~Nombre<U+2069>" sin el espacio. También
# aparecen marcas de dirección (U+200E) y espacios duros. Todo eso se quita antes del hash
# para que "~ Ana López" (remitente) y "~Ana López" (mención) den el mismo id.
_INVISIBLE = re.compile(r"[\u200e\u2068\u2069]")
_SPACES = re.compile(r"[\s\u00a0\u202f]+")

SENDER_ID_BYTES = 5  # 10 caracteres hex: de sobra para ~50 remitentes sin colisiones

# Marcas que sustituyen a los datos personales dentro del texto.
MENTION_MARK = "@[{}]"  # mención a un miembro: @[id]
NAME_MARK = "[{}]"  # nombre de un miembro escrito en el texto: [id]
AMBIGUOUS_NAME = "[nombre]"  # nombre que comparten dos o más miembros
NUMBER_MARK = "[numero]"  # teléfono, cuenta, tarjeta, folio: 8 dígitos o más
EMAIL_MARK = "[correo]"
URL_MARK = "[url:{}]"  # solo se conserva el dominio

# Tipos de registro cuyo cuerpo es contenido escrito por alguien; el de los demás
# (avisos, ubicaciones, eliminados...) se descarta porque trae nombres o coordenadas.
CONTENT_KINDS = frozenset({"text", "attachment", "poll"})

MIN_NUMBER_DIGITS = 8
# Números largos que no son datos personales: fechas AAAA-MM-DD y rangos de años.
_NOT_PERSONAL_NUMBER = re.compile(r"\d{4}-\d{2}-\d{2}|\d{4} ?- ?\d{4}")


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


def fold(text: str) -> str:
    """Minúsculas y sin ninguna marca combinante (acentos, diéresis, texto "zalgo"), para
    comparar nombres como los escribe la gente: "Ǵúśťáṽó" y "Gustavo" dan "gustavo"."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


@cache
def _fold_char(ch: str) -> str:
    return fold(ch)


def _fold_with_origin(text: str) -> tuple[str, list[int] | None]:
    """`fold(text)` y, por cada carácter del resultado, su posición en `text`.

    Sirve para buscar sobre el texto normalizado y reemplazar en el original. Para texto
    ASCII el mapeo es la identidad y se omite (`None`).
    """
    if text.isascii():
        return text.lower(), None
    folded, origin = [], []
    for position, ch in enumerate(text):
        piece = _fold_char(ch)
        folded.append(piece)
        origin.extend([position] * len(piece))
    return "".join(folded), origin


def name_forms(
    names: Iterable[str], min_length: int = 3, keep_words: Iterable[str] = ()
) -> dict[str, set[str]]:
    """Formas en que un nombre puede aparecer en el texto → nombres a los que pertenecen.

    Por cada nombre: el nombre completo y cada una de sus palabras de al menos
    `min_length` caracteres que no sea un número ni esté en `keep_words`. Las formas van
    normalizadas con `fold`. Una forma con dos o más dueños es ambigua (p. ej. dos
    miembros que se llaman Daniel).
    """
    keep = {fold(word) for word in keep_words}
    forms: dict[str, set[str]] = {}
    for name in names:
        candidates = {name} if len(name) >= min_length else set()
        candidates |= {
            word
            for word in re.findall(r"\w+", name)
            if len(word) >= min_length and not word.isdigit()
        }
        for form in {fold(candidate) for candidate in candidates} - keep:
            forms.setdefault(form, set()).add(name)
    return forms


class Masker:
    """Enmascara datos personales en el texto de los mensajes.

    Primero, una pasada de izquierda a derecha con este orden de prioridad en cada
    posición:

    1. Mención `@<U+2068>Nombre<U+2069>` → `@[id]` (o `@[numero]` si es un teléfono).
    2. URL → `[url:dominio]`: el resto de la URL puede traer usuarios o identificadores.
    3. Correo → `[correo]`.
    4. Número de 8 dígitos o más (teléfono, cuenta, tarjeta, folio) → `[numero]`, salvo
       fechas y rangos de años.

    Después, los nombres: cada nombre o palabra de nombre de un miembro, como palabra
    completa, se busca sobre el texto normalizado con `fold` (sin mayúsculas ni marcas
    combinantes) y se reemplaza en el original por `[id]`, o por `[nombre]` si es de
    varios miembros. Es la misma normalización que usa la verificación de fugas.

    Los nombres de `allow_names` (bots como Meta AI) no se tocan.
    """

    def __init__(
        self,
        names: Iterable[str],
        salt: bytes,
        min_length: int = 3,
        keep_words: Iterable[str] = (),
        allow_names: Iterable[str] = (),
    ):
        self.salt = salt
        self.allow = {normalize_name(name) for name in allow_names}
        people = {normalize_name(name) for name in names} - self.allow - {""}
        self.forms = name_forms(people, min_length, keep_words)

        self.pattern = re.compile(
            "|".join(
                [
                    rf"(?P<mention>@{FSI}(?P<mentioned>[^{PDI}]*){PDI})",
                    r"(?P<url>https?://[^\s<>\"']+)",
                    r"(?P<email>[\w.+-]+@[\w-]+(?:\.[\w-]+)+)",
                    r"(?P<number>(?<![\w/])\+?\d[\d \u00a0\u202f().-]{6,}\d(?![\w/]))",
                ]
            ),
            re.IGNORECASE,
        )
        by_length = sorted(self.forms, key=len, reverse=True)
        self.name_pattern = (
            re.compile(rf"(?<!\w)(?:{'|'.join(map(re.escape, by_length))})(?!\w)")
            if by_length
            else None
        )

    def id(self, name: str) -> str:
        return sender_id(name, self.salt)

    def _replace(self, match: re.Match) -> str:
        if match["mention"] is not None:
            name = normalize_name(match["mentioned"])
            if name in self.allow:
                return "@" + name
            if re.fullmatch(r"\+?[\d ().-]+", name):
                return "@" + NUMBER_MARK
            return MENTION_MARK.format(self.id(name))
        if match["url"] is not None:
            host = (urlsplit(match["url"]).hostname or "").removeprefix("www.")
            return URL_MARK.format(host)
        if match["email"] is not None:
            return EMAIL_MARK
        number = match["number"]
        digits = sum(ch.isdigit() for ch in number)
        if digits < MIN_NUMBER_DIGITS or _NOT_PERSONAL_NUMBER.fullmatch(number):
            return number
        return NUMBER_MARK

    def _name_mark(self, form: str) -> str:
        owners = self.forms[form]
        if len(owners) > 1:
            return AMBIGUOUS_NAME
        return NAME_MARK.format(self.id(next(iter(owners))))

    def _mask_names(self, text: str) -> str:
        if self.name_pattern is None:
            return text
        folded, origin = _fold_with_origin(text)
        pieces, last = [], 0
        for match in self.name_pattern.finditer(folded):
            if origin is None:
                start, end = match.start(), match.end()
            else:
                start, end = origin[match.start()], origin[match.end() - 1] + 1
                # Las marcas combinantes que siguen a la última letra son parte del nombre.
                while end < len(text) and not _fold_char(text[end]):
                    end += 1
            pieces += [text[last:start], self._name_mark(match.group())]
            last = end
        pieces.append(text[last:])
        return "".join(pieces)

    def mask(self, text: str) -> str:
        return self._mask_names(self.pattern.sub(self._replace, text))

    def mask_body(self, kind: str, body: str | None) -> str | None:
        """Cuerpo enmascarado si es contenido; `None` si el cuerpo se descarta."""
        if kind not in CONTENT_KINDS or body is None:
            return None
        return self.mask(body)
