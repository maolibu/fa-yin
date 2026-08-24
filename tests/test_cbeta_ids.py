from pathlib import Path

import pytest

from core.cbeta_ids import (
    discover_bookcase_xml_files,
    filename_matches_xml_id,
    parse_bookcase_id,
    split_sutra_id,
)


@pytest.mark.parametrize(
    ("value", "canon", "volume", "work", "juan", "sutra_id"),
    [
        ("T01n0001_001.xml", "T", "01", "0001", 1, "T0001"),
        ("CC001n0001_006.xml", "CC", "001", "0001", 6, "CC0001"),
        ("J37nB392_001.xml", "J", "37", "B392", 1, "JB392"),
        ("TX00na001_002.xml", "TX", "00", "a001", 2, "TXa001"),
        ("GA000na001_001.xml", "GA", "000", "a001", 1, "GAa001"),
        ("ZW01n0014c_001.xml", "ZW", "01", "0014c", 1, "ZW0014c"),
        ("T47n1987A", "T", "47", "1987A", None, "T1987A"),
    ],
)
def test_parse_bookcase_id(value, canon, volume, work, juan, sutra_id):
    parsed = parse_bookcase_id(value)
    assert (parsed.canon, parsed.volume, parsed.work, parsed.juan) == (
        canon,
        volume,
        work,
        juan,
    )
    assert parsed.sutra_id == sutra_id


def test_suffix_letters_are_not_partially_merged():
    assert parse_bookcase_id("T47n1987A").sutra_id == "T1987A"
    assert parse_bookcase_id("T47n1987B").sutra_id == "T1987B"


@pytest.mark.parametrize(
    "value",
    ["T47n1987A_extra.xml", "J37nB392_foo.xml", "not-an-id.xml"],
)
def test_invalid_or_partial_ids_fail(value):
    with pytest.raises(ValueError):
        parse_bookcase_id(value)


def test_split_sutra_id_uses_known_canons_for_ambiguous_prefixes():
    canons = {"G", "GA", "J", "T", "TX"}
    assert split_sutra_id("GA0026", canons) == ("GA", "0026")
    assert split_sutra_id("JB392", canons) == ("J", "B392")
    assert split_sutra_id("TXa001", canons) == ("TX", "a001")


def test_only_t0220_subworks_may_differ_between_filename_and_xml_id():
    source = parse_bookcase_id("T05n0220_001.xml", require_juan=True)
    assert filename_matches_xml_id(source, parse_bookcase_id("T05n0220a"))
    assert not filename_matches_xml_id(source, parse_bookcase_id("T05n0221a"))
    assert not filename_matches_xml_id(
        parse_bookcase_id("X05n0220_001.xml", require_juan=True),
        parse_bookcase_id("X05n0220a"),
    )


def test_discovery_rejects_silent_filename_omissions(tmp_path: Path):
    valid = tmp_path / "T" / "T01" / "T01n0001_001.xml"
    valid.parent.mkdir(parents=True)
    valid.write_text("<TEI/>", encoding="utf-8")
    assert discover_bookcase_xml_files(tmp_path) == [valid]

    invalid = tmp_path / "T" / "T01" / "bad.xml"
    invalid.write_text("<TEI/>", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid Bookcase XML"):
        discover_bookcase_xml_files(tmp_path)
