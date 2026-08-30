#!/usr/bin/env python3
"""
niacg 套图荤素分级 (spicy)
==========================
从 spicy_tags.json 加载三档 tag 白名单，按「荤优先」规则判定套图档位。

档位：荤 > 擦边 > 素
- 命中任意「荤」tag → 荤
- 否则命中任意「擦边」tag → 擦边
- 否则 → 素（未知 tag 不影响档位，单独返回供人工补档）

配置：spicy_tags.json（同目录），改档位/加 tag 只动 JSON，不动代码。

用法：
  from spicy import classify
  level, spicy_hit, edgy_hit, unknown = classify(["丝袜", "无圣光"])
"""
import json
from pathlib import Path
from typing import Iterable, Tuple

_CFG = Path(__file__).with_name("spicy_tags.json")
with open(_CFG, encoding="utf-8") as _f:
    _DATA = json.load(_f)

SPICY = set(_DATA["spicy"])
EDGY = set(_DATA["edgy"])
SAFE = set(_DATA["safe"])

LEVELS = ("荤", "擦边", "素", "未知")


def classify(tags: Iterable[str], title: str = "") -> Tuple[str, list, list, list]:
    """荤素判定（荤优先）。返回 (档位, 命中荤tag, 命中擦边tag, 未知tag)。"""
    spicy_hit, edgy_hit, unknown = [], [], []
    for t in tags:
        t = (t or "").strip()
        if not t:
            continue
        if t in SPICY:
            spicy_hit.append(t)
        elif t in EDGY:
            edgy_hit.append(t)
        elif t in SAFE:
            pass
        else:
            unknown.append(t)
    if spicy_hit:
        return "荤", spicy_hit, edgy_hit, unknown
    if edgy_hit:
        return "擦边", spicy_hit, edgy_hit, unknown
    return "素", spicy_hit, edgy_hit, unknown


if __name__ == "__main__":
    cases = [
        (["涂指甲油", "连裤袜", "学生制服"], "擦边"),  # 仙仙桃 JK
        (["兽耳", "玩具"], "荤"),                     # 高桥千凛 H 漫画
        (["原神", "甘雨"], "素"),                     # 纯 IP
        (["丝袜", "无圣光"], "荤"),                   # 荤优先
        (["化妆"], "素"),
        (["兽耳", "未知新tag"], "素"),                # 未知 tag 不猜
    ]
    ok = True
    for tags, expect in cases:
        lv, sh, eh, unk = classify(tags)
        mark = "PASS" if lv == expect else "FAIL"
        if lv != expect:
            ok = False
        print(f"{mark} {tags} → {lv} (期望{expect})" + (f" 未知:{unk}" if unk else ""))
    print("\n配置规模: 荤%d 擦边%d 素%d (来源 spicy_tags.json)" % (len(SPICY), len(EDGY), len(SAFE)))
    print("全部通过" if ok else "有失败!")