import pytest

from tests.chat_fixture import LRM
from wasap_group_analyzer.text import (
    clean_content,
    emoji_name,
    extract_emojis,
    is_edited,
    is_laugh,
    is_stop_word,
    load_nlp,
    message_type,
    text_for_words,
    tokenize,
)

ALIASES = {"aaaaaaaaaa": "Juárez"}
ZWJ = chr(0x200D)
FAMILY = ZWJ.join([chr(0x1F468), chr(0x1F469), chr(0x1F467)])  # familia unida con ZWJ
THUMBS_UP_TONE = chr(0x1F44D) + chr(0x1F3FD)  # pulgar arriba, tono de piel medio


@pytest.mark.parametrize(
    ("kind", "body", "expected"),
    [
        ("text", "hola", "text"),
        ("attachment", f"{LRM}sticker omitted", "sticker"),
        ("attachment", f"mira {LRM}image omitted", "image"),
        ("attachment", f"{LRM}GIF omitted", "gif"),
        ("attachment", f"{LRM}Contact card omitted", "contact"),
        ("attachment", f"{LRM}video note omitted", "video_note"),
        ("attachment", f"{LRM}hologram omitted", "other_attachment"),
        ("location", None, "location"),
    ],
)
def test_message_type_splits_attachments_by_marker(kind, body, expected):
    assert message_type(kind, body) == expected


def test_caption_text_is_not_mistaken_for_the_marker():
    assert message_type("attachment", f"the video is great {LRM}image omitted") == "image"


def test_clean_content_keeps_what_the_user_wrote_with_aliases():
    body = f"hola @[aaaaaaaaaa] y [bbbbbbbbbb] {LRM}<This message was edited>"

    assert clean_content("text", body, ALIASES) == "hola @[Juárez] y [persona]"
    assert is_edited(body)
    assert not is_edited("hola")


def test_clean_content_drops_attachment_markers_and_empty_results():
    assert clean_content("attachment", f"mira esto {LRM}image omitted", ALIASES) == "mira esto"
    assert clean_content("attachment", f"{LRM}sticker omitted", ALIASES) is None
    assert clean_content("location", None, ALIASES) is None


def test_text_for_words_removes_marks_and_poll_labels():
    content = "POLL:\n¿Vamos?\nOPTION: Sí (2 votes)\nOPTION: No (1 vote)"

    assert text_for_words(content).split() == ["¿Vamos?", "Sí", "No"]
    assert text_for_words("hola @[Juárez], [nombre] y [url:x.com] @Meta AI").split() == [
        "hola",
        ",",
        "y",
    ]


def test_extract_emojis_counts_sequences_as_one():
    text = f"jaja 😂😂 {FAMILY} {THUMBS_UP_TONE} :) xD"

    assert extract_emojis(text) == ["😂", "😂", FAMILY, THUMBS_UP_TONE]
    assert extract_emojis(None) == []
    assert emoji_name("😂") == "cara llorando de risa"


@pytest.mark.parametrize(
    "word", ["jaja", "JAJAJA", "jajaj", "jeje", "jijiji", "haha", "ajajaja", "jsjsjs", "xd", "lol"]
)
def test_laughs(word):
    assert is_laugh(word)
    assert is_stop_word(word)


@pytest.mark.parametrize("word", ["he", "ha", "has", "hijo", "jaula", "ja", "jose"])
def test_not_laughs(word):
    assert not is_laugh(word)


def test_stop_words_include_spacy_chat_fillers_and_single_letters():
    for word in ["de", "que", "we", "q", "pa", "nomás", "w", "d"]:
        assert is_stop_word(word)
    for word in ["neta", "chamba", "tacos"]:
        assert not is_stop_word(word)


def test_tokenize_marks_words_stop_words_laughs_and_adjective_lemmas():
    nlp = load_nlp("es_core_news_sm")

    (tokens,) = tokenize(nlp, ["jajaja buen taco 😂 a las 5"])
    by_token = {token["token"]: token for token in tokens}

    assert [token["token_idx"] for token in tokens] == list(range(len(tokens)))
    assert by_token["jajaja"]["is_laugh"] and by_token["jajaja"]["is_stop"]
    assert by_token["taco"]["is_alpha"] and not by_token["taco"]["is_stop"]
    assert not by_token["5"]["is_alpha"]
    assert not by_token["😂"]["is_alpha"]
    if by_token["buen"]["pos"] == "ADJ":
        assert by_token["buen"]["lemma"] == "bueno"
