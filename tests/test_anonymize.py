from wasap_group_analyzer.anonymize import normalize_name, sender_id

SALT = b"sal-de-prueba"


def test_normalize_name_unifies_sender_and_mention_forms():
    as_sender = "~\u202fAna López"
    as_mention = "\u2068~Ana López\u2069"
    with_lrm = "\u200eAna\u00a0 López "

    assert normalize_name(as_sender) == "Ana López"
    assert normalize_name(as_mention) == "Ana López"
    assert normalize_name(with_lrm) == "Ana López"


def test_normalize_name_unifies_unicode_composition():
    composed = "Jos\u00e9"
    decomposed = "Jose\u0301"

    assert normalize_name(composed) == normalize_name(decomposed)


def test_sender_id_is_stable_short_hex_and_salted():
    first = sender_id("~\u202fAna López", SALT)

    assert first == sender_id("\u2068~Ana López\u2069", SALT)
    assert len(first) == 10
    assert int(first, 16) >= 0
    assert first != sender_id("Ana López", b"otra-sal")
    assert first != sender_id("Beto", SALT)
