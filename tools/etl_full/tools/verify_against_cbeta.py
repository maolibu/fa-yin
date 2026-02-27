"""
CBETA 自动校对脚本
将本地 ETL 输出与 CBETA 官方在线 API 文本逐字对比，发现错漏。

用法：
    python tools/verify_against_cbeta.py T0251           # 校对单部经
    python tools/verify_against_cbeta.py T0001 --juan 1   # 校对指定卷
    python tools/verify_against_cbeta.py --all            # 校对全部已转换经典

CBETA API 端点：
    https://cbdata.dila.edu.tw/stable/juans?work={经号}&juan={卷号}
"""

import argparse
import difflib
import json
import os
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ============================================================
# 配置
# ============================================================
ETL_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = ETL_DIR.parent
DB_PATH = ETL_DIR / "output" / "cbeta.db"
REPORT_DIR = ETL_DIR / "output" / "verify_reports"

CBETA_API_BASE = "https://cbdata.dila.edu.tw/stable/juans"
REQUEST_DELAY = 5.0  # 请求间隔（秒），避免给 CBETA 服务器造成压力（全量校对建议 5 秒）


# ============================================================
# 从 CBETA API 获取参考文本
# ============================================================
def fetch_cbeta_html(work_id, juan_num):
    """
    调用 CBETA API 获取指定经卷的 HTML 内容。
    返回 HTML 字符串，或 None（失败时）。
    """
    import ssl
    url = f"{CBETA_API_BASE}?work={work_id}&juan={juan_num}"
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "FaYin-ETL-Verify/1.0 (Buddhist Digital Humanities)")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e):
                # SSL 证书问题（conda 环境常见），回退到不验证
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            else:
                raise
        results = data.get("results", [])
        if results:
            return results[0]
        return None
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
        print(f"    ⚠️ API 请求失败 ({work_id} 卷{juan_num}): {e}")
        return None


# ============================================================
# 文本规范化：去标签、去标点、去空白
# ============================================================
def strip_html_tags(html):
    """去除所有 HTML 标签，保留文本内容"""
    return re.sub(r"<[^>]+>", "", html)


def preprocess_cbeta_html(html):
    """
    预处理 CBETA API 返回的 HTML：
    只保留 <div id='body'...>...</div> 中的正文，
    去除 <head>, 校注 (<div id='back'>), 版权声明等。
    """
    # 用字符串查找定位 body div（不依赖换行/空格格式）
    body_start = html.find("<div id='body'")
    if body_start == -1:
        # 兼容双引号
        body_start = html.find('<div id="body"')
    if body_start != -1:
        # 跳过 <div id='body'...> 开标签
        tag_end = html.find(">", body_start)
        if tag_end != -1:
            html = html[tag_end + 1:]

    # 截断：去掉 back 区块及之后的内容
    for marker in ["<div id='back'>", '<div id="back">', "<div id='back'",
                    "<div id='cbeta-copyright'>", '<div id="cbeta-copyright">']:
        pos = html.find(marker)
        if pos != -1:
            html = html[:pos]
            break

    # 去 noteAnchor 链接（校注引用标记）
    html = re.sub(r"<a class=['\"]noteAnchor['\"][^>]*>.*?</a>", "", html, flags=re.DOTALL)
    return html


def normalize_for_compare(text):
    """
    规范化文本用于对比：
    1. 去除所有 HTML 标签
    2. 去除 CBETA 标点
    3. 去除空白字符
    4. 去除行号标记
    5. 去除编号行
    """
    # 去 HTML 标签
    text = strip_html_tags(text)

    # 解码 HTML 实体（如 &nbsp; → 空格）
    import html as html_module
    text = html_module.unescape(text)

    # 去编号行（如 "No. 251 [Nos. 250, 252-255, 257]"）
    # 也处理 [cf. No. 223] 格式（交叉引用）
    text = re.sub(r"\[cf\.\s*No\.\s*[^\]]+\]", "", text)
    text = re.sub(r"No\.\s*\d+\s*\[Nos?\.\s*[^\]]+\]", "", text)
    text = re.sub(r"No\.\s*\d+", "", text)

    # 注意：咒语中的 CBETA 断句编号（一、二、三...）不做清除，
    # 因为中文数字也出现在正文中，无法安全区分。这类差异属于可接受的格式差异。

    # 去行号和页面 ID（覆盖所有藏经格式）
    # 完整格式：T08n0251_p0848a01, A098n1267_p0123b05
    text = re.sub(r"[A-Z]+\d+n\d+_p\d*[a-c]?\d*", "", text)
    # 简短页面 ID（API 有时仅输出 A098n1267_p 不带行号）
    text = re.sub(r"[A-Z]+\d+n\d+_p", "", text)
    # 旧格式行号
    text = re.sub(r"\d{4}[a-c]\d{2}", "", text)

    # 去 CBETA 标点符号（全面覆盖）
    punctuation = (
        "，。、；：！？「」『』（）〔〕【】"
        "……—─　"
        "．·"
        ",.:;!?\"'()[]{}|/\\"
        "＊＝"
        "〈〉《》"
        "－"
    )
    for p in punctuation:
        text = text.replace(p, "")

    # 去除空白
    text = re.sub(r"\s+", "", text)

    return text


# ============================================================
# 对比两段文本
# ============================================================
def compare_texts(local_text, cbeta_text, context_size=10):
    """
    对比两段规范化后的文本。
    返回:
        match_ratio: 匹配率 (0.0 ~ 1.0)
        diffs: 差异列表 [(type, position, local_snippet, cbeta_snippet), ...]
    """
    matcher = difflib.SequenceMatcher(None, local_text, cbeta_text)
    match_ratio = matcher.ratio()

    diffs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        # 获取上下文
        ctx_start_local = max(0, i1 - context_size)
        ctx_end_local = min(len(local_text), i2 + context_size)
        ctx_start_cbeta = max(0, j1 - context_size)
        ctx_end_cbeta = min(len(cbeta_text), j2 + context_size)

        local_context = (
            local_text[ctx_start_local:i1]
            + "【" + local_text[i1:i2] + "】"
            + local_text[i2:ctx_end_local]
        )
        cbeta_context = (
            cbeta_text[ctx_start_cbeta:j1]
            + "【" + cbeta_text[j1:j2] + "】"
            + cbeta_text[j2:ctx_end_cbeta]
        )

        diffs.append({
            "type": tag,
            "position": i1,
            "local_chars": local_text[i1:i2],
            "cbeta_chars": cbeta_text[j1:j2],
            "local_context": local_context,
            "cbeta_context": cbeta_context,
        })

    return match_ratio, diffs


# ============================================================
# 校对单卷
# ============================================================
def verify_juan(conn, sutra_id, juan_num):
    """
    校对单卷：从数据库取本地文本，从 API 取 CBETA 文本，做对比。
    返回 (match_ratio, diffs, local_len, cbeta_len) 或 None。
    """
    # 获取本地文本
    row = conn.execute(
        "SELECT plain_text FROM content WHERE sutra_id = ? AND juan = ?",
        (sutra_id, juan_num),
    ).fetchone()
    if not row:
        print(f"    ⚠️ 本地数据库无 {sutra_id} 卷{juan_num}")
        return None

    local_raw = row[0]

    # 从 CBETA API 获取参考文本
    # 需要将 sutra_id (如 T0251) 转换为 API 格式
    # API work 参数直接使用 sutra_id 即可
    cbeta_html = fetch_cbeta_html(sutra_id, juan_num)
    if cbeta_html is None:
        return None

    # 规范化
    local_norm = normalize_for_compare(local_raw)
    cbeta_norm = normalize_for_compare(preprocess_cbeta_html(cbeta_html))

    # 对比
    match_ratio, diffs = compare_texts(local_norm, cbeta_norm)

    return match_ratio, diffs, len(local_norm), len(cbeta_norm)


# ============================================================
# 校对整部经
# ============================================================
def verify_sutra(conn, sutra_id, juan_filter=None):
    """校对整部经（或指定卷）"""
    # 获取卷列表
    if juan_filter is not None:
        rows = conn.execute(
            "SELECT juan FROM content WHERE sutra_id = ? AND juan = ? ORDER BY juan",
            (sutra_id, juan_filter),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT juan FROM content WHERE sutra_id = ? ORDER BY juan",
            (sutra_id,),
        ).fetchall()

    if not rows:
        print(f"❌ 数据库中找不到 {sutra_id}")
        return None

    # 获取经名
    cat = conn.execute(
        "SELECT title FROM catalog WHERE sutra_id = ?", (sutra_id,)
    ).fetchone()
    title = cat[0] if cat else sutra_id

    print(f"\n{'='*60}")
    print(f"📖 {sutra_id} {title} ({len(rows)} 卷)")
    print(f"{'='*60}")

    results = []
    for (juan_num,) in rows:
        print(f"  卷 {juan_num:>3d} ...", end=" ", flush=True)
        result = verify_juan(conn, sutra_id, juan_num)

        if result is None:
            print("⚠️ 跳过")
            continue

        match_ratio, diffs, local_len, cbeta_len = result

        # 显示结果
        if match_ratio >= 0.99:
            icon = "✅"
        elif match_ratio >= 0.95:
            icon = "🟡"
        else:
            icon = "❌"

        print(
            f"{icon} 匹配率 {match_ratio:.1%}  "
            f"(本地 {local_len} 字 / CBETA {cbeta_len} 字, "
            f"差异 {len(diffs)} 处)"
        )

        # 显示前 5 个差异
        for i, d in enumerate(diffs[:5]):
            tag_label = {
                "replace": "替换",
                "delete": "本地多余",
                "insert": "本地缺少",
            }.get(d["type"], d["type"])
            print(f"    {i+1}. [{tag_label}] 位置 {d['position']}")
            if d["local_chars"]:
                print(f"       本地: ...{d['local_context']}...")
            if d["cbeta_chars"]:
                print(f"       CBETA: ...{d['cbeta_context']}...")

        if len(diffs) > 5:
            print(f"    ... 还有 {len(diffs) - 5} 处差异")

        results.append({
            "sutra_id": sutra_id,
            "juan": juan_num,
            "match_ratio": match_ratio,
            "local_len": local_len,
            "cbeta_len": cbeta_len,
            "diff_count": len(diffs),
            "diffs": diffs,
        })

        # 请求间隔
        time.sleep(REQUEST_DELAY)

    return results


# ============================================================
# 保存报告
# ============================================================
def save_report(all_results, report_path):
    """将校对结果保存为 JSON 报告"""
    os.makedirs(report_path.parent, exist_ok=True)

    # 汇总统计
    total_juans = sum(len(r) for r in all_results if r)
    total_diffs = sum(
        sum(j["diff_count"] for j in r)
        for r in all_results if r
    )
    avg_ratio = 0
    ratios = [j["match_ratio"] for r in all_results if r for j in r]
    if ratios:
        avg_ratio = sum(ratios) / len(ratios)

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_juans": total_juans,
            "total_diffs": total_diffs,
            "avg_match_ratio": round(avg_ratio, 4),
        },
        "details": [j for r in all_results if r for j in r],
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n📄 详细报告已保存: {report_path}")


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="CBETA 自动校对工具")
    parser.add_argument(
        "sutra_id", nargs="?", default=None,
        help="经号（如 T0251）",
    )
    parser.add_argument("--juan", type=int, help="指定卷号")
    parser.add_argument("--all", action="store_true", help="校对全部已转换经典")
    parser.add_argument(
        "--report", type=str, default=None,
        help="保存 JSON 报告的路径（默认: output/verify_reports/verify_<经号>.json）",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        print("请先运行 ETL 转换脚本")
        return

    conn = sqlite3.connect(str(DB_PATH))

    all_results = []

    if args.all:
        # 校对全部
        rows = conn.execute(
            "SELECT DISTINCT sutra_id FROM catalog ORDER BY sutra_id"
        ).fetchall()
        print(f"📚 将校对 {len(rows)} 部已转换经典")
        for (sutra_id,) in rows:
            result = verify_sutra(conn, sutra_id)
            all_results.append(result)

        report_path = Path(args.report) if args.report else REPORT_DIR / "verify_all.json"

    elif args.sutra_id:
        # 校对单部经
        result = verify_sutra(conn, args.sutra_id, args.juan)
        all_results.append(result)

        report_path = (
            Path(args.report) if args.report
            else REPORT_DIR / f"verify_{args.sutra_id}.json"
        )

    else:
        parser.print_help()
        conn.close()
        return

    # 汇总
    ratios = [j["match_ratio"] for r in all_results if r for j in r]
    total_diffs = sum(j["diff_count"] for r in all_results if r for j in r)

    print(f"\n{'='*60}")
    print("📊 校对汇总")
    print(f"{'='*60}")
    print(f"  校对卷数: {len(ratios)}")
    if ratios:
        print(f"  平均匹配率: {sum(ratios)/len(ratios):.1%}")
        print(f"  最低匹配率: {min(ratios):.1%}")
        print(f"  总差异数: {total_diffs}")

    # 保存报告
    save_report(all_results, report_path)

    conn.close()


if __name__ == "__main__":
    main()
