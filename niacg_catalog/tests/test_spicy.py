"""S3：spicy 白名单补漏 —— classify 能识别新补的荤向 tag（当前不在表 → 素，红卡）。"""
import pytest

from spicy import classify, classify_str


@pytest.mark.parametrize("tag", ["露穴", "大乳晕", "阿黑顏"])
def test_classify_spicy_whitelist_after_backfill(tag):
    """新补进荤白名单的 tag 应判「荤」；实装前这些在表外 → 全判「素/未知」，故为红。

    真值来源：这三个 tag 均为明确荤向，命中即「荤」（荤优先规则）。
    """
    assert classify([tag])[0] == "荤", f"{tag} 应在荤白名单命中，实为 {classify([tag])[0]}"


# ---------------- classify_str（字符串 → 档位，含占位符兜底） ----------------

def test_classify_str_normal_tags_to_level():
    """classify_str：正常 tag 字符串 → 判出档位（泳装擦边）。"""
    assert classify_str("绝区零,化妆,泳装,sunna") == "擦边"


def test_classify_str_placeholder_unclassified():
    """classify_str：只剩「无」占位 → 未分类（数据缺失非真素）。"""
    assert classify_str("无") == "未分类"
    assert classify_str("无,,,,,无") == "未分类"


def test_classify_str_empty_unclassified():
    """classify_str：空串 → 未分类。"""
    assert classify_str("") == "未分类"


def test_classify_str_placeholder_ignored_when_valid_present():
    """classify_str：「无」占位与有效 tag 并存时，仍按有效 tag 判（不被占位干扰）。"""
    assert classify_str("无,泳装") == "擦边"
