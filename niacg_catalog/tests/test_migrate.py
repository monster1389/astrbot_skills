"""S1 卡：migrate.init_db 建表逻辑的 pytest 红卡测试。

对照 design.md §5.1 albums 表结构逐字段断言。
（沾 IO 的 sqlite3 连接本身在这用 tmp_path 建真实库验证 schema）
"""
import sqlite3
import pytest

from migrate import init_db, SCHEMA


def _cols(conn: sqlite3.Connection) -> dict:
    return {r[1]: (r[2], r[3], r[4]) for r in conn.execute("PRAGMA table_info('albums')")}


def test_init_db_creates_albums_table(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(str(db))
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "albums" in names
    conn.close()


def test_albums_schema_matches_design(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(str(db))
    cols = _cols(conn)
    # 期望：列 -> (类型, notnull, default)
    expected = {
        "id":        ("INTEGER", 0, None),        # PK
        "classid":   ("INTEGER", 0, None),
        "title":     ("TEXT",    0, None),
        "model":     ("TEXT",    0, None),
        "tags":      ("TEXT",    0, None),
        "pages":     ("INTEGER", 0, None),
        "cover_url": ("TEXT",    0, None),
        "preview_urls": ("TEXT", 0, None),  # 预览缩略图 URL JSON 列表
        "date":      ("TEXT",    0, None),
        "spicy":     ("TEXT",    0, None),
        "pdfed":     ("INTEGER", 0, "0"),
        "pulled":    ("INTEGER", 0, "0"),
        "updated_at":("TEXT",    0, None),
    }
    assert set(cols.keys()) == set(expected.keys()), f"列不一致: {set(cols.keys())^set(expected.keys())}"
    for col, (typ, notnull, default) in expected.items():
        got_typ, got_notnull, got_default = cols[col]
        assert got_typ.upper() == typ, f"{col} 类型应为 {typ}，实为 {got_typ}"
        assert got_default == default, f"{col} 默认值应为 {default}，实为 {got_default}"


def test_pk_is_id(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(str(db))
    pk = conn.execute("PRAGMA table_info('albums')").fetchall()
    pk_cols = [r[1] for r in pk if r[5] > 0]
    assert pk_cols == ["id"], f"主键应为 id，实为 {pk_cols}"
    conn.close()


def test_pdfed_pulled_default_zero(tmp_path):
    db = tmp_path / "t.db"
    conn = init_db(str(db))
    conn.execute(
        "INSERT INTO albums (id,classid,title,tags) VALUES (1,1,'t','[]')")
    row = conn.execute("SELECT pdfed,pulled FROM albums WHERE id=1").fetchone()
    assert row == (0, 0), f"pdfed/pulled 默认应为 0,0，实为 {row}"
    conn.close()


def test_upsert_semantics_updates_existing(tmp_path):
    """设计要点：以 id=pid 作唯一键，重跑 upsert 应更新而非重复插入。"""
    db = tmp_path / "t.db"
    conn = init_db(str(db))
    # 首次插入
    conn.execute(
        "INSERT INTO albums (id,classid,title,pages) VALUES (42,1,'A',10)")
    # 同 id 更新（模拟 sync 重跑）
    conn.execute(
        "INSERT INTO albums (id,classid,title,pages) VALUES (42,1,'A2',20) "
        "ON CONFLICT(id) DO UPDATE SET title=excluded.title, pages=excluded.pages")
    conn.commit()
    cnt = conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0]
    assert cnt == 1, f"同 id 应覆盖不重复，实为 {cnt}"
    title, pages = conn.execute(
        "SELECT title,pages FROM albums WHERE id=42").fetchone()
    assert (title, pages) == ("A2", 20)
    conn.close()
