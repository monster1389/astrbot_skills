"""下载器改造红卡：sample_evenly（等距抽 n 张）+ mark_pulled（置 pulled=1）。

collect_urls / download 沾 IO，沿用惯例走活体集成测试，不在此测。
"""

import sqlite3

from migrate import init_db
from niacg_album_downloader import sample_evenly, mark_pulled, build_out_dir


def _paths(n):
    return [f"{i:03d}.jpg" for i in range(n)]


# ---------------- sample_evenly ----------------

def test_sample_evenly_returns_n_items():
    """张数足够时等距返回 n 条。"""
    got = sample_evenly(_paths(9), 3)
    assert len(got) == 3, got


def test_sample_evenly_about_equal_spacing():
    """等距覆盖：9 张取 3 → 索引 0,4,8（首尾含）。"""
    got = sample_evenly(_paths(9), 3)
    assert got == ["000.jpg", "004.jpg", "008.jpg"], got


def test_sample_evenly_includes_first_and_last():
    """153 张取 5：起点 000、终点 152 必含（均匀覆盖整套）。"""
    got = sample_evenly(_paths(153), 5)
    assert got[0] == "000.jpg", got
    assert got[-1] == "152.jpg", got


def test_sample_evenly_when_fewer_than_n():
    """张数 <= n 时全取（不足 n 返回全部）。"""
    assert sample_evenly(_paths(4), 5) == _paths(4)


def test_sample_evenly_empty():
    """空列表返回空。"""
    assert sample_evenly([], 5) == []


def test_sample_evenly_n_one():
    """n=1 时返回中间一张（或首张兜底）。"""
    got = sample_evenly(_paths(10), 1)
    assert len(got) == 1, got


# ---------------- mark_pulled ----------------

def _conn(tmp_path):
    return init_db(str(tmp_path / "t.db"))


def _seed(conn, pid):
    conn.execute("INSERT INTO albums (id,classid,title) VALUES (?,1,'t')", (pid,))
    conn.commit()


def test_mark_pulled_sets_pid(tmp_path):
    """存在 pid → 置 pulled=1，返回影响行数 1。"""
    conn = _conn(tmp_path)
    _seed(conn, 10)
    n = mark_pulled(conn, 10)
    assert n == 1, n
    assert conn.execute("SELECT pulled FROM albums WHERE id=10").fetchone()[0] == 1


def test_mark_pulled_missing_pid_returns_zero(tmp_path):
    """库中不存在该 pid → 影响 0 行、不抛错（容忍点名库外套）。"""
    conn = _conn(tmp_path)
    n = mark_pulled(conn, 999)
    assert n == 0, n


# ---------------- build_out_dir（归档路径：模特→套 两级） ----------------

def test_build_out_dir_two_level():
    """给了模特 → photos/{模特}/{套名} 两级。"""
    got = build_out_dir("/root/photos", "Machi", "Cyrene_105P")
    assert got == "/root/photos/Machi/Cyrene_105P", got


def test_build_out_dir_no_model_single_level():
    """未给模特（解析不出）→ 退化单层 photos/{套名}，向后兼容。"""
    got = build_out_dir("/root/photos", "", "Cyrene_105P")
    assert got == "/root/photos/Cyrene_105P", got


def test_build_out_dir_none_model():
    """--model 未指定（None）等同空 → 单层。"""
    got = build_out_dir("/root/photos", None, "Masked Shojo")
    assert got == "/root/photos/Masked Shojo", got


def test_build_out_dir_handles_title_with_special_chars():
    """套名含空格/中括号等（不做 sanitize，交给调用方），仅拼接。"""
    got = build_out_dir("/root/photos", "张雪馨", "Edison 合作 41P")
    assert got == "/root/photos/张雪馨/Edison 合作 41P", got
