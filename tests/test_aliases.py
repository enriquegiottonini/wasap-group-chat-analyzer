from wasap_group_analyzer.aliases import ANIMALS, assign_aliases


def test_aliases_follow_the_given_order_and_ignore_repeats():
    aliases = assign_aliases(["b", "a", "b", "c"])

    assert aliases == {"b": ANIMALS[0], "a": ANIMALS[1], "c": ANIMALS[2]}


def test_aliases_skip_animals_that_share_a_word_with_a_real_name():
    aliases = assign_aliases(["a", "b"], avoid_words=[ANIMALS[0].upper(), ANIMALS[1]])

    assert aliases == {"a": ANIMALS[2], "b": ANIMALS[3]}


def test_aliases_compare_words_without_accents():
    aliases = assign_aliases(["a"], avoid_words=["colibri"])

    assert "Colibrí" not in aliases.values()


def test_aliases_run_out_gracefully():
    aliases = assign_aliases([str(n) for n in range(len(ANIMALS) + 2)])

    assert aliases[str(len(ANIMALS) + 1)] == f"Animal {len(ANIMALS) + 2}"
    assert len(set(aliases.values())) == len(ANIMALS) + 2
