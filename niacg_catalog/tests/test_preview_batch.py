"""preview_batch 表红卡：预览批次映射（batch_id + seq → album_id/title/model）。

用户挑第几套 → 查 (batch_id, seq) 拿 album_id(=albums.id) → 下载。表在 migrate.init_db 建。
"""

import sqlite3
from migrate import init_db

# COLUMNS for PRAGMA check
BATCH_COLS = {
    "batch_id": ("TEXT", 0),
    "seq":      ("INTEGER", 0),
    "album_id": ("INTEGER", 0),
    "title":    ("TEXT", 0),
    "model":    ("TEXT", 0),
}


def _cols(conn):
    return {r[1] for r in conn.execute("PRAGMA table_info('preview_batch')")}


def test_init_db_creates_preview_batch_table(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    names = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    assert "preview_batch" in names
    conn.close()


def test_preview_batch_schema(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info('preview_batch')")}
    assert set(cols.keys()) >= set(BATCH_COLS.keys()), \
        f"缺列: {set(BATCH_COLS.keys()) ^ set(cols.keys())}"
    conn.close()


def test_preview_batch_primary_key_composite(tmp_path):
    conn = init_db(str(tmp_path / "t.db"))
    pk = conn.execute("PRAGMA table_info('preview_batch')").fetchall()
    pk_cols = [r[1] for r in pk if r[5] > 0]
    assert pk_cols == ["batch_id", "seq"], f"复合主键应为 (batch_id, seq)，实为 {pk_cols}"
    conn.close()


def test_preview_batch_insert_and_query(tmp_path):
    """存一条映射，按 (batch_id, seq) 查 album_id。"""
    conn = init_db(str(tmp_path / "t.db"))
    conn.execute(
        "INSERT INTO preview_batch (batch_id,seq,album_id,title,model) "
        "VALUES (?,?,?,?,?)", ("20260830_2111", 3, 149223, "T", "M"))
    conn.commit()
    album_id = conn.execute(
        "SELECT album_id FROM preview_batch WHERE batch_id=? AND seq=?",
        ("20260830_2111", 3)).fetchone()[0]
    assert album_id == 149223
    conn.close()


def test_migrate_pid_to_album_id(tmp_path):
    """历史库 preview_batch 用旧列 pid；init_db 后应 RENAME 成 album_id（数据无损）。"""
    db = tmp_path / "t.db"
    conn = sqlite3.connect(str(db))
    # 模拟历史库：旧结构 preview_batch 表（列名 pid）
    conn.execute(
        "CREATE TABLE preview_batch (batch_id TEXT NOT NULL, seq INTEGER NOT NULL, "
        "pid INTEGER NOT NULL, title TEXT, model TEXT, "
        "PRIMARY KEY (batch_id, seq))")
    conn.execute(
        "INSERT INTO preview_batch VALUES ('20260830_2111', 3, 149223, 'T', 'M')")
    conn.commit()
    conn.close()

    conn2 = init_db(str(db))   # IF NOT EXISTS 跳过建表，走迁移 RENAME
    cols = {r[1] for r in conn2.execute("PRAGMA table_info('preview_batch')")}
    assert "album_id" in cols, "迁移后应含 album_id"
    assert "pid" not in cols, "迁移后不应再含 pid"
    album_id = conn2.execute(
        "SELECT album_id FROM preview_batch WHERE batch_id=? AND seq=?",
        ("20260830_2111", 3)).fetchone()[0]
    assert album_id == 149223, "迁移后数据应无损"
    conn2.close()
