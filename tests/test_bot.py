from scraperbot.query import parse_name_query, parse_name_search_query


def test_parse_name_query_keeps_name_and_optional_rarity() -> None:
    assert parse_name_query("  Youthberk  FFR ") == ("Youthberk", "FFR")
    assert parse_name_query("Chronojet Dragon") == ("Chronojet Dragon", None)
    assert parse_name_query("R") == ("R", None)


def test_parse_name_search_query_supports_multiple_rarities_and_finishes() -> None:
    parsed = parse_name_search_query("Youthberk rarity:ffr,sec finish:holo,standard")

    assert parsed.name == "Youthberk"
    assert parsed.rarities == ("FFR", "SEC")
    assert {finish.value for finish in parsed.finishes} == {"holo", "standard"}
