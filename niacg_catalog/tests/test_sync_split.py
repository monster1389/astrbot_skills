"""sync 拆分红卡：sync_meta（纯列表页，不碰详情页）+ enrich_pending（并发补详情页）。

2026-08-30 拍板：全量建库不做详情页补全（18,000 详情页请求 → 9h 不可接受），
改为「列表页并发入库 + 预览时懒补」两段式。详情页补全只针对真正要预览那批。
"""

import sqlite3
from pathlib import Path
from conftest import FIXTURES_DIR
from migrate import init_db
from sync_metadata import sync_meta, enrich_pending, sync_multi

PAGE = (FIXTURES_DIR / "sample_page.html").read_text(encoding="utf-8")
DETAIL_149343 = (FIXTURES_DIR / "detail_149343.html").read_text(encoding="utf-8")
DETAIL_730 = (FIXTURES_DIR / "detail_730.html").read_text(encoding="utf-8")


def _conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


# ---------------- sync_meta：纯列表页，不碰详情页 ----------------

def test_sync_meta_only_list_page_no_detail(monkeypatch, tmp_path):
    """sync_meta 只拉列表页、不调详情页；落库后 date/pages 留空。"""
    conn = _conn(tmp_path)
    called_detail = {"n": 0}

    def fake_detail(pid):
        called_detail["n"] += 1
        return DETAIL_730

    n = sync_meta(conn, page=0, photos_dir="", f_list=lambda page: PAGE,
                  f_detail=fake_detail)
    assert n >= 1
    # 关键：不调用详情页补全（懒补只在预览时做）
    assert called_detail["n"] == 0, f"sync_meta 不应进详情页，实调 {called_detail['n']} 次"
    # date 留空（待懒补）；preview_urls 用列表页封面
    row = conn.execute("SELECT date,pages,preview_urls,pdfed,pulled FROM albums WHERE id=149343").fetchone()
    assert row is not None
    assert row[0] == "", f"sync_meta 不应补 date，实为 {row[0]}"
    assert row[1] is None, f"sync_meta 不应补 pages，实为 {row[1]}"
    assert row[2] != "", "preview_urls 应含列表页封面"
    assert row[3] == 0 and row[4] == 0, "new 套 pdfed/pulled 应为 0"


def test_sync_meta_incremental_stops_at_existing(tmp_path):
    """增量：撞到库中已有 pid 即停，不补详情页。"""
    conn = _conn(tmp_path)
    # 先插入一个较新的 pid，模拟库中已有
    conn.execute("INSERT INTO albums (id,classid,title) VALUES (149343,1,'t')")
    conn.commit()

    def fake_detail(pid):
        raise AssertionError("sync_meta 不应进详情页")

    n = sync_meta(conn, page=0, photos_dir="", f_list=lambda page: PAGE,
                  f_detail=fake_detail)
    # sample_page 仅有 2 套（149343, 730/149344 之一），首个即撞库 → 无新增
    assert n == 0


# ---------------- enrich_pending：并发补详情页 ----------------

def test_enrich_pending_backfills_date_pages_tags(monkeypatch, tmp_path):
    """enrich_pending 对指定 pids 并发补 date/pages/tags 并回写库。"""
    conn = _conn(tmp_path)
    # 预置 2 套（对应两个详情页 fixture）
    conn.execute("INSERT INTO albums (id,classid,title,date) VALUES (730,1,'t','')")
    conn.execute("INSERT INTO albums (id,classid,title,date) VALUES (149343,1,'t','')")
    conn.commit()

    detail_map = {730: DETAIL_730, 149343: DETAIL_149343}
    def fake_detail(pid):
        return detail_map[pid]

    n = enrich_pending(conn, [730, 149343], f_detail=fake_detail, concurrency=4)
    assert n == 2
    # 两套各自的 date 都补上
    assert conn.execute("SELECT date FROM albums WHERE id=730").fetchone()[0] == "2022-06-08"
    assert conn.execute("SELECT date FROM albums WHERE id=149343").fetchone()[0] == "2026-08-26"


def test_enrich_pending_skips_missing_pid(tmp_path):
    """库中不存在 pid 时跳过（容忍库外套），不影响已存在 pid 的补全。"""
    conn = _conn(tmp_path)
    conn.execute("INSERT INTO albums (id,classid,title,date) VALUES (730,1,'t','')")
    conn.commit()

    def fake_detail(pid):
        return DETAIL_730

    n = enrich_pending(conn, [730, 99999], f_detail=fake_detail, concurrency=4)
    assert n == 1, f"应只补全库中存在的 730，实为 {n}"
    assert conn.execute("SELECT date FROM albums WHERE id=730").fetchone()[0] == "2022-06-08"


# ---------------- sync_multi：并发翻页 + 撞停 ----------------

def test_sync_multi_loads_multiple_pages(tmp_path):
    """sync_multi 并发抓 start_page 起共 pages 页，全部入库。"""
    conn = _conn(tmp_path)

    # 为 page0 造一份含 2 套、page1 也含 2 套的 HTML（pid 递减：新→旧）
    def fake_list(page):
        if page == 0:
            return (
                '<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">'
                '<a href="/moehome-1-2000.html" title="A - X">'
                '<img data-src="https://boom.xunge.cyou/slthh/2026/08/26/1/0_a.webp">'
                '</a></div>'
                '<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">'
                '<a href="/moehome-1-2001.html" title="B - Y">'
                '<img data-src="https://boom.xunge.cyou/slthh/2026/08/26/1/0_b.webp">'
                '</a></div>'
            )
        return (
            '<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">'
            '<a href="/moehome-1-1000.html" title="C - Z">'
            '<img data-src="https://boom.xunge.cyou/slthh/2026/08/26/1/0_c.webp">'
            '</a></div>'
        )

    n = sync_multi(conn, start_page=0, pages=2, photos_dir="",
                   concurrency=2, f_list=fake_list)
    assert n == 3, f"应入库 3 套（page0 两套 + page1 一套），实为 {n}"
    cnt = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    assert cnt == 3


def test_sync_multi_stops_when_hit_existing(tmp_path):
    """撞到库中已有 pid 即停：page0 首个 pid 已在库 → 无新增，且不抓后续页。"""
    conn = _conn(tmp_path)
    # 预置 1000 已在库（模拟更早页已入）
    conn.execute("INSERT INTO albums (id,classid,title) VALUES (1000,1,'t')")
    conn.commit()

    # 每个 page 都返回首个 pid=1000 → page0 即撞停
    def fake_list(page):
        return (
            '<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">'
            '<a href="/moehome-1-1000.html" title="A - X">'
            '<img data-src="https://boom.xunge.cyou/slthh/2026/08/26/1/0_a.webp">'
            '</a></div>'
        )

    n = sync_multi(conn, start_page=0, pages=3, photos_dir="",
                   concurrency=1, f_list=fake_list)
    assert n == 0, f"首个 pid 已在库，应无新增，实为 {n}"
