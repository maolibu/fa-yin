#!/usr/bin/env python3
"""
字体对比测试 - 生成 HTML 页面对比多个字体的字符覆盖情况
只对比: SourceHanSerif-VF, WenJinMincho, BabelStoneHan, Jigmo, NanoOldSongA
"""

import os
import hashlib
from pathlib import Path
from fontTools.ttLib import TTFont

# ============================================================
# 配置
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent
FONT_DIR = str(SCRIPT_DIR / 'font')
# 输出文件名在 main 中动态生成: font_target_{N}.html

# 要对比的字体 (强制使用 TTF/OTF) - 思源和文津在前方便对比
from collections import OrderedDict
TARGET_FONTS = OrderedDict([
    ('思源宋体', ['SourceHanSerif-VF.otf', 'SourceHanSerif-VF.ttf', 'SourceHanSerif-VF.otf.woff2']),
    ('文津宋体', 'WenJinMincho'),
    ('BabelStoneHan', ['BabelStoneHan.ttf', 'BabelStoneHan.otf', 'BabelStoneHan.woff2']),
    ('字雲Jigmo', 'Jigmo'),
    ('南老宋', 'NanoOldSongA')
])

# ============================================================
# 测试文本 - 300+ 字符
# ============================================================

# 繁简对照常用字 - 选择差异明显的字 (繁体)
TEST_COMMON_TRAD = """國語說話學習閱讀書寫認識認為時間問題關係經過經驗發現發展
傳統處理觀點觀察實際實驗應該應用機會機構圖書圖畫萬歲萬事萬物區別區域
聯繫聯絡飛機飛翔廣告廣場電話電腦語言語氣話語話題歷史歷練辦公辦事學術
團結團隊體驗體系雜誌雜事運動運輸勞動勞力聯盟聯合獨立獨自舊書舊事齊心
傷害傷心線條線索節目節日親人親戚謝謝謝罪準備準時戰爭戰鬥騎馬騎車"""

# 繁简对照常用字 - 简体
TEST_COMMON_SIMPLE = """国语说话学习阅读书写认识认为时间问题关系经过经验发现发展
传统处理观点观察实际实验应该应用机会机构图书图画万岁万事万物区别区域
联系联络飞机飞翔广告广场电话电脑语言语气话语话题历史历练办公办事学术
团结团队体验体系杂志杂事运动运输劳动劳力联盟联合独立独自旧书旧事齐心
伤害伤心线条线索节目节日亲人亲戚谢谢谢罪准备准时战争战斗骑马骑车"""

# 佛教专用字 (繁体)
TEST_BUDDHIST_TRAD = """菩薩摩訶薩阿耨多羅三藐三菩提涅槃波羅蜜般若禪定精進忍辱布施持戒
梵天帝釋龍王夜叉乾闘婆阿修羅迦樓羅緊那羅摩睺羅伽人非人觀世音彌勒佛"""

# 佛教专用字 (简体)
TEST_BUDDHIST_SIMPLE = """菩萨摩诃萨阿耨多罗三藐三菩提涅槃波罗蜜般若禅定精进忍辱布施持戒
梵天帝释龙王夜叉乾闘婆阿修罗迦楼罗紧那罗摩睺罗伽人非人观世音弥勒佛"""

# 兼容变量名
TEST_COMMON = TEST_COMMON_TRAD
TEST_BUDDHIST = TEST_BUDDHIST_TRAD

# 罕见字 - CJK扩展区 (100字) - 保持繁体
TEST_RARE = """𠀀𠀁𠀂𠀃𠀄𠀅𠀆𠀇𠀈𠀉𠀊𠀋𠀌𠀍𠀎𠀏𠀐𠀑𠀒𠀓
𠁀𠁁𠁂𠁃𠁄𠁅𠁆𠁇𠁈𠁉𠁊𠁋𠁌𠁍𠁎𠁏𠁐𠁑𠁒𠁓
𢀀𢀁𢀂𢀃𢀄𢀅𢀆𢀇𢀈𢀉𢀊𢀋𢀌𢀍𢀎𢀏𢀐𢀑𢀒𢀓
𣀀𣀁𣀂𣀃𣀄𣀅𣀆𣀇𣀈𣀉𣀊𣀋𣀌𣀍𣀎𣀏𣀐𣀑𣀒𣀓
𤀀𤀁𤀂𤀃𤀄𤀅𤀆𤀇𤀈𤀉𤀊𤀋𤀌𤀍𤀎𤀏𤀐𤀑𤀒𤀓"""

# CBETA 实际缺字样本 (50字) - 保持原样
TEST_CBETA = """䆁𦵢渠陵棻罊鶪靃蔬莿禂碿蘖頖嘷吤咻唶嚁喿嗞噇嚸
咃垉揾嫥屵𡵉㟌𥧄㜷僓俍殸胈脦𣎴殄燍烌燡狖玘琔璏頔揌"""

# 标点和符号 (30字)
TEST_SYMBOLS = """。，、；：「」『』（）【】〈〉《》""''
！？…—～·○●◎◇◆□■△▲▽▼"""

# 数字和拉丁 (30字)
TEST_LATIN = """ABCDEFGHIJKLMNOPQRSTUVWXYZ
abcdefghijklmnopqrstuvwxyz
0123456789"""

# ============================================================
# 字体处理函数
# ============================================================

def get_font_cmap(font_path):
    """获取字体的 cmap (支持的字符集)"""
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

def find_target_fonts(font_dir, targets):
    """查找目标字体 - targets 是 {display_name: pattern或[pattern]} 字典
    
    先精确匹配文件名，再模糊匹配目录名
    """
    exts = {'.ttf', '.otf', '.woff', '.woff2'}
    found = {}
    items = os.listdir(font_dir)
    
    # 第一遍：精确匹配文件名
    for display_name, pattern in targets.items():
        candidates = pattern if isinstance(pattern, (list, tuple)) else [pattern]
        for cand in candidates:
            for item in items:
                if item == cand:  # 精确匹配
                    item_path = os.path.join(font_dir, item)
                    if os.path.isfile(item_path) and Path(item).suffix.lower() in exts:
                        found[display_name] = [item_path]
                        print(f"    精确匹配: {display_name} -> {item}")
                        break
            if display_name in found:
                break
    
    # 第二遍：目录匹配 (仅匹配尚未找到的)
    for display_name, pattern in targets.items():
        if display_name in found:
            continue
        if isinstance(pattern, (list, tuple)):
            continue
        for item in items:
            item_path = os.path.join(font_dir, item)
            if os.path.isdir(item_path) and item.lower() == pattern.lower():
                files = []
                for root, _, filenames in os.walk(item_path):
                    for f in filenames:
                        if Path(f).suffix.lower() in exts:
                            files.append(os.path.join(root, f))
                if files:
                    files.sort()
                    found[display_name] = files
                    print(f"    目录匹配: {display_name} -> {item}/ ({len(files)} 文件)")
                    break
    
    return found

def colorize_text(text, cmap, color_in="#4ecca3", color_out="#e94560"):
    """根据 cmap 给文本着色"""
    result = []
    for char in text:
        if char in '\n\r\t ':
            result.append(char)
            continue
        cp = ord(char)
        if cp in cmap:
            result.append(f'<span style="color:{color_in}">{char}</span>')
        else:
            result.append(f'<span style="color:{color_out}">{char}</span>')
    return ''.join(result)

def make_safe_id(name: str) -> str:
    return f"font_{hashlib.md5(name.encode('utf-8')).hexdigest()[:8]}"


def generate_html(fonts_data, output_path):
    """生成 HTML 对比页面"""
    
    html = '''<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>字体覆盖对比</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: system-ui, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }
        h1 {
            text-align: center;
            color: #4ecca3;
            margin-bottom: 10px;
        }
        .legend {
            text-align: center;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .legend span { margin: 0 15px; }
        .green { color: #4ecca3; }
        .red { color: #e94560; }
        .container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(450px, 1fr));
            gap: 20px;
            max-width: 1800px;
            margin: 0 auto;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card h2 {
            color: #ff6b6b;
            margin: 0 0 10px 0;
            font-size: 18px;
        }
        .stats {
            color: #888;
            font-size: 12px;
            margin-bottom: 15px;
        }
        .coverage {
            color: #4ecca3;
            font-size: 13px;
            margin-bottom: 15px;
        }
        .section {
            margin-bottom: 15px;
        }
        .section-title {
            color: #888;
            font-size: 11px;
            margin-bottom: 5px;
        }
        .text-sample {
            font-size: 18px;
            line-height: 1.8;
            word-break: break-all;
        }
'''
    
    # 添加 @font-face
    for name, data in fonts_data.items():
        safe_name = make_safe_id(name)
        font_families = []
        for i, fp in enumerate(data['files']):
            ext = Path(fp).suffix.lower()
            fmt = {'ttf': 'truetype', 'otf': 'opentype', 'woff': 'woff', 'woff2': 'woff2'}.get(ext[1:], 'truetype')
            family = f"TestFont_{safe_name}_{i}"
            font_families.append(f"'{family}'")
            html += f'''
        @font-face {{
            font-family: '{family}';
            src: url('font/{os.path.relpath(fp, FONT_DIR)}') format('{fmt}');
            font-display: swap;
        }}
'''
        html += f'''
        .font_{safe_name} .text-sample {{
            font-family: {', '.join(font_families)} !important;
        }}
'''
    
    html += '''
    </style>
</head>
<body>
    <h1>字体覆盖对比测试</h1>
    <div class="legend">
        <span class="green">● 绿色 = cmap 中存在</span>
        <span class="red">● 红色 = 缺失</span>
    </div>
    <div class="container">
'''
    
    # 生成每个字体的卡片 (按 TARGET_FONTS 顺序)
    all_text = TEST_COMMON + TEST_BUDDHIST + TEST_RARE + TEST_CBETA
    all_chars = set(c for c in all_text if c not in '\n\r\t ')
    
    for name in TARGET_FONTS.keys():
        if name not in fonts_data:
            continue
        data = fonts_data[name]
        safe_name = make_safe_id(name)
        cmap = data['cmap']
        
        # 计算覆盖
        common_chars = set(c for c in TEST_COMMON if c not in '\n\r\t ')
        rare_chars = set(c for c in (TEST_RARE + TEST_CBETA) if c not in '\n\r\t ')
        
        common_covered = len(common_chars & set(chr(c) for c in cmap))
        rare_covered = len(rare_chars & set(chr(c) for c in cmap))
        
        html += f'''
        <div class="card font_{safe_name}">
            <h2>{name}</h2>
            <div class="stats">{len(data['files'])} 文件 | cmap: {len(cmap):,} 字</div>
            <div class="coverage">常用 {common_covered}/{len(common_chars)} | 罕用 {rare_covered}/{len(rare_chars)}</div>
            
            <div class="section">
                <div class="section-title">常用字 (繁体):</div>
                <div class="text-sample">{TEST_COMMON_TRAD.replace(chr(10), '')}</div>
            </div>
            
            <div class="section">
                <div class="section-title">常用字 (简体):</div>
                <div class="text-sample">{TEST_COMMON_SIMPLE.replace(chr(10), '')}</div>
            </div>
            
            <div class="section">
                <div class="section-title">佛教专用字 (繁体):</div>
                <div class="text-sample">{TEST_BUDDHIST_TRAD.replace(chr(10), '')}</div>
            </div>
            
            <div class="section">
                <div class="section-title">佛教专用字 (简体):</div>
                <div class="text-sample">{TEST_BUDDHIST_SIMPLE.replace(chr(10), '')}</div>
            </div>
            
            <div class="section">
                <div class="section-title">罕见字 (绿=覆盖, 红=缺失):</div>
                <div class="text-sample">{colorize_text(TEST_RARE[:50].replace(chr(10), ''), cmap)}</div>
            </div>
            
            <div class="section">
                <div class="section-title">CBETA 缺字样本:</div>
                <div class="text-sample">{colorize_text(TEST_CBETA.replace(chr(10), ''), cmap)}</div>
            </div>
            
            <div class="section">
                <div class="section-title">Latin:</div>
                <div class="text-sample">{TEST_LATIN.replace(chr(10), ' ')}</div>
            </div>
        </div>
'''
    
    html += '''
    </div>
</body>
</html>
'''
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ 生成 HTML: {output_path}")

# ============================================================
# 主程序
# ============================================================

if __name__ == '__main__':
    print("=" * 60)
    print("字体覆盖对比测试")
    print("=" * 60)
    
    # 查找目标字体
    print(f"\n📂 扫描字体目录: {FONT_DIR}")
    fonts = find_target_fonts(FONT_DIR, TARGET_FONTS)
    
    # 动态生成输出文件名: font_target_{字体数}.html
    OUTPUT_HTML = str(SCRIPT_DIR / f'font_target_{len(fonts)}.html')
    
    print(f"\n找到 {len(fonts)} 个目标字体:")
    for name, files in fonts.items():
        print(f"  ✓ {name}: {len(files)} 文件")
    
    # 分析字体
    print("\n📊 分析字体 cmap...")
    fonts_data = {}
    for name, files in fonts.items():
        cmap = set()
        for fp in files:
            cmap.update(get_font_cmap(fp))
        fonts_data[name] = {
            'files': files,
            'cmap': cmap
        }
        print(f"  {name}: {len(cmap):,} 字符")
    
    # 生成 HTML
    print("\n🖥️ 生成 HTML...")
    generate_html(fonts_data, OUTPUT_HTML)
    
    print("\n✅ 完成!")
    print(f"打开浏览器查看: file://{OUTPUT_HTML}")

