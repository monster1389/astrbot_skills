"""S7 卡：build_preview_pdf 的纯逻辑 pytest 红卡。

select_preview: 从 pdfed=0 的 rows 按 date 升序取前 limit 条
mark_pdfed: 把指定 pids 置 pdfed=1

（缩略图下载 + reportlab 拼 PDF 属沾 IO，用活体现测。）
"""
import sqlite3

from migrate import init_db
from build_preview_pdf import select_preview, mark_pdfed


def _conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _seed(conn, rows):
    """rows: list[(pid, date, pdfed)]"""
    for pid, date, pdfed in rows:
        conn.execute(
            "INSERT INTO albums (id,classid,title,date,pdfed,preview_urls) "
            "VALUES (?,1,'t',?,?, '')", (pid, date, pdfed))
    conn.commit()


# ---------------- select_preview ----------------

def test_select_preview_sorts_by_pid_asc():
    """按 pid（=id）升序选取——pid 是站内时间代理，最早在前。"""
    rows = [{"id": 3, "date": "2022-06-08", "pdfed": 0},
            {"id": 1, "date": "2026-08-26", "pdfed": 0},
            {"id": 2, "date": "2023-01-01", "pdfed": 0}]
    got = select_preview(rows, limit=60)
    assert [r["id"] for r in got] == [1, 2, 3], got


def test_select_preview_sorts_by_pid_when_no_date():
    """列表页 phase date 为空，仍按 pid 升序（不因缺 date 乱序/排最后）。"""
    rows = [{"id": 10, "date": "", "pdfed": 0},
            {"id": 8, "date": "", "pdfed": 0},
            {"id": 9, "date": "", "pdfed": 0}]
    got = select_preview(rows, limit=60)
    assert [r["id"] for r in got] == [8, 9, 10], got


def test_select_preview_only_pdfed_zero():
    """只取 pdfed=0（未看过）的套，跳过已置 1 的。"""
    rows = [{"id": 1, "date": "2020-01-01", "pdfed": 1},
            {"id": 2, "date": "2021-01-01", "pdfed": 0}]
    got = select_preview(rows, limit=60)
    assert [r["id"] for r in got] == [2], got


def test_select_preview_limit():
    """超出 limit 时只取前 limit 条。"""
    rows = [{"id": i, "date": f"20{i:02d}-01-01", "pdfed": 0} for i in range(10)]
    got = select_preview(rows, limit=3)
    assert len(got) == 3
    # 最早的 3 条：date 最小的 3 个 id
    assert [r["id"] for r in got] == [0, 1, 2]


def test_select_preview_empty_when_all_pdfed():
    """全部已看过时返回空。"""
    rows = [{"id": 1, "date": "2021-01-01", "pdfed": 1}]
    assert select_preview(rows, limit=60) == []


# ---------------- mark_pdfed ----------------

def test_mark_pdfed_sets_pid(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn, [(10, "2021-01-01", 0), (11, "2021-02-01", 0)])
    n = mark_pdfed(conn, [10])
    assert n == 1
    assert conn.execute("SELECT pdfed FROM albums WHERE id=10").fetchone()[0] == 1
    # 未被标记的保持 0
    assert conn.execute("SELECT pdfed FROM albums WHERE id=11").fetchone()[0] == 0


def test_mark_pdfed_all_pids(tmp_path):
    conn = _conn(tmp_path)
    _seed(conn, [(10, "2021-01-01", 0), (11, "2021-02-01", 0)])
    n = mark_pdfed(conn, [10, 11])
    assert n == 2
    assert conn.execute("SELECT COUNT(*) FROM albums WHERE pdfed=1").fetchone()[0] == 2
