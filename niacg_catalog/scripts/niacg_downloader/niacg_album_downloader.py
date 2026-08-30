#!/usr/bin/env python3
"""
niacg 套图下载器 (niacg_album_downloader)
==========================================
从 niacg.com 按套图 ID 抓取全套图片，从 xunge 图床下载到本地目录。

原理（moeupup 整页阅读链路，2026-08-29 验证）：
  - GET moeupup-{classid}-{pid}.html（整页阅读页）一次暴露全部主图 URL
  - 主图路径两种：boom.xunge.cyou/datu/（COS 分类 classid=1）、tu.xunge.cyou/tupic/（套图分类 classid=4）
  - 下载时 Referer 必须指向 niacg.com，否则图床拒服
  - 纯 httpx，无需浏览器

用法：
  python3 niacg_album_downloader.py --set "名字:classid:pid" [--set ...] [--out 输出目录]

  --set   格式 "名字:classid:pid"（classid: 1=COS, 4=套图），可多次传
          兼容旧格式 "名字:pid:gid"（自动按 classid=4 处理）
  --out   输出根目录，默认当前目录；每套图存到 {out}/{名字}/

示例：
  python3 niacg_album_downloader.py \
      --set "Rikachan:1:55630" \
      --set "Masked Shojo:4:61137" \
      --out ops_dl
"""
import argparse, os, re, sys, httpx

# ---- 环境常量（可用环境变量覆盖）----
PROXY = os.environ.get("NIACG_PROXY", "http://172.17.0.1:7890")
REF   = "https://www.niacg.com/"
UA    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
MIN_BYTES = 2000   # 小于此字节数视为坏图
# httpx 用 proxy= 单字符串，同时作用于 http/https

# 主图路径模式（2026-08-29 实测更新：COS 已从 datu 迁到 hen/{年}/{月}/{日}/{id}/{序号}_{hash}；2022 老套图走 img2.xunge.cyou/d/file/p/）
MAIN_IMG_RE = re.compile(
    r'(?:src|data-src)="(https?://(?:boom\.xunge\.cyou/(?:datu|hen)|tu\.xunge\.cyou/tupic|img2\.xunge\.cyou/d/file/p)/[^"]+\.(?:jpg|jpeg|webp|png))"'
)


def parse_set(s):
    parts = [p.strip() for p in s.split(":")]
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        raise SystemExit(f"格式错误: {s!r}，应为 名字:classid:pid 或 名字:pid:gid")
    # 兼容旧格式 名字:pid:gid（gid 为 10 位 → classid=4 套图）
    if len(parts[2]) >= 9:
        return parts[0], "4", parts[1]
    return parts[0], parts[1], parts[2]


def sample_evenly(paths, n):
    """从已排序路径列表中等距取 n 条（尽量首尾覆盖整套分布）。

    纯逻辑，供下载成功后抽预览用。规则：
      - n<=0 或空列表 → []
      - len(paths) <= n → 全取（不足 n 返回全部）
      - 否则按等分索引取 n 条：首条恒为首元素，末条恒为尾元素。

    Args:
        paths: 排序后的本地图片路径列表。
        n: 要抽的条数（如 5）。

    Returns:
        抽出的路径子列表（保持原序）。
    """
    total = len(paths)
    if n <= 0 or total == 0:
        return []
    if total <= n:
        return list(paths)
    if n == 1:
        return [paths[total // 2]]   # 单张取中间，避免除零
    idxs = []
    # 均匀取整后去重，保证唯一且覆盖首尾
    step = (total - 1) / (n - 1)
    seen = set()
    for k in range(n):
        i = int(round(k * step))
        # 保证末条命中尾元素
        if k == n - 1:
            i = total - 1
        if i not in seen:
            seen.add(i)
            idxs.append(i)
    return [paths[i] for i in idxs]


def mark_pulled(conn, pid):
    """把指定 pid 的套置 pulled=1（已拉整套归档）。

    Args:
        conn: 已连接的 SQLite 连接。
        pid: 站内套图 ID。

    Returns:
        影响行数。库中不存在该 pid 时返回 0（不抛错，容忍点名库外套）。
    """
    cur = conn.execute("UPDATE albums SET pulled=1 WHERE id=?", (pid,))
    conn.commit()
    return cur.rowcount


def collect_urls(classid, pid):
    """抓 moeupup 整页阅读页，提取全部主图 URL（去重保序）"""
    url = f"{REF}moeupup-{classid}-{pid}.html"
    r = httpx.get(url, proxy=PROXY, headers={"User-Agent": UA, "Referer": REF}, timeout=25)
    r.raise_for_status()
    urls = []
    for m in MAIN_IMG_RE.finditer(r.text):
        u = m.group(1)
        if u not in urls:
            urls.append(u)
    return urls


def download(urls, out_dir):
    """带 Referer 下载，序号命名，覆盖已有；返回 (ok, fail)"""
    os.makedirs(out_dir, exist_ok=True)
    ok = fail = 0
    for i, u in enumerate(urls):
        try:
            r = httpx.get(u, proxy=PROXY,
                             headers={"User-Agent": UA, "Referer": REF}, timeout=20)
            if r.status_code == 200 and len(r.content) > MIN_BYTES:
                ext = ".webp" if ".webp" in u else ".jpg"
                with open(os.path.join(out_dir, f"{i+1:03d}{ext}"), "wb") as fp:
                    fp.write(r.content)
                ok += 1
            else:
                fail += 1
        except Exception:
            fail += 1
    return ok, fail


def _list_downloaded(out_dir):
    """列出一套已下载的图片文件绝对路径（按文件名排序，即序号序）。"""
    files = [os.path.join(out_dir, f) for f in sorted(os.listdir(out_dir))
             if not f.startswith(".")]
    return [f for f in files if os.path.isfile(f)]


def main():
    ap = argparse.ArgumentParser(description="niacg 套图下载器（moeupup 链路）")
    ap.add_argument("--set", action="append", required=True,
                    help="套图标识 名字:classid:pid，可多次传")
    ap.add_argument("--out", default=".", help="输出根目录（默认当前目录）")
    ap.add_argument("--db", default=None,
                    help="主库路径；给了则在下载成功后顺手置 pulled=1")
    ap.add_argument("--samples", type=int, default=0,
                    help="每套下载成功后等距抽 N 张，绝对路径打到 stdout")
    args = ap.parse_args()

    sets = [parse_set(s) for s in args.set]
    out_root = os.path.abspath(args.out)
    os.makedirs(out_root, exist_ok=True)

    conn = None
    if args.db is not None:
        import sqlite3
        conn = sqlite3.connect(args.db)   # 只用于置 pulled，不建表

    try:
        for name, classid, pid in sets:
            out_dir = os.path.join(out_root, name)
            print(f"===== 开始 {name} (classid={classid}, pid={pid}) =====", flush=True)
            try:
                urls = collect_urls(classid, pid)
                if not urls:
                    print(f"[{name}] 未找到主图 URL，可能分类不对或页面异常", flush=True)
                    continue
                ok, fail = download(urls, out_dir)
                total = len([f for f in os.listdir(out_dir) if not f.startswith(".")])
                print(f"[{name}] 主图={len(urls)} 下载OK={ok} FAIL={fail} 目录张数={total}", flush=True)

                # 置 pulled=1（仅在给了 --db 且该套确实是已拉取归档的场合）
                if conn is not None:
                    rows = mark_pulled(conn, int(pid))
                    print(f"[PULLED pid={pid} rows={rows}]", flush=True)

                if args.samples > 0:
                    paths = _list_downloaded(out_dir)
                    for p in sample_evenly(paths, args.samples):
                        print(f"[SAMPLE pid={pid}] {p}", flush=True)
            except Exception as e:
                print(f"[{name}] 失败: {e}", flush=True)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
