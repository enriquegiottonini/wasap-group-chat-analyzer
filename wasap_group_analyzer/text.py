"""Texto de los mensajes para silver: tipo de mensaje, contenido legible, emojis y palabras.

Parte del cuerpo anonimizado de `messages_anon.parquet` (ver `anonymize.Masker` para las
marcas `@[id]`, `[id]`, `[nombre]`, `[url:dominio]`, `[correo]` y `[numero]`). Las
decisiones de este módulo se justifican con datos en `notebooks/02_eda_silver.py`.
"""

from collections.abc import Iterable, Iterator
import re

import emoji
import spacy
from spacy.lang.es.stop_words import STOP_WORDS

from wasap_group_analyzer.aliases import UNKNOWN_MEMBER
from wasap_group_analyzer.parsing import FSI, LRM, PDI

# --- Tipo de mensaje -------------------------------------------------------------------

# Marcador que deja WhatsApp al exportar "sin archivos" → tipo de mensaje.
ATTACHMENT_TYPES = {
    "sticker": "sticker",
    "image": "image",
    "video": "video",
    "audio": "audio",
    "GIF": "gif",
    "document": "document",
    "Contact card": "contact",
    "video note": "video_note",
}
# Siempre va precedido de U+200E; sin exigirlo, un pie de foto se confundiría con él.
_ATTACHMENT_MARKER = re.compile(f"{LRM}([A-Za-z ]+?) omitted")


def message_type(kind: str, body: str | None) -> str:
    """El tipo de registro de interim (`kind`), con los adjuntos separados por su tipo."""
    if kind != "attachment" or body is None:
        return kind
    marker = _ATTACHMENT_MARKER.search(body)
    return ATTACHMENT_TYPES.get(marker[1], "other_attachment") if marker else "other_attachment"


# --- Contenido legible -----------------------------------------------------------------

_EDITED = re.compile(f"{LRM}?<This message was edited>")
_INVISIBLE = re.compile(f"[{LRM}{FSI}{PDI}]")
_MEMBER_MARK = re.compile(r"(?P<at>@?)\[(?P<id>[0-9a-f]{10})\]")


def is_edited(body: str | None) -> bool:
    return body is not None and _EDITED.search(body) is not None


def clean_content(kind: str, body: str | None, aliases: dict[str, str]) -> str | None:
    """Texto escrito por el usuario, legible: sin marcas invisibles, sin el sufijo de
    edición ni el marcador de adjunto (queda el pie de foto) y con los ids de los
    miembros cambiados por su alias: `@[Ajolote]`, `[Ajolote]`.

    Los corchetes dejan claro que es un miembro anonimizado y no, por ejemplo, alguien
    hablando de un animal. `None` si no queda texto (stickers, audios, avisos...).
    """
    if body is None:
        return None
    text = _EDITED.sub("", body)
    if kind == "attachment":
        text = _ATTACHMENT_MARKER.sub("", text)
    text = _INVISIBLE.sub("", text)
    text = _MEMBER_MARK.sub(
        lambda match: f"{match['at']}[{aliases.get(match['id'], UNKNOWN_MEMBER)}]", text
    )
    return text.strip() or None


# --- Emojis ----------------------------------------------------------------------------


def extract_emojis(text: str | None) -> list[str]:
    """Emojis del texto en orden. Una secuencia unida con ZWJ (una familia) o con tono de
    piel cuenta como un solo emoji. Los emoticonos de texto (":)", "xD") no son emojis."""
    return [match["emoji"] for match in emoji.emoji_list(text)] if text else []


def emoji_name(symbol: str) -> str:
    """Nombre del emoji en español, p. ej. "cara llorando de risa"."""
    name = emoji.demojize(symbol, language="es", delimiters=("", ""))
    return name.replace("_", " ")


# --- Palabras --------------------------------------------------------------------------

# Todo lo que no son palabras escritas por el usuario: marcas de anonimización (menciones,
# nombres, URLs...), la mención a Meta AI y las etiquetas de las encuestas.
_NOT_WORDS = re.compile(
    r"@?\[[^\]\n]*\]|@Meta AI|^POLL:|^OPTION:|\(\d+ votes?\)", re.MULTILINE | re.IGNORECASE
)


def text_for_words(content: str | None) -> str:
    """El contenido sin las marcas de anonimización ni etiquetas: lo que analiza spaCy."""
    return _NOT_WORDS.sub(" ", content) if content else ""


# Risas: al menos dos sílabas iguales ("jaja", "jejeje", "haha", "ajajaja"), variantes
# con "s" ("jsjsjs") y "xd"/"lol". No atrapa "he", "ha", "has" ni "hijo".
LAUGH = re.compile(
    r"a?(?:[jh]+([aeiou])+)(?:[jh]+\1+)+[jh]*"
    r"|j[jks]*s[jks]*"
    r"|x+d+"
    r"|lo+l",
    re.IGNORECASE,
)

# Palabras vacías propias del chat, además de las de spaCy (STOP_WORDS): abreviaturas de
# palabras vacías, muletillas y vocativos. La jerga con significado ("neta", "chamba",
# "pedo") no está aquí: es contenido.
CHAT_STOP_WORDS = frozenset(
    {
        # abreviaturas y variantes de palabras vacías
        "q", "k", "qe", "ke", "xq", "pq", "pk", "porq", "tb", "tmb", "tmbn", "tambn",
        "pa", "pal", "pos", "ps", "nomas", "nomás", "osea", "ntp",
        # muletillas, vocativos, afirmaciones y negaciones coloquiales
        "we", "wey", "güey", "guey", "bro", "ok", "okay", "oki", "va", "sip", "nop", "nel",
        "simon", "smn", "ah", "eh", "oh", "uh", "ay", "mm", "mmm", "mmmm", "aja", "ajá",
    }
)  # fmt: skip


def is_laugh(word: str) -> bool:
    return LAUGH.fullmatch(word) is not None


def is_stop_word(word: str) -> bool:
    """Palabra vacía: de spaCy, del chat, una sola letra o una risa."""
    word = word.lower()
    return word in STOP_WORDS or word in CHAT_STOP_WORDS or len(word) == 1 or is_laugh(word)


# spaCy da el lema de la forma corta: "buen día" → "buen". Se unifica con la larga.
ADJECTIVE_APOCOPES = {
    "buen": "bueno",
    "mal": "malo",
    "gran": "grande",
    "primer": "primero",
    "tercer": "tercero",
}


def load_nlp(model: str) -> spacy.language.Language:
    """Modelo de spaCy solo con lo necesario (etiquetado y lemas): sin parser ni NER."""
    return spacy.load(model, disable=["parser", "ner"])


def tokenize(nlp: spacy.language.Language, texts: Iterable[str]) -> Iterator[list[dict]]:
    """Por cada texto, sus tokens (sin espacios) con lo que necesita el análisis.

    Una palabra es un token alfabético (`is_alpha`): letras, con o sin acento. Números,
    signos, emojis y emoticonos quedan como tokens pero no cuentan como palabras.
    """
    for doc in nlp.pipe(texts, batch_size=1000):
        rows = []
        for token in doc:
            if token.is_space:
                continue
            word = token.lower_
            lemma = token.lemma_.lower()
            if token.pos_ == "ADJ":
                lemma = ADJECTIVE_APOCOPES.get(lemma, lemma)
            rows.append(
                {
                    "token_idx": len(rows),
                    "token": word,
                    "lemma": lemma,
                    "pos": token.pos_,
                    "is_alpha": token.is_alpha,
                    "is_stop": token.is_alpha and is_stop_word(word),
                    "is_laugh": token.is_alpha and is_laugh(word),
                }
            )
        yield rows
