#!/usr/bin/env python3
"""Deterministically build lineage.db from DILA person/place/time sources."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


BUILDER_VERSION = "1.0.0"
SCHEMA_VERSION = 1
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
PERSON_ID_RE = re.compile(r"A\d{6}\Z")
SCRIPTURE_ID_RE = re.compile(
    r"[A-Z][A-Za-z]{0,2}\d{3,4}(?:[A-Za-z]|\.\d{1,2})?\Z"
)
SIGNED_YEAR_RE = re.compile(r"(?<!\d)([+-])(\d{4,})(?!\d)")
CBETA_BIBL_RE = re.compile(
    r"\(\s*CBETA\s+(?P<canon>[A-Z]+)\d+n(?P<number>[A-Za-z]?\d+[a-z]?)"
    r"_p[^)]*\)\s*(?P<title>.*)",
    re.DOTALL,
)
WORK_RE = re.compile(
    r"(?P<title>.+)\((?P<work>[A-Za-z][A-Za-z0-9.]+)\)\s*\Z"
)
MYSQL_INSERT_RE = re.compile(r"INSERT INTO `(?P<table>[^`]+)` VALUES (?P<values>.*);\s*\Z")

TABLE_SPECS = {
    "dynasties": {
        "pk": ("dynasty_id",),
        "columns": ("dynasty_id", "name_zh", "name_en", "type"),
    },
    "eras": {
        "pk": ("era_id",),
        "columns": (
            "era_id", "dynasty_id", "emperor_id", "name_zh", "name_en",
            "start_year", "end_year",
        ),
    },
    "persons": {
        "pk": ("person_id",),
        "columns": (
            "person_id", "name", "aliases", "birth_year", "death_year",
            "dynasty", "sect", "gender", "is_monk", "bio_concise",
            "bio_extensive", "cbeta_refs", "works", "place_origin",
        ),
    },
    "places": {
        "pk": ("place_id",),
        "columns": (
            "place_id", "name_zh", "name_en", "name_ja", "latitude",
            "longitude", "district", "category", "note", "cbeta_refs",
        ),
    },
    "edges": {
        "pk": ("source_id", "target_id"),
        "columns": ("source_id", "target_id", "edge_type", "description", "cbeta_ref"),
    },
    "person_scriptures": {
        "pk": ("person_id", "scripture_id", "relation"),
        "columns": ("person_id", "scripture_id", "relation", "source_text", "url"),
    },
}

EXPECTED_INDEXES = {
    "idx_edges_source",
    "idx_edges_target",
    "idx_edges_type",
    "idx_eras_dynasty",
    "idx_persons_dynasty",
    "idx_persons_sect",
    "idx_places_category",
    "idx_ps_person",
    "idx_ps_scripture",
}


class BuildError(RuntimeError):
    """A user-facing build validation failure."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if _local_name(child.tag) == name]


def _element_text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = "".join(element.itertext()).strip()
    return value or None


def _direct_text(element: ET.Element | None) -> str | None:
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _json_list(values: list[str]) -> str | None:
    return json.dumps(values, ensure_ascii=False) if values else None


def _first_signed_year(element: ET.Element | None) -> int | None:
    text = _element_text(element)
    if not text:
        return None
    match = SIGNED_YEAR_RE.search(text)
    if not match:
        return None
    value = int(match.group(2))
    return -value if match.group(1) == "-" else value


def _last_note(notes: dict[str | None, list[ET.Element]], note_type: str) -> str | None:
    values = notes.get(note_type, [])
    return _element_text(values[-1]) if values else None


def _bibliography_values(record: ET.Element, *, complete: bool) -> list[str]:
    values: list[str] = []
    for list_bibl in _direct_children(record, "listBibl"):
        for bibl in _direct_children(list_bibl, "bibl"):
            value = _element_text(bibl) if complete else _direct_text(bibl)
            if value:
                values.append(value)
    return values


def _parse_bibl_scripture(text: str) -> tuple[str, str] | None:
    match = CBETA_BIBL_RE.search(text)
    if not match:
        return None
    scripture_id = match.group("canon") + match.group("number")
    if not SCRIPTURE_ID_RE.fullmatch(scripture_id):
        return None
    return scripture_id, match.group("title").strip()


def _parse_work_scriptures(text: str | None) -> tuple[list[tuple[str, str]], list[str]]:
    if not text:
        return [], []
    records: list[tuple[str, str]] = []
    invalid: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = WORK_RE.fullmatch(stripped)
        if match is None:
            invalid.append(stripped)
            continue
        scripture_id = match.group("work")
        if SCRIPTURE_ID_RE.fullmatch(scripture_id):
            records.append((scripture_id, match.group("title").strip()))
        else:
            invalid.append(stripped)
    return records, invalid


def _relation_candidate(
    person_id: str,
    relation: ET.Element,
    ordinal: int,
) -> dict[str, Any] | None:
    relation_type = relation.get("type")
    active = (relation.get("active") or "").strip()
    if relation_type not in {"teacher", "student"}:
        return None
    if relation_type == "teacher":
        source_id, target_id = active, person_id
    else:
        source_id, target_id = person_id, active

    desc = next(iter(_direct_children(relation, "desc")), None)
    description = _element_text(desc)
    cbeta_ref = None
    if desc is not None:
        for ref in desc.iter():
            if _local_name(ref.tag) == "ref" and ref.get("type") == "url":
                cbeta_ref = _element_text(ref) or ref.get("target")
                if cbeta_ref:
                    break
    return {
        "source_id": source_id,
        "target_id": target_id,
        "edge_type": "teacher",
        "description": description,
        "cbeta_ref": cbeta_ref,
        "declaration": relation_type,
        "declared_on": person_id,
        "ordinal": ordinal,
    }


def parse_person_xml(path: Path, *, complete_refs: bool) -> tuple[list[tuple[Any, ...]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    persons: list[tuple[Any, ...]] = []
    edge_candidates: list[dict[str, Any]] = []
    scripture_candidates: list[dict[str, Any]] = []
    audit: dict[str, Any] = {
        "unknown_monk_values": [],
        "missing_primary_names": [],
        "invalid_scripture_references": [],
    }
    ordinal = 0
    stack: list[ET.Element] = []

    for event, element in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            stack.append(element)
            continue

        parent_name = _local_name(stack[-2].tag) if len(stack) >= 2 else None
        if _local_name(element.tag) == "person" and parent_name == "listPerson":
            person_id = element.get(XML_ID)
            if not person_id or not PERSON_ID_RE.fullmatch(person_id):
                raise BuildError(f"Invalid or missing person xml:id: {person_id!r}")

            person_names = _direct_children(element, "persName")
            primary_names = [item for item in person_names if item.get("type") != "alternative"]
            name = _element_text(primary_names[0]) if primary_names else None
            if not name:
                name = f"Person_{person_id}"
                audit["missing_primary_names"].append(person_id)

            aliases = [
                value
                for item in person_names
                if item.get("type") == "alternative"
                for value in [_element_text(item)]
                if value
            ]
            notes: dict[str | None, list[ET.Element]] = defaultdict(list)
            for note in _direct_children(element, "note"):
                notes[note.get("type")].append(note)

            dynasty = _last_note(notes, "dynasty")
            if dynasty is not None:
                dynasty = dynasty.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "/")
            monk_text = _last_note(notes, "monk")
            normalized_monk = re.sub(r"\s+", "", monk_text or "")
            if normalized_monk in {"是", "1", "true", "True"}:
                is_monk = 1
            elif normalized_monk in {"否", "0", "false", "False", ""}:
                is_monk = 0
            else:
                is_monk = 0
                audit["unknown_monk_values"].append({"person_id": person_id, "value": monk_text})

            sex = next(iter(_direct_children(element, "sex")), None)
            gender = None
            if sex is not None and sex.get("value"):
                try:
                    parsed_gender = int(sex.get("value", ""))
                    gender = parsed_gender if parsed_gender != 0 else None
                except ValueError:
                    gender = None

            refs = _bibliography_values(element, complete=complete_refs)
            works = _last_note(notes, "worksInTripitaka")
            persons.append((
                person_id,
                name,
                _json_list(aliases),
                _first_signed_year(next(iter(_direct_children(element, "birth")), None)),
                _first_signed_year(next(iter(_direct_children(element, "death")), None)),
                dynasty,
                _last_note(notes, "sect"),
                gender,
                is_monk,
                _last_note(notes, "concise"),
                _last_note(notes, "extensive"),
                _json_list(refs),
                works,
                _last_note(notes, "placeOfOrigin"),
            ))

            for list_relation in _direct_children(element, "listRelation"):
                for relation in _direct_children(list_relation, "relation"):
                    ordinal += 1
                    candidate = _relation_candidate(person_id, relation, ordinal)
                    if candidate:
                        edge_candidates.append(candidate)

            for bibl_text in refs:
                parsed = _parse_bibl_scripture(bibl_text)
                if parsed:
                    scripture_id, source_text = parsed
                    scripture_candidates.append({
                        "person_id": person_id,
                        "scripture_id": scripture_id,
                        "relation": "mentioned",
                        "source_text": source_text,
                        "url": None,
                        "ordinal": len(scripture_candidates),
                    })
                elif "CBETA" in bibl_text:
                    audit["invalid_scripture_references"].append({
                        "person_id": person_id,
                        "source": "listBibl",
                        "text": bibl_text,
                    })

            parsed_works, invalid_works = _parse_work_scriptures(works)
            for invalid_work in invalid_works:
                audit["invalid_scripture_references"].append({
                    "person_id": person_id,
                    "source": "worksInTripitaka",
                    "text": invalid_work,
                })
            for scripture_id, title in parsed_works:
                scripture_candidates.append({
                    "person_id": person_id,
                    "scripture_id": scripture_id,
                    "relation": "authored",
                    "source_text": title,
                    "url": f"https://cbetaonline.dila.edu.tw/{scripture_id}",
                    "ordinal": len(scripture_candidates),
                })

            element.clear()
        stack.pop()

    return persons, edge_candidates, scripture_candidates, audit


def _deduplicate_edges(
    candidates: list[dict[str, Any]],
    person_ids: set[str],
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    invalid: list[dict[str, Any]] = []
    dangling: list[dict[str, Any]] = []
    for candidate in candidates:
        source_id = candidate["source_id"]
        target_id = candidate["target_id"]
        if not PERSON_ID_RE.fullmatch(source_id) or not PERSON_ID_RE.fullmatch(target_id):
            invalid.append(candidate)
            continue
        if source_id not in person_ids or target_id not in person_ids:
            dangling.append(candidate)
        grouped[(source_id, target_id)].append(candidate)

    rows: list[tuple[Any, ...]] = []
    conflicts: list[dict[str, Any]] = []
    duplicate_candidates = 0
    for key in sorted(grouped):
        values = grouped[key]
        duplicate_candidates += max(0, len(values) - 1)
        values.sort(key=lambda item: (
            0 if item["declaration"] == "teacher" else 1,
            0 if item.get("cbeta_ref") else 1,
            -len(item.get("description") or ""),
            item["ordinal"],
        ))
        selected = values[0]
        rows.append((
            selected["source_id"], selected["target_id"], "teacher",
            selected.get("description"), selected.get("cbeta_ref"),
        ))
        distinct = {
            (item.get("description"), item.get("cbeta_ref"))
            for item in values
        }
        if len(distinct) > 1:
            conflicts.append({
                "key": list(key),
                "rule": "teacher declaration, then URL, then longer description, then source order",
                "selected": selected,
                "discarded": values[1:],
            })
    return rows, {
        "candidate_count": len(candidates),
        "duplicate_candidate_count": duplicate_candidates,
        "conflicts": conflicts,
        "invalid": invalid,
        "dangling": dangling,
    }


def _deduplicate_scriptures(candidates: list[dict[str, Any]]) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[(candidate["person_id"], candidate["scripture_id"], candidate["relation"])].append(candidate)
    rows: list[tuple[Any, ...]] = []
    conflicts: list[dict[str, Any]] = []
    duplicate_candidates = 0
    for key in sorted(grouped):
        values = sorted(grouped[key], key=lambda item: item["ordinal"])
        duplicate_candidates += max(0, len(values) - 1)
        selected = values[0]
        rows.append((*key, selected.get("source_text"), selected.get("url")))
        distinct = {(item.get("source_text"), item.get("url")) for item in values}
        if len(distinct) > 1:
            conflicts.append({"key": list(key), "selected": selected, "discarded": values[1:]})
    return rows, {
        "candidate_count": len(candidates),
        "duplicate_candidate_count": duplicate_candidates,
        "conflicts": conflicts,
    }


def parse_place_xml(path: Path, *, complete_refs: bool) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    places: list[tuple[Any, ...]] = []
    audit: dict[str, Any] = {"missing_chinese_names": [], "invalid_geo": []}
    stack: list[ET.Element] = []
    for event, element in ET.iterparse(path, events=("start", "end")):
        if event == "start":
            stack.append(element)
            continue

        parent_name = _local_name(stack[-2].tag) if len(stack) >= 2 else None
        if _local_name(element.tag) == "place" and parent_name == "listPlace":
            place_id = element.get(XML_ID)
            if not place_id:
                element.clear()
                stack.pop()
                continue
            names: dict[str, list[str]] = defaultdict(list)
            all_names: list[str] = []
            non_english_names: list[str] = []
            for place_name in _direct_children(element, "placeName"):
                value = _element_text(place_name)
                if value:
                    language = (place_name.get(XML_LANG) or "").split("-", 1)[0]
                    names[language].append(value)
                    all_names.append(value)
                    if language != "eng":
                        non_english_names.append(value)
            name_zh = names["zho"][-1] if names["zho"] else None
            if not name_zh:
                audit["missing_chinese_names"].append(place_id)
                name_zh = (
                    non_english_names[0]
                    if non_english_names
                    else (all_names[-1] if all_names else f"Place_{place_id}")
                )

            longitude = latitude = None
            geo = next((item for item in element.iter() if _local_name(item.tag) == "geo"), None)
            geo_text = _element_text(geo)
            if geo_text:
                parts = geo_text.split()
                if len(parts) == 2:
                    try:
                        longitude, latitude = float(parts[0]), float(parts[1])
                    except ValueError:
                        audit["invalid_geo"].append({"place_id": place_id, "value": geo_text})
                else:
                    audit["invalid_geo"].append({"place_id": place_id, "value": geo_text})

            direct_notes = _direct_children(element, "note")
            untyped_notes = [item for item in direct_notes if item.get("type") is None]
            category_notes = [item for item in direct_notes if item.get("type") == "category"]
            district = next(iter(_direct_children(element, "district")), None)
            places.append((
                place_id,
                name_zh,
                names["eng"][-1] if names["eng"] else None,
                names["jpn"][-1] if names["jpn"] else None,
                latitude,
                longitude,
                (
                    district.text.strip()
                    if district is not None and district.text is not None
                    else ("" if district is not None else None)
                ),
                _element_text(category_notes[-1]) if category_notes else None,
                _element_text(untyped_notes[-1]) if untyped_notes else None,
                _json_list(_bibliography_values(element, complete=complete_refs)),
            ))
            element.clear()
        stack.pop()
    return places, audit


def parse_mysql_inserts(path: Path, wanted_tables: set[str]) -> dict[str, list[tuple[Any, ...]]]:
    tables: dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.startswith("INSERT INTO "):
                continue
            match = MYSQL_INSERT_RE.match(line)
            if not match or match.group("table") not in wanted_tables:
                continue
            try:
                rows = ast.literal_eval("[" + match.group("values") + "]")
            except (SyntaxError, ValueError) as exc:
                raise BuildError(f"Cannot parse MySQL INSERT at line {line_number}: {exc}") from exc
            tables[match.group("table")].extend(rows)
    missing = wanted_tables - tables.keys()
    if missing:
        raise BuildError(f"Missing required MySQL INSERT tables: {', '.join(sorted(missing))}")
    return tables


def julian_day_to_gregorian_year(julian_day: int) -> int:
    """Return the astronomical proleptic-Gregorian year for an integer JDN."""
    a = julian_day + 32044
    b = (4 * a + 3) // 146097
    c = a - (146097 * b) // 4
    d = (4 * c + 3) // 1461
    e = c - (1461 * d) // 4
    m = (5 * e + 2) // 153
    return 100 * b + d - 4800 + m // 10


def _last_language_name(
    rows: Iterable[tuple[Any, ...]],
    entity_id: int,
    language_id: int,
) -> str | None:
    values = [row[1] for row in rows if row[0] == entity_id and row[3] == language_id]
    return values[-1] if values else None


def parse_time_sql(path: Path, *, mode: str) -> tuple[list[tuple[Any, ...]], list[tuple[Any, ...]], dict[str, Any]]:
    wanted = {
        "c_languages", "t_dynasty", "t_dynasty_names", "t_emperor",
        "t_era", "t_era_names", "t_month",
    }
    tables = parse_mysql_inserts(path, wanted)
    language_codes = {row[0]: str(row[1]).lower() for row in tables["c_languages"]}
    english_ids = {key for key, code in language_codes.items() if code.startswith("eng")}
    english_id = min(english_ids) if english_ids else -1

    dynasties: list[tuple[Any, ...]] = []
    dynasty_names = tables["t_dynasty_names"]
    for dynasty_id, dynasty_type in tables["t_dynasty"]:
        dynasties.append((
            dynasty_id,
            _last_language_name(dynasty_names, dynasty_id, 1) or f"Dynasty_{dynasty_id}",
            _last_language_name(dynasty_names, dynasty_id, english_id),
            dynasty_type,
        ))

    emperor_dynasties = dict(tables["t_emperor"])
    era_emperors = dict(tables["t_era"])
    era_names = tables["t_era_names"]
    months_by_era: dict[int, list[tuple[Any, ...]]] = defaultdict(list)
    for month in tables["t_month"]:
        months_by_era[month[5]].append(month)

    names_zh = {
        era_id: _last_language_name(era_names, era_id, 1) or f"Era_{era_id}"
        for era_id in era_emperors
    }
    names_en = {
        era_id: _last_language_name(era_names, era_id, english_id)
        for era_id in era_emperors
    }
    audit: dict[str, Any] = {
        "source_era_count": len(tables["t_era"]),
        "source_month_count": len(tables["t_month"]),
        "no_month": [],
        "only_proleptic_skipped": [],
        "legacy_collapses": [],
    }

    era_groups: list[tuple[int, list[int]]]
    if mode == "legacy-compatible":
        grouped: dict[tuple[int, str], list[int]] = defaultdict(list)
        era_groups = []
        for era_id, emperor_id in tables["t_era"]:
            if not months_by_era.get(era_id):
                era_groups.append((era_id, [era_id]))
                audit["no_month"].append(era_id)
            else:
                dynasty_id = emperor_dynasties[emperor_id]
                grouped[(dynasty_id, names_zh[era_id])].append(era_id)
        for key in sorted(grouped):
            members = sorted(grouped[key])
            canonical = members[0]
            era_groups.append((canonical, members))
            if len(members) > 1:
                audit["legacy_collapses"].append({
                    "dynasty_id": key[0], "name_zh": key[1],
                    "canonical_era_id": canonical, "member_era_ids": members,
                })
    else:
        era_groups = [(era_id, [era_id]) for era_id, _ in tables["t_era"]]

    eras: list[tuple[Any, ...]] = []
    for canonical_id, member_ids in era_groups:
        emperor_id = era_emperors[canonical_id]
        dynasty_id = emperor_dynasties[emperor_id]
        all_months = [month for era_id in member_ids for month in months_by_era.get(era_id, [])]
        if mode == "source-faithful":
            selected_months = [month for month in all_months if month[10] == "S"]
            if all_months and not selected_months:
                audit["only_proleptic_skipped"].append({
                    "era_id": canonical_id,
                    "month_count": len(all_months),
                })
                continue
        else:
            selected_months = all_months

        if not all_months and canonical_id not in audit["no_month"]:
            audit["no_month"].append(canonical_id)
        start_year = min(
            (julian_day_to_gregorian_year(month[6] + month[9] - 1) for month in selected_months),
            default=None,
        )
        end_year = max(
            (julian_day_to_gregorian_year(month[7]) for month in selected_months),
            default=None,
        )
        eras.append((
            canonical_id, dynasty_id, emperor_id, names_zh[canonical_id],
            names_en[canonical_id], start_year, end_year,
        ))

    audit["output_era_count"] = len(eras)
    audit["standard_month_rule"] = (
        "source-faithful keeps S months, uses first + start_from - 1 through last, "
        "and excludes P-only eras; legacy-compatible includes S and P months"
    )
    return dynasties, eras, audit


def apply_edge_overrides(
    rows: list[tuple[Any, ...]],
    override_path: Path,
    source_hashes: dict[str, str],
    person_ids: set[str],
) -> tuple[list[tuple[Any, ...]], dict[str, Any]]:
    payload = json.loads(override_path.read_text(encoding="utf-8"))
    if payload.get("format_version") != 1:
        raise BuildError("Edge override format_version must be 1")
    expected_hashes = payload.get("expected_source_sha256", {})
    if "person_xml" not in expected_hashes:
        raise BuildError("Edge overrides must pin expected_source_sha256.person_xml")
    for source_name, expected in expected_hashes.items():
        actual = source_hashes.get(source_name)
        if actual != expected:
            raise BuildError(
                f"Edge overrides expect {source_name} SHA-256 {expected}, got {actual}"
            )
    indexed = {(row[0], row[1]): row for row in rows}
    applied: list[dict[str, Any]] = []
    for item in payload.get("overrides", []):
        reason = item.get("reason")
        if not reason:
            raise BuildError("Every edge override requires a non-empty reason")
        source_id, target_id = item.get("source_id"), item.get("target_id")
        if not isinstance(source_id, str) or not PERSON_ID_RE.fullmatch(source_id):
            raise BuildError(f"Edge override has invalid source_id: {source_id!r}")
        if not isinstance(target_id, str) or not PERSON_ID_RE.fullmatch(target_id):
            raise BuildError(f"Edge override has invalid target_id: {target_id!r}")
        action = item.get("action", "upsert")
        key = (source_id, target_id)
        before = indexed.get(key)
        if action == "remove":
            indexed.pop(key, None)
            after = None
        elif action == "upsert":
            after = (
                source_id, target_id, item.get("edge_type", "teacher"),
                item.get("description"), item.get("cbeta_ref"),
            )
            indexed[key] = after
        else:
            raise BuildError(f"Unsupported edge override action: {action!r}")
        applied.append({
            "override": item,
            "before": before,
            "after": after,
            "missing_person_endpoints": [
                person_id
                for person_id in (source_id, target_id)
                if person_id not in person_ids
            ],
        })
    return [indexed[key] for key in sorted(indexed)], {
        "path": str(override_path.resolve()),
        "sha256": sha256_file(override_path),
        "applied": applied,
    }


def _insert_rows(connection: sqlite3.Connection, table: str, rows: list[tuple[Any, ...]]) -> None:
    columns = TABLE_SPECS[table]["columns"]
    placeholders = ",".join("?" for _ in columns)
    column_sql = ",".join(columns)
    connection.executemany(
        f"INSERT INTO {table} ({column_sql}) VALUES ({placeholders})",
        rows,
    )


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def compare_databases(baseline: Path, candidate: Path) -> dict[str, Any]:
    report: dict[str, Any] = {
        "format_version": 1,
        "baseline": {"path": str(baseline.resolve()), "sha256": sha256_file(baseline)},
        "candidate": {"path": str(candidate.resolve()), "sha256": sha256_file(candidate)},
        "tables": {},
    }
    old_db = _read_only_connection(baseline)
    new_db = _read_only_connection(candidate)
    try:
        for table, spec in TABLE_SPECS.items():
            columns = spec["columns"]
            pk_columns = spec["pk"]

            def load(db: sqlite3.Connection) -> dict[tuple[Any, ...], dict[str, Any]]:
                result: dict[tuple[Any, ...], dict[str, Any]] = {}
                for row in db.execute(f"SELECT {','.join(columns)} FROM {table}"):
                    record = dict(row)
                    result[tuple(record[name] for name in pk_columns)] = record
                return result

            old_rows, new_rows = load(old_db), load(new_db)
            old_keys, new_keys = set(old_rows), set(new_rows)
            added_keys = sorted(new_keys - old_keys)
            removed_keys = sorted(old_keys - new_keys)
            changed_rows: list[dict[str, Any]] = []
            field_stats: dict[str, dict[str, int]] = {}
            for column in columns:
                field_stats[column] = {
                    "changed_common_rows": 0,
                    "baseline_non_null": sum(old_rows[key][column] is not None for key in old_rows),
                    "candidate_non_null": sum(new_rows[key][column] is not None for key in new_rows),
                }
            for key in sorted(old_keys & new_keys):
                fields: dict[str, dict[str, Any]] = {}
                for column in columns:
                    old_value, new_value = old_rows[key][column], new_rows[key][column]
                    if old_value != new_value:
                        fields[column] = {"baseline": old_value, "candidate": new_value}
                        field_stats[column]["changed_common_rows"] += 1
                if fields:
                    changed_rows.append({"key": list(key), "fields": fields})
            report["tables"][table] = {
                "primary_key": list(pk_columns),
                "baseline_count": len(old_rows),
                "candidate_count": len(new_rows),
                "common_count": len(old_keys & new_keys),
                "added_count": len(added_keys),
                "removed_count": len(removed_keys),
                "changed_row_count": len(changed_rows),
                "field_stats": field_stats,
                "added": [{"key": list(key), "row": new_rows[key]} for key in added_keys],
                "removed": [{"key": list(key), "row": old_rows[key]} for key in removed_keys],
                "changed": changed_rows,
            }
    finally:
        old_db.close()
        new_db.close()
    return report


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.link(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _verify_checksum_manifest(manifest: Path, sources: dict[str, Path], hashes: dict[str, str]) -> None:
    expected_by_basename: dict[str, set[str]] = defaultdict(set)
    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = re.match(r"([0-9a-fA-F]{64})\s+\*?(.*)\Z", line)
        if not match:
            raise BuildError(f"Invalid SHA256SUMS line: {raw_line!r}")
        expected_by_basename[Path(match.group(2)).name].add(match.group(1).lower())
    for source_name, path in sources.items():
        candidates = expected_by_basename.get(path.name, set())
        if not candidates:
            raise BuildError(f"Checksum manifest has no entry for {path.name}")
        if hashes[source_name] not in candidates:
            raise BuildError(
                f"SHA-256 mismatch for {path}: expected one of {sorted(candidates)}, "
                f"got {hashes[source_name]}"
            )


def build_lineage_database(
    *,
    person_xml: Path,
    place_xml: Path,
    time_sql: Path,
    output: Path,
    mode: str = "source-faithful",
    schema_path: Path | None = None,
    manifest_path: Path | None = None,
    audit_path: Path | None = None,
    checksum_manifest: Path | None = None,
    edge_overrides: Path | None = None,
    compare_to: Path | None = None,
    diff_path: Path | None = None,
) -> dict[str, Any]:
    schema_path = schema_path or Path(__file__).with_name("schema.sql")
    manifest_path = manifest_path or output.with_suffix(".manifest.json")
    audit_path = audit_path or output.with_suffix(".audit.json")
    if compare_to is not None:
        diff_path = diff_path or output.with_suffix(".diff.json")
    elif diff_path is not None:
        raise BuildError("--diff-report requires --compare-to")

    inputs = {
        "person_xml": person_xml,
        "place_xml": place_xml,
        "time_sql": time_sql,
    }
    required_paths = {**inputs, "schema": schema_path}
    if checksum_manifest:
        required_paths["checksum_manifest"] = checksum_manifest
    if edge_overrides:
        required_paths["edge_overrides"] = edge_overrides
    if compare_to:
        required_paths["compare_to"] = compare_to
    for label, path in required_paths.items():
        if not path.is_file():
            raise BuildError(f"{label} does not exist or is not a file: {path}")
    for path in [output, manifest_path, audit_path, diff_path]:
        if path is not None and path.exists():
            raise BuildError(f"Refusing to overwrite existing path: {path}")
    destinations = [output, manifest_path, audit_path]
    if diff_path is not None:
        destinations.append(diff_path)
    resolved_destinations = [path.resolve(strict=False) for path in destinations]
    if len(set(resolved_destinations)) != len(resolved_destinations):
        raise BuildError("Output, manifest, audit, and diff paths must be distinct")
    if mode not in {"source-faithful", "legacy-compatible"}:
        raise BuildError(f"Unsupported mode: {mode}")

    source_hashes = {name: sha256_file(path) for name, path in inputs.items()}
    if checksum_manifest:
        _verify_checksum_manifest(checksum_manifest, inputs, source_hashes)

    complete_refs = mode == "source-faithful"
    persons, edge_candidates, scripture_candidates, person_audit = parse_person_xml(
        person_xml, complete_refs=complete_refs
    )
    person_ids = {row[0] for row in persons}
    edges, edge_audit = _deduplicate_edges(edge_candidates, person_ids)
    scriptures, scripture_audit = _deduplicate_scriptures(scripture_candidates)
    # The existing database already preserved nested place bibliography text;
    # the compatibility split is needed only for person bibliographies.
    places, place_audit = parse_place_xml(place_xml, complete_refs=True)
    dynasties, eras, time_audit = parse_time_sql(time_sql, mode=mode)

    override_audit = None
    if edge_overrides:
        edges, override_audit = apply_edge_overrides(
            edges, edge_overrides, source_hashes, person_ids
        )

    table_rows = {
        "dynasties": sorted(dynasties, key=lambda row: row[0]),
        "eras": sorted(eras, key=lambda row: row[0]),
        "persons": sorted(persons, key=lambda row: row[0]),
        "places": sorted(places, key=lambda row: row[0]),
        "edges": sorted(edges, key=lambda row: (row[0], row[1])),
        "person_scriptures": sorted(scriptures, key=lambda row: (row[0], row[1], row[2])),
    }
    audit = {
        "format_version": 1,
        "mode": mode,
        "persons": person_audit,
        "places": place_audit,
        "time": time_audit,
        "edges": edge_audit,
        "person_scriptures": scripture_audit,
        "edge_overrides": override_audit,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(file_descriptor)
    temp_path = Path(temp_name)
    temp_path.unlink()
    try:
        connection = sqlite3.connect(temp_path)
        try:
            connection.executescript(schema_path.read_text(encoding="utf-8"))
            for table in TABLE_SPECS:
                _insert_rows(connection, table, table_rows[table])
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
            indexes = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
                )
            }
            missing_indexes = sorted(EXPECTED_INDEXES - indexes)
            if integrity != "ok":
                raise BuildError(f"SQLite integrity_check failed: {integrity}")
            if foreign_key_issues:
                raise BuildError(f"SQLite foreign_key_check failed: {foreign_key_issues[:5]}")
            if missing_indexes:
                raise BuildError(f"Missing required indexes: {', '.join(missing_indexes)}")
            connection.execute("VACUUM")
        finally:
            connection.close()
        # Hard-link publication is atomic and fails if a concurrent process has
        # created the requested target since the initial refusal check.
        os.link(temp_path, output)
        temp_path.unlink()
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    delivered_paths = [output]
    try:
        comparison = compare_databases(compare_to, output) if compare_to else None
        if diff_path is not None and comparison is not None:
            _write_json(diff_path, comparison)
            delivered_paths.append(diff_path)
        _write_json(audit_path, audit)
        delivered_paths.append(audit_path)

        output_hash = sha256_file(output)
        manifest = {
            "format_version": 1,
            "builder": {
                "version": BUILDER_VERSION,
                "schema_version": SCHEMA_VERSION,
                "script_sha256": sha256_file(Path(__file__)),
                "schema_sha256": sha256_file(schema_path),
                "python": sys.version.split()[0],
                "sqlite": sqlite3.sqlite_version,
            },
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "sources": {
                name: {
                    "path": str(path.resolve()),
                    "size": path.stat().st_size,
                    "sha256": source_hashes[name],
                }
                for name, path in inputs.items()
            },
            "checksum_manifest": (
                {
                    "path": str(checksum_manifest.resolve()),
                    "sha256": sha256_file(checksum_manifest),
                }
                if checksum_manifest else None
            ),
            "rules": {
                "cbeta_refs": (
                    "complete listBibl itertext"
                    if complete_refs else "direct bibl text only"
                ),
                "is_monk": (
                    "TEI note[@type='monk'] explicit value; "
                    "unknown values audited and set to 0"
                ),
                "years": "first signed TEI year, preserving BCE sign",
                "edges": (
                    "retain syntactically valid TEI teacher/student declarations including "
                    "dangling endpoints; deduplicate by teacher declaration, URL, longer "
                    "description, then source order"
                ),
                "person_scriptures": (
                    "complete line-oriented worksInTripitaka grammar, including mixed-case "
                    "series, uppercase suffixes, and dotted subnumbers; invalid lines are audited"
                ),
                "places": (
                    "top-level place with xml:id; last same base-language name; "
                    "geo longitude/latitude reversed"
                ),
                "eras": time_audit["standard_month_rule"],
            },
            "counts": {table: len(rows) for table, rows in table_rows.items()},
            "validation": {
                "integrity_check": "ok",
                "foreign_key_check_issue_count": 0,
                "required_indexes": sorted(EXPECTED_INDEXES),
                "missing_indexes": [],
            },
            "output": {
                "path": str(output.resolve()),
                "size": output.stat().st_size,
                "sha256": output_hash,
            },
            "audit_report": {
                "path": str(audit_path.resolve()),
                "sha256": sha256_file(audit_path),
            },
            "edge_overrides": (
                {
                    "path": str(edge_overrides.resolve()),
                    "sha256": sha256_file(edge_overrides),
                }
                if edge_overrides else None
            ),
            "comparison_report": (
                {"path": str(diff_path.resolve()), "sha256": sha256_file(diff_path)}
                if diff_path else None
            ),
        }
        _write_json(manifest_path, manifest)
        delivered_paths.append(manifest_path)
        return manifest
    except Exception:
        for delivered_path in reversed(delivered_paths):
            delivered_path.unlink(missing_ok=True)
        raise


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build lineage.db from DILA authority person/place/time sources."
    )
    parser.add_argument("--person-xml", type=Path, required=True)
    parser.add_argument("--place-xml", type=Path, required=True)
    parser.add_argument("--time-sql", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("source-faithful", "legacy-compatible"),
        default="source-faithful",
    )
    parser.add_argument("--schema", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--checksum-manifest", type=Path)
    parser.add_argument("--edge-overrides", type=Path)
    parser.add_argument("--compare-to", type=Path)
    parser.add_argument("--diff-report", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    try:
        manifest = build_lineage_database(
            person_xml=args.person_xml,
            place_xml=args.place_xml,
            time_sql=args.time_sql,
            output=args.output,
            mode=args.mode,
            schema_path=args.schema,
            manifest_path=args.manifest,
            audit_path=args.audit_report,
            checksum_manifest=args.checksum_manifest,
            edge_overrides=args.edge_overrides,
            compare_to=args.compare_to,
            diff_path=args.diff_report,
        )
    except (BuildError, OSError, sqlite3.Error, ET.ParseError, json.JSONDecodeError) as exc:
        print(f"lineage builder error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "output": manifest["output"],
        "counts": manifest["counts"],
        "mode": manifest["mode"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
