import pytest

from tests.chat_fixture import FSI, LRM, NNBSP, PDI
from wasap_group_analyzer.anonymize import (
    Masker,
    fold,
    name_forms,
    normalize_name,
    sender_id,
)

SALT = b"sal-de-prueba"
ACUTE = chr(0x301)  # acento agudo combinante
STROKE = chr(0x336)  # tachado combinante, como en texto decorado


def decorate(text: str, mark: str) -> str:
    return "".join(ch + mark for ch in text)


def test_normalize_name_unifies_sender_and_mention_forms():
    as_sender = f"~{NNBSP}Ana López"
    as_mention = f"{FSI}~Ana López{PDI}"
    with_lrm = f"{LRM}Ana{chr(0xA0)} López "

    assert normalize_name(as_sender) == "Ana López"
    assert normalize_name(as_mention) == "Ana López"
    assert normalize_name(with_lrm) == "Ana López"


def test_normalize_name_unifies_unicode_composition():
    composed = "Jos" + chr(0xE9)
    decomposed = "Jose" + ACUTE

    assert normalize_name(composed) == normalize_name(decomposed)


def test_sender_id_is_stable_short_hex_and_salted():
    first = sender_id(f"~{NNBSP}Ana López", SALT)

    assert first == sender_id(f"{FSI}~Ana López{PDI}", SALT)
    assert len(first) == 10
    assert int(first, 16) >= 0
    assert first != sender_id("Ana López", b"otra-sal")
    assert first != sender_id("Beto", SALT)


def test_fold_drops_case_accents_and_decorative_marks():
    assert fold("Ramón") == "ramon"
    assert fold(decorate("Gustavo", ACUTE)) == "gustavo"
    assert fold(decorate("Zuko", STROKE)) == "zuko"


def test_name_forms_split_names_and_flag_shared_first_names():
    forms = name_forms(["Daniel Soto", "Daniel Ruiz", "M", "Ana 2024"], min_length=3)

    assert forms["daniel"] == {"Daniel Soto", "Daniel Ruiz"}
    assert forms["soto"] == {"Daniel Soto"}
    assert forms["daniel soto"] == {"Daniel Soto"}
    assert "m" not in forms
    assert "2024" not in forms


def test_name_forms_skip_keep_words():
    forms = name_forms(["Ana LCC"], keep_words=["lcc"])

    assert "lcc" not in forms
    assert "ana" in forms


@pytest.fixture
def masker():
    return Masker(
        ["Ana López", f"~{NNBSP}Beto Ruiz", "Daniel Soto", "Daniel Vega", "M", "Meta AI"],
        SALT,
        allow_names=["Meta AI"],
    )


def ids(masker, *names):
    return [masker.id(name) for name in names]


def test_mentions_become_ids_of_the_mentioned_member(masker):
    (beto,) = ids(masker, "Beto Ruiz")

    assert masker.mask(f"hola @{FSI}~Beto Ruiz{PDI}!") == f"hola @[{beto}]!"


def test_mentions_of_allowed_bots_and_phone_numbers(masker):
    assert masker.mask(f"@{FSI}Meta AI{PDI} dime algo") == "@Meta AI dime algo"
    assert masker.mask(f"@{FSI}+52 662 123 4567{PDI}") == "@[numero]"


def test_names_in_text_whatever_the_case_accents_or_decoration(masker):
    ana, beto = ids(masker, "Ana López", "Beto Ruiz")

    assert masker.mask("ya llegó ANA lopez") == f"ya llegó [{ana}]"
    assert masker.mask(decorate("Beto", STROKE) + ", ven") == f"[{beto}], ven"
    assert masker.mask("anabel y bet") == "anabel y bet"  # solo palabras completas


def test_shared_first_names_are_masked_as_ambiguous(masker):
    (soto,) = ids(masker, "Daniel Soto")

    assert masker.mask("Daniel dijo que Soto no viene") == f"[nombre] dijo que [{soto}] no viene"


def test_short_names_and_allowed_names_are_left_alone(masker):
    assert masker.mask("M&M con Meta") == "M&M con Meta"


def test_urls_keep_only_their_domain(masker):
    text = "mira https://www.instagram.com/perfil.x/?hl=es y ya"

    assert masker.mask(text) == "mira [url:instagram.com] y ya"


def test_emails_and_long_numbers_are_masked_but_not_dates(masker):
    text = "escribe a ana.l@example.com o al +52 (662) 123-4567, tarjeta 1234 5678 9012 3456"

    assert masker.mask(text) == "escribe a [correo] o al [numero], tarjeta [numero]"
    assert masker.mask("el 2025-01-15, temporada 2024-2025, $1 500 000") == (
        "el 2025-01-15, temporada 2024-2025, $1 500 000"
    )


def test_mask_body_keeps_content_kinds_and_drops_the_rest(masker):
    (ana,) = ids(masker, "Ana López")

    assert masker.mask_body("text", "hola Ana") == f"hola [{ana}]"
    assert masker.mask_body("attachment", f"foto de Ana {LRM}image omitted") == (
        f"foto de [{ana}] {LRM}image omitted"
    )
    assert masker.mask_body("system_notice", f"{LRM}Ana López added Carla") is None
    assert masker.mask_body("location", f"{LRM}Location: https://maps.google.com/?q=1,2") is None
    assert masker.mask_body("text", None) is None
