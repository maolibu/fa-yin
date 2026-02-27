#!/usr/bin/env python3
"""
全部字库渲染测试 - 扫描 font 目录下所有字体，生成 HTML 页面
输出: font_all_{N}.html  (N = 字体组数)

依赖: pip install fonttools
"""

import os
from pathlib import Path
from collections import defaultdict
from fontTools.ttLib import TTFont

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = str(SCRIPT_DIR / 'font')

# 测试文本
TEST_COMMON = "諸佛智慧甚深無量，其智慧門難解難入。一切有為法，如夢幻泡影。"
TEST_RARE = ("𮗿𮡘𤦲𮥘𬃖𤛓𪄱𪙔𮑾𦱕𧂐𦿆𩑔𠯗𭉨𭇓𠲿𠸻𠺕𠼝𢒯𡀔𡂠𡄇𡆗"
             "𠷐𤬪𡎔𡣶𡰱𡼏𡺲𡻬𡺿𬿆𫣖𭮨脃𦟛𣧑𣩠𤏙𤋲𭵱𤘽𭹁𤥭𭹳𩑶𢯵")
TEST_LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZ 0123456789"


def get_font_cmap(font_path):
    """获取字体的 cmap"""
    try:
        font = TTFont(font_path)
        cmap = set()
        for table in font['cmap'].tables:
            if hasattr(table, 'cmap'):
                cmap.update(table.cmap.keys())
        font.close()
        return cmap
    except Exception as e:
        print(f"  ⚠️ 无法读取 {Path(font_path).name}: {e}")
        return set()


def collect_fonts_by_subdir(font_dir):
    """按子文件夹收集并合并字体"""
    exts = {'.ttf', '.otf', '.woff', '.woff2'}
    groups = defaultdict(list)

    for item in os.listdir(font_dir):
        item_path = os.path.join(font_dir, item)
        if os.path.isdir(item_path):
            for root, _, files in os.walk(item_path):
                for f in files:
                    if Path(f).suffix.lower() in exts:
                        groups[item].append(os.path.join(root, f))
        elif Path(item).suffix.lower() in exts:
            groups[item].append(item_path)

    result = {}
    for name, files in sorted(groups.items()):
        merged_cmap = set()
        print(f"\n📁 {name}")
        for fp in files:
            cmap = get_font_cmap(fp)
            merged_cmap.update(cmap)
            size = os.path.getsize(fp)
            print(f"   - {Path(fp).name}: {len(cmap):,} 字符, {size/1024/1024:.1f} MB")
        if len(files) > 1:
            print(f"   📊 合并: {len(merged_cmap):,} 字符")
        result[name] = {'files': files, 'cmap': merged_cmap}
    return result


def colorize_char(char, cmap, color_common="#ffffff", color_rare="#4ecca3", color_miss="#e94560"):
    """根据 cmap 给单个字符着色"""
    cp = ord(char)
    if cp in cmap:
        # 常用 BMP 区用白色，扩展区用绿色
        color = color_common if cp < 0x10000 else color_rare
    else:
        color = color_miss
    return f'<span style="color:{color}">{char}</span>'


def generate_html(font_groups, output_path):
    """生成全部字库渲染测试 HTML"""

    # 常用字和罕用字集合
    common_chars = set(c for c in TEST_COMMON if c not in '\n\r\t ')
    rare_chars = set(c for c in TEST_RARE if c not in '\n\r\t ')

    html = '<!DOCTYPE html>\n<html>\n<head>\n    <meta charset="UTF-8">\n'
    html += '    <title>CBETA 字库渲染测试</title>\n    <style>\n'

    # @font-face 规则
    font_face_count = 0
    font_stack_map = {}
    for idx, (name, data) in enumerate(font_groups.items()):
        safe_name = name.replace('.', '_').replace('-', '_').replace(' ', '_')
        font_families = []
        for fp in data['files']:
            ext = Path(fp).suffix.lower()
            fmt = {'ttf': 'truetype', 'otf': 'opentype', 'woff': 'woff', 'woff2': 'woff2'}.get(ext[1:], 'truetype')
            rel = os.path.relpath(fp, FONT_DIR)
            family = f"TestFont_{idx}_{safe_name}_{len(font_families)}"
            font_families.append(f"'{family}'")
            html += f"""
@font-face {{
    font-family: '{family}';
    src: url('font/{rel}') format('{fmt}');
    font-display: swap;
}}
"""
            font_face_count += 1
        font_stack_map[idx] = ', '.join(font_families) if font_families else f"'TestFont_{idx}_{safe_name}'"

    # 每个卡片的字体样式
    for idx, (name, data) in enumerate(font_groups.items()):
        safe_name = name.replace('.', '_').replace('-', '_').replace(' ', '_')
        html += f"""
.card-{idx} .font-sample {{
    font-family: {font_stack_map.get(idx, f"'TestFont_{idx}_{safe_name}'")} !important;
}}
"""

    # 全局样式
    html += """
        * { box-sizing: border-box; }
        body {
            font-family: system-ui, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
            margin: 0;
        }
        h1 { text-align: center; color: #fff; margin-bottom: 10px; }
        .subtitle { text-align: center; color: #888; margin-bottom: 30px; }
        .legend { text-align: center; margin-bottom: 20px; font-size: 14px; }
        .legend span { margin: 0 15px; }
        .container { max-width: 1000px; margin: 0 auto; }
        .card {
            background: #16213e;
            margin-bottom: 25px;
            padding: 20px;
            border-radius: 12px;
            border: 1px solid #0f3460;
        }
        .card-header {
            border-bottom: 1px solid #0f3460;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .font-title { font-size: 1.4em; font-weight: bold; color: #e94560; }
        .font-files { font-size: 0.8em; color: #666; margin-top: 5px; }
        .font-stats { font-size: 0.85em; color: #4ecca3; margin-top: 3px; }
        .font-sample { font-size: 22px; line-height: 1.8; }
        .sample-label {
            font-size: 12px;
            color: #666;
            margin-top: 10px;
            font-family: system-ui, sans-serif !important;
        }
        .sample-text { word-break: break-all; }
    </style>
</head>
<body>
    <h1>🔍 CBETA 字库渲染测试</h1>
    <p class="subtitle">颜色表示 cmap 覆盖情况（通过 fontTools 分析）</p>
    <div class="legend">
        <span style="color:#fff">⬤ 白色 = 常用字覆盖</span>
        <span style="color:#4ecca3">⬤ 绿色 = 罕用字覆盖</span>
        <span style="color:#e94560">⬤ 红色 = 缺失（使用系统回退）</span>
    </div>
    <div class="container">
        """

    # 生成每个字体卡片
    for idx, (name, data) in enumerate(font_groups.items()):
        cmap = data['cmap']

        # 统计
        common_covered = len(common_chars & set(chr(c) for c in cmap if c <= 0x10FFFF))
        rare_covered = len(rare_chars & set(chr(c) for c in cmap if c <= 0x10FFFF))

        # 常用字着色
        common_html = ''.join(colorize_char(c, cmap) for c in TEST_COMMON)
        # 罕用字着色 (分两行)
        rare_line1 = ''.join(colorize_char(c, cmap) for c in TEST_RARE[:25])
        rare_line2 = ''.join(colorize_char(c, cmap) for c in TEST_RARE[25:])
        # Latin 着色
        latin_html = ''.join(colorize_char(c, cmap) for c in TEST_LATIN)

        html += f"""
    <div class="card card-{idx}">
        <div class="card-header">
            <div class="font-title">{name}</div>
            <div class="font-files">{len(data['files'])} 文件 | cmap: {len(cmap):,} 字</div>
            <div class="font-stats">常用 {common_covered}/{len(common_chars)} | 罕用 {rare_covered}/{len(rare_chars)}</div>
        </div>
        <div class="font-sample">
            <div class="sample-label">常用字 (白=覆盖, 红=缺失):</div>
            <div class="sample-text">{common_html}</div>
            <div class="sample-label">罕用字 (绿=覆盖, 红=缺失):</div>
            <div class="sample-text">{rare_line1}</div>
            <div class="sample-text">{rare_line2}</div>
            <div class="sample-label">Latin:</div>
            <div class="sample-text">{latin_html}</div>
        </div>
    </div>
"""

    html += """
    </div>
</body>
</html>
"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n✅ 生成完毕: {output_path}")
    print(f"📝 共 {font_face_count} 个 @font-face 规则")


if __name__ == '__main__':
    print("=" * 60)
    print("全部字库渲染测试")
    print("=" * 60)

    font_groups = collect_fonts_by_subdir(FONT_DIR)

    # 动态生成输出文件名: font_all_{字体组数}.html
    output_path = str(SCRIPT_DIR / f'font_all_{len(font_groups)}.html')

    print(f"\n发现 {len(font_groups)} 个字体组")
    print("分析字体覆盖...")
    for name, data in font_groups.items():
        cmap = data['cmap']
        common_chars = set(c for c in TEST_COMMON if c not in '\n\r\t ')
        rare_chars = set(c for c in TEST_RARE if c not in '\n\r\t ')
        test_chars = common_chars | rare_chars
        covered = len(test_chars & set(chr(c) for c in cmap if c <= 0x10FFFF))
        print(f"  {name}: cmap {len(cmap)} 字符, 测试文本覆盖 {covered}/{len(test_chars)}")

    generate_html(font_groups, output_path)
