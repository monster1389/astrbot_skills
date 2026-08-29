#!/usr/bin/env python3
"""图片转 PDF：把多张图片拼成 PDF 相册（每页一张，保留原比例）。

用途：图片发送管线的一部分。当合并转发插件不可用或图片数量超过阈值时，
用本脚本把图片集拼成 PDF，便于 QQ 直接预览翻页。

用法：
    python3 images_to_pdf.py --output out.pdf --images a.webp b.webp c.jpg
    python3 images_to_pdf.py --output out.pdf --dir /path/to/images/
    python3 images_to_pdf.py --output out.pdf --dir /path/ --images extra.webp

参数：
    -o, --output       PDF 输出路径（必填，建议 .pdf 后缀）
    -i, --images       图片文件路径列表（可多个，与 --dir 可混用）
    -d, --dir          图片目录：取目录下全部图片，按文件名自然排序
    --min-width        过滤低于此宽度(px)的缩略图，默认 200（跳过小图）
    --resolution       PDF 嵌入 DPI，默认 110
    --page-rows        每页行数（>1 时网格排版），默认 1
    --page-cols        每页列数（>1 时网格排版），默认 1
"""

import argparse
import os
import re
import sys
import time

from PIL import Image


def natural_key(name: str) -> list:
    """文件名自然排序：把数字段转成 int，使 2 < 10 < 100。"""
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r"(\d+)", name)]


def collect_images(images: list[str], directory: str | None, min_width: int) -> list[str]:
    """收集并过滤图片路径，返回按自然序排好的列表。"""
    paths: list[str] = []
    if directory and os.path.isdir(directory):
        for f in os.listdir(directory):
            fp = os.path.join(directory, f)
            if os.path.isfile(fp):
                paths.append(fp)
    for p in images or []:
        if os.path.isfile(p):
            paths.append(p)
    if not paths:
        print("错误：未收集到任何有效图片路径。", file=sys.stderr)
        sys.exit(2)
    # 去重 + 按文件名自然排序
    unique = sorted(set(paths), key=lambda p: natural_key(os.path.basename(p)))
    # 过滤非图片与小图
    keep: list[str] = []
    for p in unique:
        try:
            with Image.open(p) as im:
                if im.width >= min_width:
                    keep.append(p)
        except Exception:
            pass
    if not keep:
        print(f"错误：过滤后没有图片（min-width={min_width} 过滤掉了全部）。", file=sys.stderr)
        sys.exit(2)
    return keep


def build_pdf(paths: list[str], output: str, resolution: int,
              rows: int, cols: int) -> int:
    """拼 PDF：默认每页一张；rows/cols>1 时按网格排版。返回页数。"""
    pages: list[Image.Image] = []
    if rows <= 1 and cols <= 1:
        pages = [Image.open(p).convert("RGB") for p in paths]
    else:
        # 网格模式：先算出每页的格子大小，缩放填格
        thumbs = [Image.open(p).convert("RGB") for p in paths]
        cell_w = max(im.width for im in thumbs)
        cell_h = max(im.height for im in thumbs)
        per_page = rows * cols
        for i in range(0, len(thumbs), per_page):
            batch = thumbs[i:i + per_page]
            page = Image.new("RGB", (cell_w * cols, cell_h * rows), (0, 0, 0))
            for idx, im in enumerate(batch):
                # 等比缩放到格子内
                im.thumbnail((cell_w, cell_h))
                x = (idx % cols) * cell_w
                y = (idx // cols) * cell_h
                page.paste(im, (x, y))
            pages.append(page)
    if not pages:
        print("错误：无页面可输出。", file=sys.stderr)
        sys.exit(2)
    pages[0].save(output, save_all=True, append_images=pages[1:],
                  resolution=resolution)
    return len(pages)


def validate(output: str) -> int:
    """用 pypdf 复核输出 PDF 页数。"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(output)
        return len(reader.pages)
    except Exception as e:
        print(f"警告：pypdf 校验失败（{e}）", file=sys.stderr)
        return -1


def main() -> None:
    ap = argparse.ArgumentParser(description="图片转 PDF 相册")
    ap.add_argument("-o", "--output", default=None,
                    help="PDF 输出路径（默认：当前目录 images_<时间戳>.pdf）")
    ap.add_argument("-i", "--images", nargs="*", default=[], help="图片文件路径列表")
    ap.add_argument("-d", "--dir", default=None, help="图片目录路径")
    ap.add_argument("--min-width", type=int, default=200, help="过滤小于此宽度的图(px)")
    ap.add_argument("--resolution", type=int, default=110, help="PDF DPI")
    ap.add_argument("--page-rows", type=int, default=1, help="每页行数")
    ap.add_argument("--page-cols", type=int, default=1, help="每页列数")
    args = ap.parse_args()

    # 未指定输出时：默认当前工作目录 + 自动文件名（配合输出目录约定）
    if not args.output:
        ts = time.strftime("%Y%m%d_%H%M%S")
        args.output = f"images_{ts}.pdf"

    paths = collect_images(args.images, args.dir, args.min_width)
    print(f"待拼图片：{len(paths)} 张")
    pages = build_pdf(paths, args.output, args.resolution,
                      args.page_rows, args.page_cols)
    checked = validate(args.output)
    size_kb = os.path.getsize(args.output) // 1024
    print(f"PDF 生成完成：{args.output}")
    print(f"页数：{pages}（pypdf 复核：{checked}） 大小：{size_kb}KB")
    sys.exit(0 if checked == pages else 1)


if __name__ == "__main__":
    main()
