import xml.etree.ElementTree as ET
from pathlib import Path

from core.cbeta_parser import CBETAParser
from obsidian_vault import xml_to_md
from obsidian_vault.xml_to_md import (
    _parse_ref_target,
    convert_sutra_group,
    extract_metadata,
    find_sutra_groups,
)


def _write_bookcase_xml(
    path: Path,
    *,
    xml_id: str,
    title: str = "跨冊測試經",
    total_juan: int = 2,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''<TEI xmlns="http://www.tei-c.org/ns/1.0"
                 xmlns:xml="http://www.w3.org/XML/1998/namespace"
                 xml:id="{xml_id}">
          <teiHeader><fileDesc>
            <titleStmt><title level="m" xml:lang="zh-Hant">{title}</title></titleStmt>
            <extent>{total_juan}卷</extent>
          </fileDesc></teiHeader>
          <text><body><p>如是我聞。</p></body></text>
        </TEI>''',
        encoding="utf-8",
    )


def test_parser_gaiji_fallback_is_explicit_and_detectable():
    parser = CBETAParser.__new__(CBETAParser)
    parser.gaiji_data = {}
    assert parser._resolve_gaiji("#CB99999") == "[CB99999]"


def test_parser_gaiji_uses_normalized_fields_before_composition():
    parser = CBETAParser.__new__(CBETAParser)
    parser.gaiji_data = {
        "CB00001": {"norm_uni_char": "正", "composition": "[止*一]"}
    }
    assert parser._resolve_gaiji("#CB00001") == "正"


def test_vault_reference_parser_supports_all_id_shapes():
    assert _parse_ref_target("../J37/J37nB392.xml#xpath2(//0001a01)") == "J37nB392"
    assert _parse_ref_target("../T47/T47n1987A.xml#x") == "T47n1987A"
    assert _parse_ref_target("../CC001/CC001n0001.xml") == "CC001n0001"


def test_vault_metadata_does_not_merge_uppercase_suffixes():
    root = ET.fromstring(
        '''<TEI xmlns="http://www.tei-c.org/ns/1.0"
                 xmlns:xml="http://www.w3.org/XML/1998/namespace"
                 xml:id="T47n1987A">
             <teiHeader><fileDesc><titleStmt>
               <title level="m" xml:lang="zh-Hant">測試</title>
             </titleStmt></fileDesc></teiHeader>
           </TEI>'''
    )
    meta = extract_metadata(ET.ElementTree(root))
    assert meta["sutra_id"] == "T1987A"
    assert meta["volume"] == "47"


def test_vault_groups_cross_volume_files_by_authoritative_sutra_id(
    tmp_path, monkeypatch
):
    xml_base = tmp_path / "cbeta" / "XML"
    first = xml_base / "B" / "B01" / "B01n0001_001.xml"
    second = xml_base / "B" / "B02" / "B02n0001_002.xml"
    _write_bookcase_xml(first, xml_id="B01n0001")
    _write_bookcase_xml(second, xml_id="B02n0001")
    monkeypatch.setattr(xml_to_md, "XML_BASE", xml_base)

    groups = find_sutra_groups()

    assert groups == [("B0001", [str(first), str(second)])]


def test_vault_cross_volume_output_is_one_note_with_cbeta_aliases(tmp_path):
    first = tmp_path / "cbeta" / "XML" / "B" / "B01" / "B01n0001_001.xml"
    second = tmp_path / "cbeta" / "XML" / "B" / "B02" / "B02n0001_002.xml"
    _write_bookcase_xml(first, xml_id="B01n0001")
    _write_bookcase_xml(second, xml_id="B02n0001")
    output = tmp_path / "vault"

    meta = convert_sutra_group([str(first), str(second)], output, verbose=False)

    assert meta is not None
    assert meta["sutra_id"] == "B0001"
    assert meta["cbeta_ids"] == ["B01n0001", "B02n0001"]
    assert meta["total_juan"] == 2
    notes = list((output / "經文").rglob("*.md"))
    assert len(notes) == 1
    assert notes[0].name == "B0001_跨冊測試經.md"
    text = notes[0].read_text(encoding="utf-8")
    assert 'sutra_id: "B0001"' in text
    assert '  - "B01n0001"' in text
    assert '  - "B02n0001"' in text
    assert text.count("## 卷") == 2
