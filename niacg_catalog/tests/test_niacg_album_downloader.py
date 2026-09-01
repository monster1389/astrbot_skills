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


# ---------------- build_out_dir（归档路径：模特→套 两级 + unclassified 兜底） ----------------

def test_build_out_dir_two_level():
    """给了真实模特 → photos/{模特}/{套名} 两级。"""
    got = build_out_dir("/root/photos", "Machi", "Cyrene_105P")
    assert got == "/root/photos/Machi/Cyrene_105P", got


def test_build_out_dir_unclassified_for_empty_model():
    """model 为空 → 落 unclassified/{套名}（不明确模特统一兜底）。"""
    got = build_out_dir("/root/photos", "", "Cyrene_105P")
    assert got == "/root/photos/unclassified/Cyrene_105P", got


def test_build_out_dir_unclassified_for_none_model():
    """--model 未指定（None）→ 落 unclassified/{套名}。"""
    got = build_out_dir("/root/photos", None, "Masked Shojo")
    assert got == "/root/photos/unclassified/Masked Shojo", got


def test_build_out_dir_unclassified_for_chinese_unclass():
    """model 为「未分类」占位 → 归一化到 unclassified/{套名}。"""
    got = build_out_dir("/root/photos", "未分类", "Cyrene_105P")
    assert got == "/root/photos/unclassified/Cyrene_105P", got


def test_build_out_dir_unclassified_for_unknown():
    """model 为「未知」→ 归一化到 unclassified/{套名}。"""
    got = build_out_dir("/root/photos", "未知", "Cyrene_105P")
    assert got == "/root/photos/unclassified/Cyrene_105P", got


def test_build_out_dir_handles_title_with_special_chars():
    """套名含空格/中括号等（不做 sanitize，交给调用方），仅拼接。"""
    got = build_out_dir("/root/photos", "张雪馨", "Edison 合作 41P")
    assert got == "/root/photos/张雪馨/Edison 合作 41P", got


# ---------------- C7：resolve_model（override 优先，否则白名单判定） ----------------

def test_resolve_model_override_wins():
    """给了 override → 直接用，不查白名单。"""
    whitelist = {"Rikachan", "Machi"}
    assert dl.resolve_model("Machi", "Rikachan - Yae Miko", whitelist) == "Machi"


def test_resolve_model_no_override_whitelist_hit():
    """没给 override → 走 extract_model 白名单精确匹配，命中返回模特名。"""
    whitelist = {"Rikachan"}
    assert dl.resolve_model(None, "Rikachan - Yae Miko", whitelist) == "Rikachan"


def test_resolve_model_no_override_unclassified():
    """没给 override 且未命中白名单 → 未分类。"""
    whitelist = {"Rikachan"}
    assert dl.resolve_model(None, "Nookkiizz - Koharu", whitelist) == "未分类"


def test_resolve_model_override_empty_string_is_falsy():
    """override 为空串 → 视为未给，走白名单判定（同 None）。"""
    whitelist = {"Rikachan"}
    assert dl.resolve_model("", "Rikachan - Yae Miko", whitelist) == "Rikachan"


# ---------------- C4：parse_set（删旧格式兼容） ----------------

import pytest
from unittest import mock
import niacg_album_downloader as dl


def test_parse_set_three_segment():
    """只支持 名字:classid:pid 三字段。"""
    assert dl.parse_set("套名:1:149223") == ("套名", "1", "149223")


def test_parse_set_no_legacy_gid_translate():
    """不再把旧格式 名字:pid:gid 的 gid 特判为 classid=4（删旧格式兼容）。"""
    assert dl.parse_set("套名:123:4567890123") == ("套名", "123", "4567890123")


def test_parse_set_bad_format_raises():
    """字段数/非数字 → 明确报错。"""
    with pytest.raises(SystemExit):
        dl.parse_set("bad")


# ---------------- C2：_download_one 失败需留诊断 ----------------

def test_download_one_failure_prints_diag(tmp_path, capsys):
    """下载异常：返回 False，且 stderr 带 URL+原因（不静默吞）。"""
    with mock.patch.object(dl.httpx, "get", side_effect=Exception("boom")):
        ok = dl._download_one("http://x/1.jpg", str(tmp_path), 0)
    assert ok is False
    err = capsys.readouterr().err
    assert "boom" in err and "1.jpg" in err


# ---------------- C3：collect_urls 空页应明确报错 ----------------

def test_collect_urls_empty_raises():
    """页面无主图 URL → raise RuntimeError（而非静默返回空）。"""
    with mock.patch.object(dl.httpx, "get") as m:
        resp = mock.Mock()
        resp.status_code = 200
        resp.text = "<html>no img here</html>"
        m.return_value = resp
        with pytest.raises(RuntimeError):
            dl.collect_urls("1", "149223")


# ---------------- MAIN_IMG_RE：img2/datu 老套主图 ----------------

def test_main_img_re_matches_img2_datu():
    """img2.xunge.cyou/datu/（2022 老套主图）应被 MAIN_IMG_RE 命中。"""
    for attr in ("src", "data-src"):
        html = (f'<img {attr}="https://img2.xunge.cyou/datu/1487/16/1195abc.jpg">')
        m = dl.MAIN_IMG_RE.search(html)
        assert m and m.group(1) == "https://img2.xunge.cyou/datu/1487/16/1195abc.jpg", (attr, m)
