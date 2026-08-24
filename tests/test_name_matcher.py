from core.name_matcher import count_keywords


def test_count_keywords_matches_str_count_semantics():
    text = "金總持見總持，金總持持金剛經。aaaa"
    words = ["金總持", "總持", "金剛經", "不存在", "aa", "aa", ""]

    counts = count_keywords(text, words)

    assert counts == {
        word: text.count(word)
        for word in dict.fromkeys(words)
        if word and text.count(word)
    }


def test_count_keywords_handles_suffix_outputs_and_empty_inputs():
    assert count_keywords("阿彌陀佛", ["阿彌陀佛", "彌陀佛", "佛"]) == {
        "阿彌陀佛": 1,
        "彌陀佛": 1,
        "佛": 1,
    }
    assert count_keywords("", ["佛"]) == {}
    assert count_keywords("佛", []) == {}
