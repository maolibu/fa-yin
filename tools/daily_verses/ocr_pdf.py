"""
扫描版 PDF → TXT 文字识别脚本
使用 EasyOCR 识别中文（含繁体）

环境准备（在 ocr 环境中）：
    ~/miniforge3/envs/ocr/bin/pip install easyocr pymupdf

用法：
    python ocr_pdf.py                          # 处理当前目录下所有 PDF
    python ocr_pdf.py 某本书.pdf               # 处理单个文件
    python ocr_pdf.py --dpi 150                # 调整渲染精度（默认 150）
"""

import sys
import argparse
from pathlib import Path

import fitz  # PyMuPDF：将 PDF 页面渲染为图片
import numpy as np
import easyocr


def pdf_to_images(pdf_path: str, dpi: int = 150) -> list[np.ndarray]:
    """将 PDF 每一页渲染为图片（numpy 数组）"""
    doc = fitz.open(pdf_path)
    images = []
    zoom = dpi / 72  # 72 是 PDF 默认 DPI
    matrix = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=matrix)
        # 转为 numpy 数组 (RGB)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
            pix.height, pix.width, pix.n
        )
        # 如果有 alpha 通道，去掉
        if pix.n == 4:
            img = img[:, :, :3]
        images.append(img)
        print(f"  第 {page_num + 1}/{len(doc)} 页已渲染 "
              f"({pix.width}x{pix.height})", flush=True)

    doc.close()
    return images


def ocr_images(images: list[np.ndarray], reader: easyocr.Reader) -> list[str]:
    """对图片列表进行 OCR，返回每页的文字"""
    page_texts = []
    for i, img in enumerate(images):
        # EasyOCR 返回 [(bbox, text, confidence), ...]
        results = reader.readtext(img)

        lines = []
        for (bbox, text, confidence) in results:
            lines.append(text)

        page_text = "\n".join(lines)
        page_texts.append(page_text)
        print(f"  第 {i + 1}/{len(images)} 页 OCR 完成 "
              f"(识别 {len(lines)} 行)", flush=True)

    return page_texts


def process_pdf(pdf_path: str, reader: easyocr.Reader, dpi: int = 150):
    """处理单个 PDF 文件，输出同名 .txt"""
    pdf_path = Path(pdf_path)
    output_path = pdf_path.with_suffix(".txt")

    print(f"\n{'='*60}")
    print(f"正在处理: {pdf_path.name}")
    print(f"输出文件: {output_path.name}")
    print(f"{'='*60}")

    # 第一步：PDF → 图片
    print("\n[1/2] 将 PDF 页面渲染为图片...")
    images = pdf_to_images(str(pdf_path), dpi=dpi)
    print(f"  共 {len(images)} 页")

    # 第二步：图片 → 文字
    print("\n[2/2] 进行 OCR 识别...")
    page_texts = ocr_images(images, reader)

    # 写入文件
    with open(output_path, "w", encoding="utf-8") as f:
        for i, text in enumerate(page_texts):
            f.write(f"--- 第 {i + 1} 页 ---\n")
            f.write(text)
            f.write("\n\n")

    total_chars = sum(len(t) for t in page_texts)
    print(f"\n✅ 完成！共识别 {total_chars} 个字符")
    print(f"   输出文件: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="扫描版 PDF OCR 识别（EasyOCR）"
    )
    parser.add_argument(
        "files", nargs="*",
        help="要处理的 PDF 文件（不指定则处理当前目录下所有 PDF）"
    )
    parser.add_argument(
        "--dpi", type=int, default=150,
        help="渲染 DPI，越高越精确但越慢（默认 150）"
    )
    args = parser.parse_args()

    # 确定要处理的文件
    if args.files:
        pdf_files = [Path(f) for f in args.files]
    else:
        # 自动查找当前目录下的 PDF
        script_dir = Path(__file__).parent
        pdf_files = sorted(script_dir.glob("*.pdf"))

    if not pdf_files:
        print("❌ 没有找到 PDF 文件")
        sys.exit(1)

    print(f"找到 {len(pdf_files)} 个 PDF 文件:")
    for f in pdf_files:
        size_mb = f.stat().st_size / 1024 / 1024
        print(f"  - {f.name} ({size_mb:.1f} MB)")

    # 初始化 EasyOCR（只加载一次模型，支持简繁体中文 + 英文）
    print("\n正在加载 OCR 模型（首次运行需下载约 200MB）...")
    reader = easyocr.Reader(["ch_tra", "en"], gpu=False)
    print("模型加载完成！")

    # 逐个处理
    results = []
    for pdf_file in pdf_files:
        result = process_pdf(str(pdf_file), reader, dpi=args.dpi)
        results.append(result)

    print(f"\n{'='*60}")
    print(f"全部完成！共处理 {len(results)} 个文件:")
    for r in results:
        print(f"  ✅ {r}")


if __name__ == "__main__":
    main()
