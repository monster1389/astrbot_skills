"""S2/S3/S4 卡：sync_metadata 解析/增量/落库 的 pytest 红卡测试。

fixture 用实测提取的真实卡片块（tests/fixtures/sample_page.html）。
model 走向：标题抽候选 → 白名单(现有 photos/ 模特目录)归一化精确匹配，
            命中用白名单名，未命中归「未分类」。
"""
import re
import sqlite3
from pathlib import Path

import pytest

from conftest import FIXTURES_DIR
from sync_metadata import extract_candidate, extract_model

PAGE = (FIXTURES_DIR / "sample_page.html").read_text(encoding="utf-8")


# ---------------- extract_candidate（纯候选抽取） ----------------

def test_extract_candidate_splits_on_dash():
    """优先按 ' - ' 分割，取左段。"""
    assert extract_candidate("Nookkiizz - Koharu") == "Nookkiizz"


def test_extract_candidate_splits_on_double_space():
    """无 ' - ' 时按双空格分割，取左段。"""
    assert extract_candidate("Mercurius-i (露)  珍珠号") == "Mercurius-i"


def test_extract_candidate_no_separator_whole():
    """无分隔符时整串作候选。"""
    assert extract_candidate("SomeTitleNoSep") == "SomeTitleNoSep"


def test_extract_candidate_strips_parenthesis():
    """归一化：剥离括号内容与首尾符号。"""
    assert extract_candidate("Luniie (루니) - Xxx") == "Luniie"


# ---------------- extract_model（白名单匹配） ----------------

def test_extract_model_whitelist_exact_hit():
    """候选与白名单归一化后精确相等 → 返回白名单名。"""
    whitelist = {"Rikachan", "Tsubaki", "狐狸小妖"}
    assert extract_model("Rikachan - Yae Miko", whitelist) == "Rikachan"


def test_extract_model_whitelist_no_match_unclassified():
    """候选不在白名单 → 未分类。"""
    whitelist = {"Rikachan", "Tsubaki"}
    assert extract_model("Nookkiizz - Koharu", whitelist) == "未分类"


def test_extract_model_empty_candidate_unclassified():
    """剥光后候选为空 → 未分类。"""
    assert extract_model("(C108)  珍珠号", {"Tsubaki"}) == "未分类"


def test_extract_model_photographer_team_unclassified():
    """摄影师团队不在白名单（白名单是模特目录）→ 未分类。"""
    whitelist = {"Tsubaki", "Rikachan"}
    assert extract_model("DJAWA Photo - Swimming Lessons", whitelist) == "未分类"


# ---------------- S2：parse_list_page ----------------

def test_parse_list_page_returns_list():
    from sync_metadata import parse_list_page
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    assert isinstance(albums, list)
    assert len(albums) == 2


def test_parse_list_page_fields_from_real_card():
    from sync_metadata import parse_list_page
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    a = albums[0]
    assert a.pid == 149343
    assert a.title == "DJAWA Photo Luniie (\ub8e8\ub2c8) - Swimming Lessons Sunna"
    assert a.cover_url == "https://boom.xunge.cyou/slthh/2026/08/26/1787716844/0_129873a9.webp"
    assert "绝区零" in a.tags
    assert "sunna" in a.tags
    assert a.classid == 1


def test_parse_list_page_date_left_empty_for_detail_enrich():
    """date 列表页阶段留空，交由详情页 enrich_from_detail 补全。"""
    from sync_metadata import parse_list_page
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    a = albums[0]
    assert a.date == "", f"列表页阶段 date 应为空（待详情页补），实为 {a.date}"


def test_parse_list_page_model_from_title_via_whitelist():
    """model 由标题抽候选 + 白名单精确匹配；命中则用白名单名。"""
    from sync_metadata import parse_list_page
    # 含 DJAWA Photo（团队）但候选剥括号后为 Luniie，白名单无 Luniie → 未分类
    albums = parse_list_page(PAGE, classid=1, whitelist={"Rikachan"})
    assert albums[0].model == "未分类"


def test_parse_list_page_model_hit_whitelist():
    """候选命中白名单 → 用白名单名（目录名）。"""
    from sync_metadata import parse_list_page
    block = (
        '<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">'
        '<a href="/moehome-1-99999.html" title="Rikachan - Yae Miko">'
        '<img data-src="https://boom.xunge.cyou/slthh/2026/08/26/1787716844/0_x.webp">'
        '</a></div>'
    )
    albums = parse_list_page(block, classid=1, whitelist={"Rikachan"})
    assert albums[0].model == "Rikachan"


def test_parse_list_page_pages_is_none():
    from sync_metadata import parse_list_page
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    assert albums[0].pages is None


def test_parse_list_page_preview_urls_default_cover():
    """列表页阶段 preview_urls 至少含封面 URL（单张）；真正多张缩略图后续补。"""
    from sync_metadata import parse_list_page
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    a = albums[0]
    assert a.preview_urls == a.cover_url, f"preview_urls 初值应=封面 URL，实为 {a.preview_urls}"


# ---------------- S5：详情页补全（enrich_from_detail） ----------------

DETAIL_149343 = (FIXTURES_DIR / "detail_149343.html").read_text(encoding="utf-8")
DETAIL_730 = (FIXTURES_DIR / "detail_730.html").read_text(encoding="utf-8")


def test_enrich_from_detail_returns_date_pages_previews_tags():
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    assert set(d.keys()) >= {"date", "pages", "preview_urls", "tags"}


def test_enrich_from_detail_date_from_datepublished():
    """date 来自详情页 datePublished（上架日期），非封面时间戳。"""
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    assert d["date"] == "2022-06-08"   # 旧套上架日期实测值
    d2 = enrich_from_detail(DETAIL_149343)
    assert d2["date"] == "2026-08-26"  # 新套上架日期实测值


def test_enrich_from_detail_pages_from_pagecount():
    """pages 来自详情页「页数」字段。"""
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    assert d["pages"] == 22


def test_enrich_from_detail_preview_urls_uses_cover_planA():
    """方案A：preview_urls 恒用列表页封面 cover_url，详情页 enrich 不回填。"""
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    # enrich 不再抓缩略图（slthh 是推荐位、hen/d_file 是原图），preview_urls 置空由列表页封面承担
    assert d["preview_urls"] == "", "方案A下详情页不回填 preview_urls（恒用列表页封面）"
    assert "slthh" not in d["preview_urls"], "不应含推荐位 slthh"
    assert "hen" not in d["preview_urls"] and "d/file" not in d["preview_urls"], "不应含原图"


def test_enrich_from_detail_date_pages_tags_still_work():
    """方案A仍保留 date/pages/tags 补全能力（详情页照常补这三样）。"""
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    assert d["date"] == "2022-06-08"
    assert d["pages"] == 22
    assert d["tags"] != ""


def test_enrich_from_detail_tags_from_detail_page():
    """tags 来自详情页（比列表页更全）。"""
    from sync_metadata import enrich_from_detail
    d = enrich_from_detail(DETAIL_730)
    assert "绝区零" in d["tags"] or d["tags"] != ""


# ---------------- S6：sync 编排（注入 fake 抓取，不打真实网络） ----------------

def test_sync_injects_list_and_detail(monkeypatch, tmp_path):
    """sync 用注入的 f_list/f_detail 跑通「列表→详情→增量→落库」闭环，不打网络。

    fake 详情页按 pid 返回对应 fixture，验证「每套拿到自己的详情页数据」。
    """
    from sync_metadata import sync_meta, enrich_pending
    from migrate import init_db

    conn = init_db(str(tmp_path / "t.db"))
    # fake 详情页：按 pid 映射到真实 fixture
    detail_map = {
        149343: (FIXTURES_DIR / "detail_149343.html").read_text(encoding="utf-8"),
        730: (FIXTURES_DIR / "detail_730.html").read_text(encoding="utf-8"),
    }

    def fake_detail(pid):
        # 若 sample_page 里的 pid 不在 map，回退用 730 的（保证不崩）
        return detail_map.get(pid, detail_map[730])

    # 两段式：① sync_meta 只拉列表页入库（date 留空）→ ② enrich_pending 懒补
    n = sync_meta(conn, page=0, photos_dir="",
                  f_list=lambda page: PAGE, f_detail=fake_detail)

    cnt = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    assert cnt >= 1, "应至少写入 1 条"
    # ① 阶段：sync_meta 不补 date
    row0 = conn.execute("SELECT date FROM albums WHERE id=149343").fetchone()
    assert row0[0] == "", f"sync_meta 不应补 date，实为 {row0[0]}"

    # ② 阶段：enrich_pending 并发补 date/pages/tags
    pids = [r[0] for r in conn.execute("SELECT id FROM albums")]
    enrich_pending(conn, pids, f_detail=fake_detail, concurrency=4)
    row = conn.execute(
        "SELECT date,pages,preview_urls,tags FROM albums WHERE id=149343").fetchone()
    assert row is not None, "149343 应已落库"
    assert row[0] == "2026-08-26", f"149343 date 应补齐为 2026-08-26，实为 {row[0]}"
    assert row[1] == 22, f"149343 pages 应补齐为 22，实为 {row[1]}"


# ---------------- S3：select_new ----------------

def test_select_new_stops_at_existing_pid():
    from sync_metadata import parse_list_page, select_new
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    existing = {albums[1].pid}
    new = select_new(albums, existing)
    assert [a.pid for a in new] == [albums[0].pid], new


def test_select_new_all_when_empty_db():
    from sync_metadata import parse_list_page, select_new
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    new = select_new(albums, set())
    assert len(new) == 2


def test_select_new_none_when_all_exist():
    from sync_metadata import parse_list_page, select_new
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    existing = {a.pid for a in albums}
    new = select_new(albums, existing)
    assert new == []


# ---------------- S4：upsert_albums ----------------

def _init_conn(tmp_path):
    from migrate import init_db
    return init_db(str(tmp_path / "t.db"))


def test_upsert_albums_inserts_new(tmp_path):
    from sync_metadata import parse_list_page, upsert_albums
    conn = _init_conn(tmp_path)
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    n = upsert_albums(conn, albums)
    assert n == 2
    cnt = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    assert cnt == 2


def test_upsert_albums_updates_existing_pid(tmp_path):
    from sync_metadata import parse_list_page, upsert_albums
    conn = _init_conn(tmp_path)
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    upsert_albums(conn, albums)
    albums[0].title = "NEW_TITLE"
    n = upsert_albums(conn, albums)
    cnt = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    assert cnt == 2, f"应覆盖不重复，实为 {cnt}"
    db_title = conn.execute("SELECT title FROM albums WHERE id=?", (albums[0].pid,)).fetchone()[0]
    assert db_title == "NEW_TITLE"


def test_upsert_albums_preserves_pdfed_pulled(tmp_path):
    from sync_metadata import parse_list_page, upsert_albums
    conn = _init_conn(tmp_path)
    albums = parse_list_page(PAGE, classid=1, whitelist=set())
    upsert_albums(conn, albums)
    conn.execute("UPDATE albums SET pdfed=1 WHERE id=?", (albums[0].pid,))
    conn.commit()
    upsert_albums(conn, albums)
    row = conn.execute("SELECT pdfed FROM albums WHERE id=?", (albums[0].pid,)).fetchone()
    assert row[0] == 1, f"upsert 不应重置 pdfed，实为 {row[0]}"
