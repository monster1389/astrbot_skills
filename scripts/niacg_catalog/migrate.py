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
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """创建/打开主库并确保 `albums` 表存在。

    Args:
        db_path: SQLite 数据库文件路径。

    Returns:
        连接对象（已建表，未提交事务）。

    Raises:
        sqlite3.Error: 建表失败时抛出。
    """
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn
