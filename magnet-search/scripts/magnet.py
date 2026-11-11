#!/usr/bin/env python3
"""bt4g 磁力搜索 —— 走 RSS 接口，绕过 Cloudflare。

用法:
    python3 magnet.py 关键词 [条数]

示例:
    python3 magnet.py 蘿莉 15
    python3 magnet.py ubuntu 5

代理:
    默认走宿主机代理 http://172.17.0.1:7890（本容器无默认路由，必须走）。
    覆盖: PROXY=http://其他:端口
    强制直连: PROXY=

注意:
    简中关键词常被站点过滤返回空结果，换繁体或英文即可。
"""
import os
import re
import sys
import html
import urllib.parse
import urllib.request

RSS = "https://bt4g.org/search?q={}&page=rss"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
DEFAULT_PROXY = "http://172.17.0.1:7890"


def fetch(keyword, timeout=30):
    # PROXY 环境变量优先；未设置时用默认代理；设为空串则强制直连
    proxy = os.environ["PROXY"] if "PROXY" in os.environ else DEFAULT_PROXY
    proxy = proxy or None
    handlers = [urllib.request.ProxyHandler({"http": proxy, "https": proxy})] if proxy else []
    opener = urllib.request.build_opener(*handlers)
    opener.addheaders = [("User-Agent", UA)]
    url = RSS.format(urllib.parse.quote(keyword))
    with opener.open(url, timeout=timeout) as r:
        return html.unescape(r.read().decode("utf-8", "replace"))


def parse(text):
    """返回 [(infohash, magnet), ...]，保持站点原始顺序。"""
    out = []
    for block in re.findall(r"<item>(.*?)</item>", text, re.S):
        m = re.search(r"<link>(.*?)</link>", block, re.S)
        if not m:
            continue
        magnet = html.unescape(m.group(1)).strip()
        h = re.search(r"btih:([A-Za-z0-9]{32,40})", magnet)
        out.append((h.group(1) if h else "", magnet))
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip())
        return 1

    keyword = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    try:
        results = parse(fetch(keyword))[:limit]
    except Exception as e:
        print(f"请求失败: {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    if not results:
        print("无结果。简体中文常被过滤，换繁体或英文再试。", file=sys.stderr)
        return 2

    for i, (infohash, magnet) in enumerate(results, 1):
        print(f"{i:02d}  {magnet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
