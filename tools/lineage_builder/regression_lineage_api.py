#!/usr/bin/env python3
"""Run every lineage API endpoint against an isolated lineage database."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lineage-db", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


async def run(lineage_db: Path, report: Path) -> None:
    if not lineage_db.is_file():
        raise SystemExit(f"lineage database does not exist: {lineage_db}")
    if report.exists():
        raise SystemExit(f"refusing to overwrite report: {report}")

    repo = Path(__file__).resolve().parents[2]
    os.environ["LINEAGE_DB"] = str(lineage_db.resolve())
    os.environ["USER_DATA_DIR"] = str((report.parent / "user-data").resolve())
    sys.path.insert(0, str(repo / "src"))

    import httpx
    from main import app

    expected_db = sqlite3.connect(f"file:{lineage_db.resolve()}?mode=ro&immutable=1", uri=True)
    try:
        expected = {
            "persons": expected_db.execute("SELECT count(*) FROM persons").fetchone()[0],
            "edges": expected_db.execute(
                "SELECT count(*) FROM edges WHERE edge_type='teacher'"
            ).fetchone()[0],
            "places": expected_db.execute(
                "SELECT count(*) FROM places WHERE latitude IS NOT NULL"
            ).fetchone()[0],
            "scriptures": expected_db.execute(
                "SELECT count(DISTINCT scripture_id) FROM person_scriptures"
            ).fetchone()[0],
        }
    finally:
        expected_db.close()

    checks: list[dict[str, object]] = []

    async def get(client: "httpx.AsyncClient", path: str) -> "httpx.Response":
        started = time.monotonic()
        response = await client.get(path)
        elapsed = round(time.monotonic() - started, 3)
        if response.status_code != 200:
            raise AssertionError((path, response.status_code, response.text[:500]))
        checks.append({
            "path": path,
            "status": response.status_code,
            "seconds": elapsed,
            "bytes": len(response.content),
        })
        return response

    started_all = time.monotonic()
    for handler in app.router.on_startup:
        await handler()
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", timeout=90
        ) as client:
            search = (await get(client, "/api/lineage/search?q=金总持")).json()
            assert any(row["person_id"] == "A000001" for row in search)

            person = (await get(client, "/api/lineage/person/A000001")).json()
            assert person["person_id"] == "A000001" and person["name"] == "金總持"

            lineage = (await get(
                client, "/api/lineage/lineage/A000001?depth=5"
            )).json()
            assert lineage["root"] == "A000001"
            assert {"nodes", "edges"} <= lineage.keys()

            chronicle = (await get(
                client, "/api/lineage/chronicle?sect=曹洞宗&monk=monk"
            )).json()
            assert isinstance(chronicle, list) and chronicle

            map_data = (await get(
                client, "/api/lineage/map_data?limit=5000"
            )).json()
            assert {"origins", "temples", "mountains", "sect"} <= map_data.keys()

            person_places = (await get(
                client, "/api/lineage/person_places/A000001"
            )).json()
            assert isinstance(person_places, list)

            stats = (await get(client, "/api/lineage/stats")).json()
            assert stats == expected
    finally:
        for handler in app.router.on_shutdown:
            await handler()

    payload = {
        "status": "passed",
        "transport": "in-process ASGI after explicit production startup handlers",
        "lineage_db": str(lineage_db.resolve()),
        "endpoint_count": len(checks),
        "elapsed_seconds": round(time.monotonic() - started_all, 3),
        "stats": expected,
        "checks": checks,
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args.lineage_db, args.report))


if __name__ == "__main__":
    main()
