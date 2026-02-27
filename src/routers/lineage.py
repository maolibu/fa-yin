"""
祖师法脉 API — 从 30_Lineage/main.py 迁移整合
提供人物搜索、详情、法脉图、编年表、地图等 API。
所有端点前缀 /api/lineage。
"""

import sqlite3
import json
import bisect
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

import config

router = APIRouter(prefix="/api/lineage", tags=["祖师法脉"])

# ─── 数据库连接 ────────────────────────────────────────────────
def get_db():
    """获取 lineage.db 只读连接"""
    db_path = config.LINEAGE_DB
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ─── 朝代配置（编年表用） ──────────────────────────────────────

DYNASTY_ORDER = [
    ("先秦", -3000, -221),
    ("秦", -221, -206),
    ("漢", -206, 220),
    ("三國", 220, 265),
    ("西晉", 265, 317),
    ("東晉", 317, 420),
    ("南北朝", 420, 589),
    ("隋", 589, 618),
    ("唐", 618, 907),
    ("五代十國", 907, 960),
    ("北宋", 960, 1127),
    ("南宋", 1127, 1271),
    ("元", 1271, 1368),
    ("明", 1368, 1644),
    ("清", 1644, 1912),
    ("近現代", 1912, 2100),
]

_DB_TO_DISPLAY = {
    '唐': '唐', '北宋': '北宋', '南宋': '南宋',
    '大明': '明', '大清': '清',
}

_DYNASTY_NAME_MAP = {
    "先秦": "先秦", "秦": "秦", "漢": "漢",
    "三國": "三國", "西晉": "西晉", "東晉": "東晉",
    "南北朝": "南北朝",
    "隋": "隋", "唐": "唐",
    "五代十國": "五代十國",
    "北宋": "北宋", "南宋": "南宋",
    "元": "元", "明": "明", "清": "清", "近現代": "近現代", "民國": "近現代",
    "劉宋": "南北朝", "南齊": "南北朝", "南梁": "南北朝", "南陳": "南北朝",
    "北魏": "南北朝", "東魏": "南北朝", "西魏": "南北朝",
    "北齊": "南北朝", "北周": "南北朝", "陳": "南北朝",
    "西漢": "漢", "東漢": "漢", "新": "漢", "新莽": "漢",
    "曹魏": "三國", "蜀漢": "三國", "孫吳": "三國",
    "宋": "北宋",
    "後梁": "五代十國", "後唐": "五代十國", "後晉": "五代十國",
    "後漢": "五代十國", "後周": "五代十國",
    "金": "南宋", "大理國": "南宋",
    "前秦": "東晉", "後趙": "東晉", "後秦": "東晉",
    "前涼": "東晉", "後涼": "東晉", "北涼": "東晉", "南涼": "東晉",
    "西秦": "東晉", "成漢": "東晉",
    "春秋": "先秦", "戰國": "先秦", "東周": "先秦", "西周": "先秦",
    "唐堯": "先秦", "商": "先秦",
    "大明": "明", "大清": "清",
    "明/    清": "明", "清/    民國": "清",
    "隋/    唐": "唐", "元/    明": "明",
    "南宋/    元": "南宋", "唐/    五代十國": "唐",
    "北宋/    南宋": "北宋", "五代十國/    北宋": "五代十國",
    "金/    蒙古": "南宋", "金/    元": "元",
    "東晉/    劉宋": "東晉", "劉宋/    南齊": "南北朝",
    "南齊/    南梁": "南北朝", "南梁/    陳": "南北朝",
    "北魏/    東魏": "南北朝", "北魏/    西魏": "南北朝",
}


# ─── 辅助函数 ──────────────────────────────────────────────────

def _load_eras(db):
    """从 DB 加载清洗后的中国年号"""
    rows = db.execute("""
        SELECT e.era_id, e.name_zh, e.start_year, e.end_year,
               d.name_zh as dynasty_name
        FROM eras e
        JOIN dynasties d ON e.dynasty_id = d.dynasty_id
        WHERE d.type = 'chinese' AND e.start_year IS NOT NULL
          AND d.name_zh IN ('唐', '北宋', '南宋', '大明', '大清')
        ORDER BY e.start_year
    """).fetchall()
    result = {}
    for r in rows:
        display = _DB_TO_DISPLAY.get(r['dynasty_name'], r['dynasty_name'])
        if display not in result:
            result[display] = []
        result[display].append({
            'name': r['name_zh'],
            'start': r['start_year'],
            'end': r['end_year'],
        })
    return result


def _build_periods(db):
    """构建时段列表：小朝代整段，大朝代用年号细分"""
    eras_by_dynasty = _load_eras(db)

    for dynasty_name, era_list in eras_by_dynasty.items():
        sorted_eras = sorted(era_list, key=lambda e: e['start'])
        patches = []
        for i in range(1, len(sorted_eras)):
            prev_end = sorted_eras[i - 1]['end']
            curr_start = sorted_eras[i]['start']
            gap = curr_start - prev_end
            if gap > 1:
                patches.append({
                    'name': f'{prev_end + 1}–{curr_start - 1}',
                    'start': prev_end + 1,
                    'end': curr_start - 1,
                })
        era_list.extend(patches)

    periods = []
    for name, start, end in DYNASTY_ORDER:
        if name in eras_by_dynasty and eras_by_dynasty[name]:
            for era in eras_by_dynasty[name]:
                era_start = max(era['start'], start)
                era_end = min(era['end'], end)
                if era_start > era_end:
                    continue
                periods.append({
                    "id": f"{name}_{era['name']}",
                    "label": era['name'],
                    "dynasty": name,
                    "start": era_start,
                    "end": era_end,
                    "is_sub": True,
                })
        else:
            periods.append({
                "id": name,
                "label": name,
                "dynasty": name,
                "start": start,
                "end": end,
                "is_sub": False,
            })

    periods.sort(key=lambda p: p["start"])
    return periods


# ═══════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════

@router.get("/search")
async def search(q: str = Query(..., min_length=1)):
    """人名搜索（模糊匹配，繁简兼容）"""
    # 简→繁转换，确保简体输入也能匹配繁体人名
    try:
        from opencc import OpenCC
        _cc_s2t = OpenCC('s2t')
        q_t = _cc_s2t.convert(q)
    except ImportError:
        q_t = q

    db = get_db()
    try:
        # 如果简繁转换结果相同，只用一组条件
        if q_t == q:
            rows = db.execute("""
                SELECT person_id, name, dynasty, sect, birth_year, death_year
                FROM persons
                WHERE name LIKE ? OR aliases LIKE ? OR place_origin LIKE ?
                ORDER BY
                    CASE WHEN name = ? THEN 0
                         WHEN name LIKE ? THEN 1
                         WHEN place_origin LIKE ? THEN 2
                         ELSE 3 END,
                    birth_year
                LIMIT 20
            """, (f"%{q}%", f"%{q}%", f"%{q}%", q, f"{q}%", f"%{q}%")).fetchall()
        else:
            # 用转换后的繁体也搜索
            rows = db.execute("""
                SELECT person_id, name, dynasty, sect, birth_year, death_year
                FROM persons
                WHERE name LIKE ? OR name LIKE ?
                   OR aliases LIKE ? OR aliases LIKE ?
                   OR place_origin LIKE ? OR place_origin LIKE ?
                ORDER BY
                    CASE WHEN name = ? OR name = ? THEN 0
                         WHEN name LIKE ? OR name LIKE ? THEN 1
                         WHEN place_origin LIKE ? OR place_origin LIKE ? THEN 2
                         ELSE 3 END,
                    birth_year
                LIMIT 20
            """, (f"%{q}%", f"%{q_t}%",
                  f"%{q}%", f"%{q_t}%",
                  f"%{q}%", f"%{q_t}%",
                  q, q_t,
                  f"{q}%", f"{q_t}%",
                  f"%{q}%", f"%{q_t}%")).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@router.get("/person/{person_id}")
async def get_person(person_id: str):
    """人物详情 + 师承 + 经文"""
    db = get_db()
    try:
        p = db.execute("SELECT * FROM persons WHERE person_id = ?", (person_id,)).fetchone()
        if not p:
            raise HTTPException(status_code=404, detail=f"人物 {person_id} 不存在")

        person = dict(p)
        for field in ("aliases", "cbeta_refs"):
            if person.get(field):
                try:
                    person[field] = json.loads(person[field])
                except (json.JSONDecodeError, TypeError):
                    pass

        teachers = db.execute("""
            SELECT p.person_id, p.name, p.dynasty, p.sect, e.description
            FROM edges e JOIN persons p ON e.source_id = p.person_id
            WHERE e.target_id = ? AND e.edge_type = 'teacher'
        """, (person_id,)).fetchall()
        person["teachers"] = [dict(r) for r in teachers]

        students = db.execute("""
            SELECT p.person_id, p.name, p.dynasty, p.sect
            FROM edges e JOIN persons p ON e.target_id = p.person_id
            WHERE e.source_id = ? AND e.edge_type = 'teacher'
            ORDER BY p.birth_year
        """, (person_id,)).fetchall()
        person["students"] = [dict(r) for r in students]

        social = db.execute("""
            SELECT p.person_id, p.name, p.dynasty, e.description
            FROM edges e JOIN persons p ON
                CASE WHEN e.source_id = ? THEN e.target_id ELSE e.source_id END = p.person_id
            WHERE (e.source_id = ? OR e.target_id = ?) AND e.edge_type = 'social'
            LIMIT 20
        """, (person_id, person_id, person_id)).fetchall()
        person["social"] = [dict(r) for r in social]

        scriptures = db.execute("""
            SELECT scripture_id, relation, source_text, url
            FROM person_scriptures
            WHERE person_id = ?
            ORDER BY relation, scripture_id
        """, (person_id,)).fetchall()
        person["scriptures"] = [dict(r) for r in scriptures]

        return person
    finally:
        db.close()


@router.get("/lineage/{person_id}")
async def get_lineage(person_id: str, depth: int = Query(default=3, ge=1, le=5)):
    """以 person_id 为根的法脉子树（ego-centric）"""
    db = get_db()
    try:
        nodes = {}
        edges = []
        visited_down = set()

        def add_node(pid):
            if pid in nodes:
                return True
            p = db.execute(
                """SELECT p.person_id, p.name, p.dynasty, p.sect, p.birth_year, p.death_year,
                          (SELECT COUNT(*) FROM edges WHERE source_id = p.person_id AND edge_type='teacher') as student_count
                   FROM persons p WHERE p.person_id = ?""",
                (pid,)
            ).fetchone()
            if not p:
                return False
            nodes[pid] = dict(p)
            return True

        def collect_down(pid, current_depth):
            if pid in visited_down or current_depth > depth:
                return
            visited_down.add(pid)
            add_node(pid)
            children = db.execute("""
                SELECT target_id, description, cbeta_ref FROM edges
                WHERE source_id = ? AND edge_type = 'teacher'
            """, (pid,)).fetchall()
            for child in children:
                cid = child["target_id"]
                edges.append({"source": pid, "target": cid, "description": child["description"], "cbeta_ref": child["cbeta_ref"]})
                collect_down(cid, current_depth + 1)

        def collect_up(pid, levels):
            if levels <= 0 or pid in nodes:
                return
            add_node(pid)
            teachers = db.execute("""
                SELECT source_id, description, cbeta_ref FROM edges
                WHERE target_id = ? AND edge_type = 'teacher'
            """, (pid,)).fetchall()
            for t in teachers:
                tid = t["source_id"]
                edges.append({"source": tid, "target": pid, "description": t["description"], "cbeta_ref": t["cbeta_ref"]})
                collect_up(tid, levels - 1)

        collect_up(person_id, 2)
        collect_down(person_id, 1)

        return {
            "root": person_id,
            "nodes": list(nodes.values()),
            "edges": edges,
        }
    finally:
        db.close()


@router.get("/chronicle")
async def get_chronicle(
    sect: str = Query(default=None),
    monk: str = Query(default=None, description="僧俗过滤: monk=僧人, lay=俗人"),
):
    """编年表数据 — 三层手风琴"""
    db = get_db()
    try:
        conditions = ["1=1"]
        params = []
        if sect:
            conditions.append("sect LIKE ?")
            params.append(f"%{sect}%")
        if monk == "monk":
            conditions.append("is_monk = 1")
        elif monk == "lay":
            conditions.append("is_monk = 0")

        where = " AND ".join(conditions)
        rows = db.execute(f"""
            SELECT person_id, name, dynasty, sect, birth_year, death_year, is_monk
            FROM persons
            WHERE {where}
        """, params).fetchall()

        with_year = []
        without_year = []
        no_info = []
        for r in rows:
            p = dict(r)
            eff = p["birth_year"]
            if eff is None and p["death_year"] is not None:
                eff = p["death_year"] - 30
            p["_eff_year"] = eff
            if eff is not None:
                with_year.append(p)
            elif p["dynasty"]:
                without_year.append(p)
            else:
                no_info.append(p)

        with_year.sort(key=lambda p: p["_eff_year"])
        periods = _build_periods(db)
        for period in periods:
            period["_persons"] = []

        eff_years = [p["_eff_year"] for p in with_year]
        assigned = set()

        for period in sorted(periods, key=lambda p: p["start"]):
            p_start = period["start"]
            p_end = period["end"]
            start_idx = bisect.bisect_left(eff_years, p_start)
            for i in range(start_idx, len(with_year)):
                if with_year[i]["_eff_year"] > p_end:
                    break
                pid = with_year[i]["person_id"]
                if pid in assigned:
                    continue
                period["_persons"].append(with_year[i])
                assigned.add(pid)

        dynasty_unknown = defaultdict(list)
        for p in without_year:
            mapped = _DYNASTY_NAME_MAP.get(p["dynasty"])
            if mapped:
                dynasty_unknown[mapped].append(p)
            else:
                no_info.append(p)

        for dname, persons_list in dynasty_unknown.items():
            if not persons_list:
                continue
            dynasty_end = 0
            for d_name, d_start, d_end in DYNASTY_ORDER:
                if d_name == dname:
                    dynasty_end = d_end
                    break
            periods.append({
                "id": f"{dname}_待考",
                "label": "待考",
                "dynasty": dname,
                "start": dynasty_end,
                "end": dynasty_end,
                "is_sub": True,
                "_persons": persons_list,
            })

        if no_info:
            periods.append({
                "id": "待考",
                "label": "待考",
                "dynasty": "待考",
                "start": 9999,
                "end": 9999,
                "is_sub": False,
                "_persons": no_info,
            })

        dynasty_order_idx = {name: i for i, (name, _, _) in enumerate(DYNASTY_ORDER)}
        periods.sort(key=lambda p: (
            dynasty_order_idx.get(p["dynasty"], 999),
            p["start"],
        ))

        result = []
        for period in periods:
            pp = period["_persons"]
            if not pp:
                continue
            clean_persons = [
                {k: v for k, v in p.items() if not k.startswith("_")}
                for p in pp
            ]
            result.append({
                "id": period["id"],
                "label": period["label"],
                "dynasty": period["dynasty"],
                "start": period["start"],
                "end": period["end"],
                "is_sub": period["is_sub"],
                "person_count": len(clean_persons),
                "persons": clean_persons,
            })

        return result
    finally:
        db.close()


@router.get("/map_data")
async def get_map_data(
    sect: str = Query(default=None),
    limit: int = Query(default=2000, le=5000),
):
    """地图联动数据 — 籍贯 + 寺庙 + 山峰"""
    db = get_db()
    try:
        conditions = ["place_origin IS NOT NULL"]
        params = []
        if sect:
            conditions.append("sect LIKE ?")
            params.append(f"%{sect}%")

        where = " AND ".join(conditions)
        persons = db.execute(f"""
            SELECT person_id, name, sect, dynasty, birth_year, death_year, place_origin
            FROM persons
            WHERE {where}
            LIMIT ?
        """, params + [limit]).fetchall()

        origin_map = {}
        for p in persons:
            origin = p["place_origin"].strip()
            lines = origin.split("\n")
            place_name = lines[0].strip() if lines else ""
            for line in lines:
                line = line.strip()
                if line.startswith("PL"):
                    if line not in origin_map:
                        origin_map[line] = {"place_name": place_name, "persons": []}
                    origin_map[line]["persons"].append({
                        "person_id": p["person_id"],
                        "name": p["name"],
                        "sect": p["sect"],
                        "dynasty": p["dynasty"],
                    })

        origins = []
        if origin_map:
            place_ids = list(origin_map.keys())
            ph = ",".join("?" * len(place_ids))
            places = db.execute(f"""
                SELECT place_id, name_zh, latitude, longitude, district
                FROM places
                WHERE place_id IN ({ph}) AND latitude IS NOT NULL
            """, place_ids).fetchall()
            for pl in places:
                info = origin_map.get(pl["place_id"], {})
                origins.append({
                    "place_id": pl["place_id"],
                    "name": pl["name_zh"] or info.get("place_name", ""),
                    "lat": pl["latitude"],
                    "lng": pl["longitude"],
                    "district": pl["district"],
                    "persons": info.get("persons", []),
                    "count": len(info.get("persons", [])),
                })

        temples_rows = db.execute("""
            SELECT place_id, name_zh, latitude, longitude, district, category
            FROM places
            WHERE latitude IS NOT NULL
              AND category LIKE '%寺廟%'
            LIMIT 2000
        """).fetchall()
        temples = [{
            "place_id": t["place_id"],
            "name": t["name_zh"],
            "lat": t["latitude"],
            "lng": t["longitude"],
            "district": t["district"],
        } for t in temples_rows]

        mountains_rows = db.execute("""
            SELECT place_id, name_zh, latitude, longitude, district
            FROM places
            WHERE latitude IS NOT NULL
              AND category LIKE '%山峰%'
            LIMIT 1000
        """).fetchall()
        mountains = [{
            "place_id": m["place_id"],
            "name": m["name_zh"],
            "lat": m["latitude"],
            "lng": m["longitude"],
            "district": m["district"],
        } for m in mountains_rows]

        return {
            "origins": origins,
            "temples": temples,
            "mountains": mountains,
            "sect": sect,
        }
    finally:
        db.close()


@router.get("/person_places/{person_id}")
async def get_person_places(person_id: str):
    """通过 place_origin 查找人物关联的地点坐标"""
    db = get_db()
    try:
        p = db.execute(
            "SELECT place_origin FROM persons WHERE person_id = ?",
            (person_id,)
        ).fetchone()
        if not p or not p["place_origin"]:
            return []

        origin = p["place_origin"]
        lines = origin.strip().split("\n")
        results = []
        for line in lines:
            line = line.strip()
            if line.startswith("PL"):
                place = db.execute("""
                    SELECT place_id, name_zh, latitude, longitude, district
                    FROM places WHERE place_id = ?
                """, (line,)).fetchone()
                if place:
                    results.append(dict(place))
        return results
    finally:
        db.close()


@router.get("/stats")
async def get_stats():
    """统计数据 — 状态栏用"""
    db = get_db()
    try:
        persons = db.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
        edges = db.execute("SELECT COUNT(*) FROM edges WHERE edge_type='teacher'").fetchone()[0]
        places = db.execute("SELECT COUNT(*) FROM places WHERE latitude IS NOT NULL").fetchone()[0]
        scriptures = db.execute(
            "SELECT COUNT(DISTINCT scripture_id) FROM person_scriptures"
        ).fetchone()[0]
        return {
            "persons": persons,
            "edges": edges,
            "places": places,
            "scriptures": scriptures,
        }
    finally:
        db.close()

