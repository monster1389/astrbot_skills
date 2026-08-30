"""build_preview_pdf — 拼预览 PDF。

查 pdfed=0，按 date 升序从最早取，限额 60，拼预览 PDF（缩略图+标题+date+tags）。
拼成即置 pdfed=1（design.md §3.2）。
PDF 存档到 pdf/（不删）；临时缩略图文件用完即删。
脚本无发送能力，发送由编排层负责。
"""

from __future__ import annotations

import json
import os
import sqlite3
import datetime


# ---------------- S7a：纯逻辑 ----------------

def select_preview(rows: list[dict], limit: int = 60) -> list[dict]:
    """从 pdfed=0 的行中按 date 升序取前 limit 条。

    Args:
        rows: albums 行记录（含 id/date/pdfed 等字段）的列表。
        limit: 最多选取条数，默认 60。

    Returns:
        按 date 升序、且限量的 preview 行列表（仅 pdfed=0）。
    """
    # 只取未看过（pdfed=0）的；按 pid（=id）升序——pid 是站内时间代理，
    # 列表页 phase 无 date 时也可靠地按「最早」取（2026-08-30 实测 pid 与 date 单调同步）
    pending = [r for r in rows if r["pdfed"] == 0]
    pending.sort(key=lambda r: r["id"])
    return pending[:limit]


def mark_pdfed(conn: sqlite3.Connection, pids: list[int]) -> int:
    """把指定 pid 置 pdfed=1。

    Args:
        conn: 已连接的 SQLite 连接。
        pids: 要标记的 pid 列表。

    Returns:
        置位的行数。
    """
    if not pids:
        return 0
    cur = conn.executemany(
        "UPDATE albums SET pdfed=1 WHERE id=?", [(p,) for p in pids])
    conn.commit()
    return cur.rowcount


# ---------------- S7b：IO 层（下载缩略图 + 拼 PDF，活体现测） ----------------

def fetch_preview_image(url: str, dest: str) -> str:
    """下载一张缩略图到本地。

    复用下载器的 httpx + Referer 链路（图床要求 Referer 指向 niacg.com）。

    Args:
        url: 缩略图 URL。
        dest: 本地目标路径。

    Returns:
        本地文件路径。

    Raises:
        httpx.HTTPError: 下载失败时抛出。
    """
    import httpx
    from sync_metadata import PROXY, REF, UA
    r = httpx.get(url, proxy=PROXY, headers={"User-Agent": UA, "Referer": REF}, timeout=25)
    r.raise_for_status()
    with open(dest, "wb") as fp:
        fp.write(r.content)
    return dest


def build_preview(conn: sqlite3.Connection, limit: int = 60,
                  out_dir: str = "/AstrBot/data/niacg_catalog/pdf",
                  tmp_dir: str = "/tmp/niacg_preview") -> str:
    """执行拼预览 PDF 全流程。

    查 pdfed=0 → 按 date 升序取 limit → 下载缩略图 → 拼 PDF → 存档 → 置 pdfed=1。

    Args:
        conn: 已连接的 SQLite 连接。
        limit: 最多拼多少套，默认 60。
        out_dir: PDF 存档目录（pdf/，不删）。
        tmp_dir: 缩略图临时目录（用完即删）。

    Returns:
        生成的 PDF 绝对路径。
    """
    cols = ["id", "title", "date", "tags", "preview_urls", "pdfed"]
    rows = [dict(zip(cols, r)) for r in conn.execute(
        f"SELECT {','.join(cols)} FROM albums")]
    selected = select_preview(rows, limit)
    if not selected:
        raise ValueError("没有 pdfed=0 的可拼套")

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(tmp_dir, exist_ok=True)

    # 下载每套预览图（优先第 1 张缩略图；JSON 数组或单 URL 都支持；下载失败无图）
    images = []
    for row in selected:
        pv = row.get("preview_urls") or ""
        urls = []
        if pv.startswith("["):
            try:
                urls = json.loads(pv)
            except Exception:
                urls = []
        elif pv:
            urls = [pv]          # 单 URL 兜底（旧套封面）
        url = (urls[0] if urls else "")
        img_path = os.path.join(tmp_dir, f"{row['id']}.img")
        if url:
            try:
                fetch_preview_image(url, img_path)
                images.append((row, img_path))
            except Exception:
                images.append((row, ""))   # 下载失败则该套无图，仅文字
        else:
            images.append((row, ""))

    pdf_path = os.path.join(out_dir, f"preview_{datetime.datetime.now():%Y%m%d_%H%M%S}.pdf")
    _render_pdf(images, pdf_path)
    mark_pdfed(conn, [r["id"] for r in selected])

    # 清理临时缩略图
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return pdf_path


def _render_pdf(images: list, pdf_path: str) -> None:
    """用 reportlab 把 (row, img_path) 列表渲染成 PDF。

    images: list[(row_dict, img_path|"")]。每套一行：缩略图 + 标题 + date + tags。
    属活体现测范畴（reportlab 排版）。
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table,
                                    TableStyle, Image)
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # 注册 CJK 字体（标题含中/日文），失败回退 Helvetica
    CJK = "HeiseiMin-W3"
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(CJK))
    except Exception:
        CJK = "Helvetica"

    styles = getSampleStyleSheet()
    cell_s = ParagraphStyle("cell", parent=styles["Normal"], fontName=CJK,
                            fontSize=18, leading=25)

    doc = SimpleDocTemplate(pdf_path, pagesize=A4, margins=10*mm)
    story = []
    for row, img_path in images:
        cells = []
        img_ok = img_path and os.path.exists(img_path)
        # reportlab 对 webp 兼容不稳，用 PIL 统一转成 PNG 再嵌入；
        # 且 d/file/p 抓的是原图(几千像素)，拼 PDF 前缩放到预览尺寸，避免渲染卡慢/体积膨胀
        if img_ok:
            try:
                from PIL import Image as PILImage
                normalized = img_path + ".png"
                with PILImage.open(img_path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((800, 1200))   # 预览用缩略：控制在 ~800px 宽，提速
                    im.save(normalized, "PNG")
                img_ok = os.path.exists(normalized)
                img_path = normalized
            except Exception:
                img_ok = False
        if img_ok:
            cells.append(Image(img_path, width=58*mm, height=76*mm))
        else:
            cells.append(Paragraph("[无图]", cell_s))
        text = Paragraph(f"{row['title']}<br/>{row['date']}<br/>{row['tags']}", cell_s)
        cells.append(text)
        row_tbl = Table([[cells[0], cells[1]]], colWidths=[64*mm, 122*mm])
        row_tbl.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(row_tbl)
        story.append(Paragraph("", cell_s))

    doc.build(story)
