from scraperbot.bot import parse_name_query


def test_parse_name_query_keeps_name_and_optional_rarity() -> None:
    assert parse_name_query("  Youthberk  FFR ") == ("Youthberk", "FFR")
    assert parse_name_query("Chronojet Dragon") == ("Chronojet Dragon", None)
    assert parse_name_query("R") == ("R", None)
