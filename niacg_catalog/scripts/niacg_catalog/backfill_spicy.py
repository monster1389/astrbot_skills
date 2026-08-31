#!/usr/bin/env python3
"""
backfill_spicy — 存量 spicy 回填：按 tags 重算并回写 spicy 列。

只 UPDATE spicy 一列，不触碰 pdfed/pulled/model/tags/date 等无关字段。
占位符「无」→ 未分类，判定复用 spicy.classify_str（与 sync_metadata 一致）。

用法：
  python backfill_spicy.py --dry-run      # 只统计，不写库
  python backfill_spicy.py                # 正式回填（默认库）
  python backfill_spicy.py --db X.db      # 指定库
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from spicy import classify_str

DEFAULT_DB = "/AstrBot/data/skills/niacg_catalog/catalog/niacg.db"


def backfill(conn: sqlite3.Connection, dry_run: bool = False) -> tuple[int, int, int]:
    """遍历 albums 重算 spicy（只改 spicy 列），返回 (总数, 待改数, 已一致数)。

    Args:
        conn: 已连接的 SQLite 主库。
        dry_run: True 时只统计不写入。

    Returns:
        (总行数, 需更新行数, 已一致行数)。
    """
    cur = conn.cursor()
    rows = cur.execute("SELECT id, tags, spicy FROM albums").fetchall()
    to_update, same = [], 0
    for pid, tags, old in rows:
        new = classify_str(tags)
        if new != old:
            to_update.append((new, pid))
        else:
            same += 1
    if not dry_run and to_update:
        cur.executemany("UPDATE albums SET spicy=? WHERE id=?", to_update)
        conn.commit()
    return len(rows), len(to_update), same


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="存量 spicy 回填（只改 spicy 列）")
    ap.add_argument("--db", default=DEFAULT_DB, help="SQLite 主库路径")
    ap.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    total, updated, same = backfill(conn, dry_run=args.dry_run)
    mode = "[dry-run]" if args.dry_run else "[回填]"
    print(f"{mode} 总数{total} / 需更新{updated} / 已一致{same}")
    if not args.dry_run:
        print(f"已回写 {updated} 行 spicy（只改 spicy 列）")
