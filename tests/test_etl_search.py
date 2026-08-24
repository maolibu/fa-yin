from pathlib import Path
import sqlite3

from src.etl import etl_build_search as etl


def _write_xml(path: Path, xml_id: str, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''<?xml version="1.0" encoding="utf-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0"
     xmlns:xml="http://www.w3.org/XML/1998/namespace"
     xml:id="{xml_id}">
  <teiHeader>
    <fileDesc>
      <titleStmt><title level="m" xml:lang="zh-Hant">測試經</title></titleStmt>
      <publicationStmt><p>test</p></publicationStmt>
      <sourceDesc><p>test</p></sourceDesc>
    </fileDesc>
    <extent>1卷</extent>
  </teiHeader>
  <text><body><p>{text}</p></body></text>
</TEI>
''',
        encoding="utf-8",
    )


def test_etl_keeps_letter_prefixes_suffixes_and_cross_volume_segments(
    tmp_path: Path, monkeypatch
):
    xml_root = tmp_path / "XML"
    files = [
        (xml_root / "J" / "J37" / "J37nB392_001.xml", "J37nB392", "甲"),
        (xml_root / "T" / "T47" / "T47n1987A_001.xml", "T47n1987A", "乙"),
        (xml_root / "T" / "T47" / "T47n1987B_001.xml", "T47n1987B", "丙"),
        (xml_root / "L" / "L130" / "L130n1557_017.xml", "L130n1557", "前"),
        (xml_root / "L" / "L131" / "L131n1557_017.xml", "L131n1557", "後"),
        (xml_root / "T" / "T05" / "T05n0220_001.xml", "T05n0220a", "般若"),
    ]
    for path, xml_id, text in files:
        _write_xml(path, xml_id, text)

    monkeypatch.setattr(etl, "XML_BASE", xml_root)
    etl._processed_sutras = set()
    connection = etl.init_db(tmp_path / "search.db")
    for path, _, _ in files:
        assert etl.process_file(path, connection) is not None
    connection.commit()

    ids = {
        row[0] for row in connection.execute("SELECT sutra_id FROM catalog")
    }
    assert {"JB392", "T1987A", "T1987B", "L1557", "T0220a"} <= ids
    assert connection.execute(
        "SELECT plain_text FROM content WHERE sutra_id='L1557' AND juan=17"
    ).fetchone()[0] == "前後"
    assert connection.execute("SELECT count(*) FROM content_source").fetchone()[0] == 6
    assert connection.execute("SELECT count(*) FROM content").fetchone()[0] == 5
    connection.execute("INSERT INTO content_fts(content_fts) VALUES('integrity-check')")
    connection.close()


def test_invalid_xml_id_rolls_back_only_that_file(tmp_path: Path, monkeypatch):
    xml_root = tmp_path / "XML"
    path = xml_root / "T" / "T01" / "T01n0001_001.xml"
    _write_xml(path, "BROKEN", "不應寫入")
    monkeypatch.setattr(etl, "XML_BASE", xml_root)
    etl._processed_sutras = set()
    connection = etl.init_db(tmp_path / "search.db")
    assert etl.process_file(path, connection) is None
    assert connection.execute("SELECT count(*) FROM content").fetchone()[0] == 0
    connection.close()
