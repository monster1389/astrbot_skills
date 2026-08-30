"""migrate — 建库/建表/schema 迁移。

只负责数据库结构的创建与演进，与「拉量」「抓取」分离（AGENT.md §4 解耦原则）。
"""

from __future__ import annotations

import sqlite3


# albums 表 schema，对照 design.md §5.1。
# 注：pdfed/pulled 用 NOT NULL DEFAULT 0，其余字段允许 NULL（元数据可能缺失）。
SCHEMA = """
CREATE TABLE IF NOT EXISTS albums (
    id          INTEGER PRIMARY KEY,        -- 站内 pid
    classid     INTEGER,                    -- 1=COS 板，4=套图板
    title       TEXT,
    model       TEXT,
    tags        TEXT,                       -- JSON 数组或逗号分隔
    pages       INTEGER,                    -- 张数（主图数），列表页查不到，下载后可回填
    cover_url   TEXT,
    preview_urls TEXT,                  -- 缩略图 URL JSON 列表（详情页 slthh 补全）
    date        TEXT,                   -- 发布日期（详情页 datePublished）
    spicy       TEXT,                       -- 荤/擦边/素/未分类
    pdfed       INTEGER NOT NULL DEFAULT 0, -- 0=未看过 / 1=拼过预览 PDF
    pulled      INTEGER NOT NULL DEFAULT 0, -- 0=未拉整套 / 1=已拉整套归档
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS preview_batch (
    batch_id    TEXT NOT NULL,              -- 预览批次标识（时间戳 YYYYMMDD_HHMM）
    seq         INTEGER NOT NULL,           -- 批内序号（1..限 60）
    album_id    INTEGER NOT NULL,           -- 指向 albums.id（站内套图 id，路由到下载）
    title       TEXT,                       -- 该套标题（展示/确认用）
    model       TEXT,                       -- 该套模特（展示/确认用）
    PRIMARY KEY (batch_id, seq)
);
"""


def _migrate_preview_batch_pid(conn: sqlite3.Connection) -> None:
    """把历史 preview_batch 表的 `pid` 列重命名为 `album_id`（SQLite 3.25+ 支持 RENAME COLUMN）。

    仅做 schema 对齐、不触碰数据。幂等：仅当存在 `pid` 列且不存在 `album_id` 列时执行，
    重复调用安全（已迁过则跳过，新库本就用 album_id 也不会误改）。
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info('preview_batch')")}
    if "pid" in cols and "album_id" not in cols:
        conn.execute("ALTER TABLE preview_batch RENAME COLUMN pid TO album_id")


def init_db(db_path: str) -> sqlite3.Connection:
    """创建/打开主库并确保 `albums`、`preview_batch` 表存在，对齐历史命名。

    Args:
        db_path: SQLite 数据库文件路径。

    Returns:
        连接对象（已建表、已迁移，事务已提交）。

    Raises:
        sqlite3.Error: 建表/迁移失败时抛出。
    """
    conn = sqlite3.connect(db_path)
    for stmt in SCHEMA.split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    _migrate_preview_batch_pid(conn)
    conn.commit()
    return conn
