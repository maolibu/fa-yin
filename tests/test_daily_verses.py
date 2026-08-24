import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

from tools.daily_verses.csv_to_verses_json import convert_csv_to_json


def test_daily_verses_csv_rebuilds_frozen_json(tmp_path):
    rebuilt = tmp_path / "verses.json"
    convert_csv_to_json(
        PROJECT_ROOT / "tools" / "daily_verses" / "每日偈颂.csv",
        rebuilt,
    )

    expected = json.loads((PROJECT_ROOT / "data" / "db" / "verses.json").read_text(encoding="utf-8"))
    actual = json.loads(rebuilt.read_text(encoding="utf-8"))

    assert len(actual) == 365
    assert actual == expected
