import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from tools.lineage_builder.build_lineage_db import (
    BuildError,
    EXPECTED_INDEXES,
    build_lineage_database,
    compare_databases,
    parse_time_sql,
)


FIXTURES = Path(__file__).parent / "fixtures" / "lineage"


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_fixture(tmp_path, name="lineage.db", mode="source-faithful", **kwargs):
    output = tmp_path / name
    manifest = build_lineage_database(
        person_xml=FIXTURES / "person.xml",
        place_xml=FIXTURES / "place.xml",
        time_sql=FIXTURES / "time.sql",
        output=output,
        mode=mode,
        **kwargs,
    )
    return output, manifest


def test_source_faithful_build_and_schema(tmp_path):
    output, manifest = build_fixture(tmp_path)
    assert manifest["counts"] == {
        "dynasties": 1,
        "eras": 3,
        "persons": 2,
        "places": 2,
        "edges": 2,
        "person_scriptures": 6,
    }
    db = sqlite3.connect(output)
    db.row_factory = sqlite3.Row
    assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    indexes = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL")
    }
    assert EXPECTED_INDEXES <= indexes

    person = dict(db.execute("SELECT * FROM persons WHERE person_id='A000001'").fetchone())
    assert person["name"] == "甲師"
    assert json.loads(person["aliases"]) == ["甲別名"]
    assert person["birth_year"] == -500
    assert person["death_year"] == 500
    assert person["dynasty"] == "前朝/後朝"
    assert person["is_monk"] == 1
    assert json.loads(person["cbeta_refs"]) == [
        "( CBETA T01n0001_p0001a01 ) 測試經",
        "嵌套書目",
    ]

    place = dict(db.execute(
        "SELECT * FROM places WHERE place_id='PL000000000001'"
    ).fetchone())
    assert place["place_id"] == "PL000000000001"
    assert place["name_zh"] == "最後中文名"
    assert place["latitude"] == 30.25
    assert place["longitude"] == 120.5
    assert place["name_ja"] == "Tesuto"
    assert json.loads(place["cbeta_refs"])[-1] == "嵌套地點書目"
    unnamed = dict(db.execute(
        "SELECT * FROM places WHERE place_id='PL000000000002'"
    ).fetchone())
    assert unnamed["name_zh"] == "Place_PL000000000002"
    assert unnamed["district"] == ""

    edge = dict(db.execute(
        "SELECT * FROM edges WHERE source_id='A000002' AND target_id='A000001'"
    ).fetchone())
    assert (edge["source_id"], edge["target_id"]) == ("A000002", "A000001")
    assert edge["description"].startswith("教師聲明")
    assert edge["cbeta_ref"] == "https://example.test/teacher"
    scriptures = {
        tuple(row)
        for row in db.execute(
            "SELECT scripture_id, relation FROM person_scriptures WHERE person_id='A000001'"
        )
    }
    assert scriptures == {
        ("T0001", "mentioned"),
        ("T0002", "authored"),
        ("A1504", "authored"),
        ("Ba001", "authored"),
        ("T1986B", "authored"),
        ("T0310.37", "authored"),
    }
    assert db.execute(
        "SELECT gender FROM persons WHERE person_id='A000002'"
    ).fetchone()[0] == 9
    db.close()

    audit = json.loads(output.with_suffix(".audit.json").read_text(encoding="utf-8"))
    assert audit["edges"]["dangling"][0]["target_id"] == "A999999"
    assert audit["persons"]["invalid_scripture_references"] == [{
        "person_id": "A000001",
        "source": "worksInTripitaka",
        "text": "無經號條目",
    }]


def test_modes_make_reference_and_era_rules_explicit(tmp_path):
    source_db, _ = build_fixture(tmp_path, "source.db", "source-faithful")
    legacy_db, manifest = build_fixture(tmp_path, "legacy.db", "legacy-compatible")
    db = sqlite3.connect(legacy_db)
    refs = json.loads(db.execute(
        "SELECT cbeta_refs FROM persons WHERE person_id='A000001'"
    ).fetchone()[0])
    assert refs == ["( CBETA T01n0001_p0001a01 ) 測試經"]
    place_refs = json.loads(db.execute(
        "SELECT cbeta_refs FROM places WHERE place_id='PL000000000001'"
    ).fetchone()[0])
    assert place_refs[-1] == "嵌套地點書目"
    assert db.execute("SELECT count(*) FROM eras").fetchone()[0] == 3
    assert db.execute("SELECT count(*) FROM eras WHERE era_id=2").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM eras WHERE era_id=4").fetchone()[0] == 0
    db.close()
    assert manifest["mode"] == "legacy-compatible"
    report = compare_databases(legacy_db, source_db)
    assert report["tables"]["persons"]["field_stats"]["cbeta_refs"]["changed_common_rows"] == 1


def test_time_standard_proleptic_and_no_month_audit():
    _, source_eras, source_audit = parse_time_sql(FIXTURES / "time.sql", mode="source-faithful")
    assert {row[0] for row in source_eras} == {1, 3, 4}
    assert source_audit["only_proleptic_skipped"] == [{"era_id": 2, "month_count": 1}]
    assert source_audit["no_month"] == [3]
    _, legacy_eras, legacy_audit = parse_time_sql(FIXTURES / "time.sql", mode="legacy-compatible")
    assert {row[0] for row in legacy_eras} == {1, 2, 3}
    assert legacy_audit["legacy_collapses"][0]["member_era_ids"] == [1, 4]


def test_output_is_deterministic_and_existing_paths_are_refused(tmp_path):
    first, _ = build_fixture(tmp_path, "first.db")
    second, _ = build_fixture(tmp_path, "second.db")
    assert file_hash(first) == file_hash(second)
    with pytest.raises(BuildError, match="Refusing to overwrite"):
        build_lineage_database(
            person_xml=FIXTURES / "person.xml",
            place_xml=FIXTURES / "place.xml",
            time_sql=FIXTURES / "time.sql",
            output=first,
        )
    same_path = tmp_path / "same.db"
    with pytest.raises(BuildError, match="must be distinct"):
        build_lineage_database(
            person_xml=FIXTURES / "person.xml",
            place_xml=FIXTURES / "place.xml",
            time_sql=FIXTURES / "time.sql",
            output=same_path,
            manifest_path=same_path,
        )


def test_checksum_manifest_is_verified(tmp_path):
    checksum_file = tmp_path / "SHA256SUMS.txt"
    checksum_file.write_text("\n".join(
        f"{file_hash(FIXTURES / name)}  {name}"
        for name in ("person.xml", "place.xml", "time.sql")
    ) + "\n", encoding="utf-8")
    _, manifest = build_fixture(tmp_path, checksum_manifest=checksum_file)
    assert manifest["checksum_manifest"]["sha256"] == file_hash(checksum_file)


def test_auditable_edge_override(tmp_path):
    override = tmp_path / "overrides.json"
    override.write_text(json.dumps({
        "format_version": 1,
        "expected_source_sha256": {
            "person_xml": file_hash(FIXTURES / "person.xml"),
        },
        "overrides": [
            {
                "action": "upsert",
                "source_id": "A000002",
                "target_id": "A000001",
                "description": "明示兼容描述",
                "cbeta_ref": None,
                "reason": "fixture compatibility test",
            },
            {
                "action": "remove",
                "source_id": "A000001",
                "target_id": "A999999",
                "reason": "fixture dangling-edge removal test",
            },
        ],
    }, ensure_ascii=False), encoding="utf-8")
    output, manifest = build_fixture(tmp_path, edge_overrides=override)
    db = sqlite3.connect(output)
    assert db.execute(
        "SELECT description FROM edges WHERE source_id='A000002' AND target_id='A000001'"
    ).fetchone()[0] == "明示兼容描述"
    db.close()
    audit = json.loads(output.with_suffix(".audit.json").read_text(encoding="utf-8"))
    assert audit["edge_overrides"]["applied"][0]["before"][3].startswith("教師聲明")
    assert audit["edge_overrides"]["applied"][1]["missing_person_endpoints"] == ["A999999"]
    assert manifest["edge_overrides"]["sha256"] == file_hash(override)
