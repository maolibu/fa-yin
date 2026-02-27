"""
地图瓦片校验工具
功能：
1. 检查文件大小是否为0
2. 检查文件头是否为 PNG 格式
3. 生成预览 HTML 文件供人工抽查
"""

import os
import random
from pathlib import Path

# 配置路径
BASE_DIR = Path(__file__).resolve().parent.parent / "data" / "tiles"
PREVIEW_FILE = BASE_DIR / "preview.html"

def is_valid_png(filepath):
    """检查文件头是否为 PNG"""
    try:
        with open(filepath, "rb") as f:
            header = f.read(8)
            # PNG 签名: 89 50 4E 47 0D 0A 1A 0A
            return header == b"\x89\x50\x4e\x47\x0d\x0a\x1a\x0a"
    except Exception:
        return False

def main():
    if not BASE_DIR.exists():
        print(f"❌ 目录不存在: {BASE_DIR}")
        return

    print(f"正在校验目录: {BASE_DIR}")
    
    total_files = 0
    zero_byte_files = []
    invalid_header_files = []
    valid_files = []

    # 遍历文件
    for filepath in BASE_DIR.rglob("*"):
        if filepath.is_file() and filepath.suffix.lower() == ".png":
            total_files += 1
            
            # 检查大小
            if filepath.stat().st_size == 0:
                zero_byte_files.append(filepath)
                print(f"  [0字节] {filepath.relative_to(BASE_DIR)}")
                continue

            # 检查文件头
            if not is_valid_png(filepath):
                invalid_header_files.append(filepath)
                print(f"  [无效PNG] {filepath.relative_to(BASE_DIR)}")
                continue

            valid_files.append(filepath)

            if total_files % 2000 == 0:
                print(f"  已扫描 {total_files} 个文件...")

    print("\n═══ 校验结果 ═══")
    print(f"扫描总数: {total_files}")
    print(f"有效文件: {len(valid_files)}")
    
    if zero_byte_files:
        print(f"❌ 0字节文件: {len(zero_byte_files)} (建议删除并重新下载)")
    else:
        print("✅ 无 0字节文件")

    if invalid_header_files:
        print(f"❌ 无效PNG文件: {len(invalid_header_files)} (可能是 HTML 错误页)")
        # 打印前5个无效文件的内容头（可能是 HTTP 错误文本）
        for f in invalid_header_files[:5]:
            try:
                with open(f, "rb") as verify_f:
                    print(f"    -> {f.name}: {verify_f.read(50)}")
            except:
                pass
    else:
        print("✅ 所有文件 PNG 头验证通过")

    # 生成预览 HTML
    if valid_files:
        sample_count = min(100, len(valid_files))
        samples = random.sample(valid_files, sample_count)
        
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>瓦片抽样检查</title>
            <style>
                body { background: #888; color: #fff; font-family: sans-serif; padding: 20px; }
                h1 { text-align: center; }
                .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(256px, 1fr)); gap: 10px; }
                .tile { background: #ccc; border: 1px solid #000; padding: 5px; text-align: center; color: #000; }
                .tile img { display: block; margin: 0 auto; background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10"><rect width="5" height="5" fill="%23eee"/><rect x="5" y="5" width="5" height="5" fill="%23eee"/></svg>'); }
                .dark .tile { background: #333; color: #fff; border-color: #666; }
                .label { font-size: 10px; margin-top: 5px; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
            </style>
        </head>
        <body>
            <h1>随机抽样预览 (100张)</h1>
            <div class="grid">
        """
        
        for p in samples:
            rel_path = p.relative_to(BASE_DIR)
            # 区分 light/dark 样式
            is_dark = "dark" in str(rel_path)
            css_class = "tile dark" if is_dark else "tile"
            html_content += f"""
                <div class="{css_class}">
                    <img src="{rel_path}" width="256" height="256" loading="lazy">
                    <div class="label">{rel_path}</div>
                </div>
            """
            
        html_content += """
            </div>
        </body>
        </html>
        """
        
        with open(PREVIEW_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        print(f"\n✅ 已生成预览文件: {PREVIEW_FILE}")
        print(f"   请在浏览器中打开此文件以进行人工检查。")

if __name__ == "__main__":
    main()
