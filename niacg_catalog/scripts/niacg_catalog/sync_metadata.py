"""sync_metadata — 增量抓取列表页元数据并落库。

只负责「拉列表页元数据 → 解析 → 增量筛选 → upsert 落库」。
与建库( migrate )、下载、发送/删除( 编排层 )分离（AGENT.md §4 解耦原则）。
"""

from __future__ import annotations

import re
import json
import sqlite3
import datetime
import urllib.parse
from dataclasses import dataclass, asdict

# ---------------- 常量 ----------------

LIST_RE = re.compile(
    r'<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">(.*?)(?=<div class="col-xs-6 col-sm-4 col-md-3 col-lg-3 list-col col-xl-2">|$)', re.S)
HREF_RE = re.compile(r'/moehome-1-(\d+)\.html')
TITLE_RE = re.compile(r'title="([^"]+)"')
COVER_RE = re.compile(r'data-src="([^"]+)"')
TAG_RE = re.compile(r'class="tag">([^<]+)<')
TS_RE = re.compile(r'/(\d{10})/')  # 封面 URL 里的 unix 秒时间戳
UNCLASSIFIED = "未分类"

# 详情页字段正则
DP_DATE_RE = re.compile(r'datePublished"\s+content="([\d-]+)"')   # 上架日期
DP_PAGES_RE = re.compile(r'页数\s*[：:]\s*([0-9]+)')               # 张数
DP_TAG_RE = re.compile(r'/search/photos\?search_query=([^"&]+)')   # 详情页 tag


# ---------------- 领域模型 ----------------

@dataclass
class Album:
    """一套图集的元数据（对应 albums 表一行）。"""
    pid: int                       # 站内 pid（主键）
    classid: int                   # 1=COS 板 / 4=套图板
    title: str = ""
    model: str = UNCLASSIFIED      # 模特名，白名单初始猜测，下载回填覆盖
    tags: str = ""                 # JSON 数组或逗号分隔
    pages: int | None = None       # 张数，列表页查不到，详情页补全
    cover_url: str = ""
    preview_urls: str = ""         # 缩略图 URL JSON 列表（详情页 slthh 补全）
    date: str = ""                 # 发布日期，详情页 datePublished
    spicy: str = UNCLASSIFIED
    pdfed: int = 0
    pulled: int = 0
    updated_at: str = ""


# ---------------- extract_model（纯逻辑） ----------------

def _normalize_candidate(name: str) -> str:
    """归一化候选/白名单：剥括号内容、去首尾符号。"""
    name = re.sub(r'\(.*?\)', '', name)
    return name.strip(' -!·:')


def extract_candidate(title: str) -> str:
    """从标题抽取模特候选（纯文本，不含白名单匹配）。

    抽取规则：优先按 ` - ` 分割取左段；无则按双空格；再无则整串。
    随后归一化（剥括号、去首尾符号）。

    Args:
        title: 列表页标题（如 `Luniie (루니) - Swimming Lessons Sunna`）。

    Returns:
        归一化后的候选字符串（可能为空串）。
    """
    cand = title
    for sep in (' - ', '  '):
        if sep in cand:
            cand = cand.split(sep)[0]
            break
    return _normalize_candidate(cand)


def extract_model(title: str, whitelist: set[str]) -> str:
    """从标题抽取模特候选，与现有 photos/ 白名单做归一化精确匹配。

    匹配策略（拍板口径）：候选与白名单都做同样归一化，然后**完全相等**才算
    命中（不模糊/不子串）；命中返回白名单名，未命中归「未分类」。

    Args:
        title: 列表页标题（如 `Luniie (루니) - Swimming Lessons Sunna`）。
        whitelist: 现有 photos/ 顶层模特目录名集合（除「未分类」）。

    Returns:
        白名单模特名；未命中时返回「未分类」。
    """
    cand = extract_candidate(title)
    if not cand:
        return UNCLASSIFIED
    for w in whitelist:
        if _normalize_candidate(w) == cand:
            return w
    return UNCLASSIFIED


# ---------------- S2：卡片解析 ----------------

def _parse_album(block: str, classid: int, whitelist: set[str]) -> Album:
    """从单个卡片块解析出一套 Album。

    Args:
        block: 一个列表卡片块的 HTML 片段。
        classid: 板块号（1=COS / 4=套图）。
        whitelist: 现有 photos/ 模特目录名集合。

    Returns:
        Album 对象（pages 恒为 None，date 由封面时间戳派生）。

    Raises:
        ValueError: 缺 pid / title / cover_url 时抛出（无兜底，显式报错）。
    """
    href = HREF_RE.search(block)
    title = TITLE_RE.search(block)
    cover = COVER_RE.search(block)
    if not (href and title and cover):
        raise ValueError(f"卡片块缺必备字段: pid={bool(href)} title={bool(title)} cover={bool(cover)}")

    pid = int(href.group(1))
    full_title = title.group(1)
    cover_url = cover.group(1)
    tags = ",".join(TAG_RE.findall(block))
    model = extract_model(full_title, whitelist)
    # date/pages/preview_urls 列表页拿不到可靠值，留空/None，由详情页 enrich 补全
    return Album(
        pid=pid,
        classid=classid,
        title=full_title,
        model=model,
        tags=tags,
        pages=None,           # 列表页无张数，详情页补
        cover_url=cover_url,
        preview_urls=cover_url,  # 列表页阶段只能用封面这张预览
        date="",              # 详情页 datePublished 补
        updated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def parse_list_page(html: str, classid: int = 1, whitelist: set[str] | None = None) -> list[Album]:
    """解析列表页 HTML，返回全部卡片对应的 Album 列表。

    Args:
        html: 列表页完整 HTML 文本。
        classid: 板块号（默认 COS 板 1）。
        whitelist: 现有 photos/ 模特目录名集合；为 None 时全部模特归「未分类」。

    Returns:
        Album 列表（按页面原始顺序，即时间倒序）。
    """
    whitelist = whitelist or set()
    blocks = LIST_RE.findall(html)
    return [_parse_album(b, classid, whitelist) for b in blocks]


# ---------------- S4：详情页补全 ----------------

def enrich_from_detail(detail_html: str) -> dict:
    """从详情页 HTML 补全一套图的 date/pages/preview_urls/tags。

    一次详情页请求即可拿齐这些字段（拍板口径）。字段来源：
    - date: datePublished（上架日期）
    - pages: 「页数」字段
    - preview_urls: 该套专属缩略图 URL 列表（方案B，hen/d_file 路径 + date 归属判定，排除推荐位）
    - tags: 详情页 tag 链接（URL 解码后逗号分隔）

    Args:
        detail_html: moehome-{pid}.html 的完整 HTML 文本。

    Returns:
        dict，含 date/pages/preview_urls/tags 键；字段缺失时 date/pages 置空/None，
        preview_urls 置空串，tags 用空串占位（不一刀切报错，因部分详情页个别字段缺失）。
    """
    dm = DP_DATE_RE.search(detail_html)
    pm = DP_PAGES_RE.search(detail_html)
    date = dm.group(1) if dm else ""
    # 方案A：preview_urls 恒用列表页封面 cover_url（列表页补时已设），详情页不回填。
    # 详情页不再抓缩略图（slthh 是推荐位、hen/d_file 是原图，都不适合当预览）。
    # tags：去重 + 单次 URL 解码（%E5%85%A8%E5%BD%A9 → 全彩）
    tags = ",".join(dict.fromkeys(
        urllib.parse.unquote(t) for t in DP_TAG_RE.findall(detail_html)))

    pages = int(pm.group(1)) if pm else None
    return {
        "date": date,
        "pages": pages,
        "preview_urls": "",
        "tags": tags,
    }


# ---------------- S3：增量停止 ----------------

def select_new(albums: list[Album], existing_pids: set[int]) -> list[Album]:
    """增量筛选：按页顶→页尾（最新→最旧），撞到库中已有 pid 即停。

    约定列表页按发布时间倒序，页顶为最新。因此从前往后扫，
    一旦遇到库中已有的 pid，说明后续更老的都已入库，直接截断返回。

    Args:
        albums: 本次解析出的 Album 列表（时间倒序）。
        existing_pids: 库中已存在的 pid 集合。

    Returns:
        需要入库的新增前缀段（从页顶到首次撞到已有 pid 之前）。
    """
    new: list[Album] = []
    for a in albums:
        if a.pid in existing_pids:
            break
        new.append(a)
    return new


# ---------------- S4：落库 ----------------

UPSERT_SQL = """
INSERT INTO albums (id,classid,title,model,tags,pages,cover_url,preview_urls,date,spicy,updated_at)
VALUES (:pid,:classid,:title,:model,:tags,:pages,:cover_url,:preview_urls,:date,:spicy,:updated_at)
ON CONFLICT(id) DO UPDATE SET
    classid=excluded.classid,
    title=excluded.title,
    model=excluded.model,
    tags=excluded.tags,
    pages=excluded.pages,
    cover_url=excluded.cover_url,
    preview_urls=excluded.preview_urls,
    date=excluded.date,
    spicy=excluded.spicy,
    updated_at=excluded.updated_at
"""


def upsert_albums(conn: sqlite3.Connection, albums: list[Album]) -> int:
    """将 Album 列表按 pid upsert 落库。

    Args:
        conn: 已连接的 SQLite 连接（需已建 albums 表）。
        albums: 待入库的 Album 列表。

    Returns:
        处理的记录数。

    Raises:
        sqlite3.Error: 落库失败时抛出。
    """
    if not albums:
        return 0
    conn.executemany(UPSERT_SQL, [asdict(a) for a in albums])
    conn.commit()
    return len(albums)


# ---------------- S6：网络层与编排（沾 IO，活体验证） ----------------

import os
import httpx

PROXY = os.environ.get("NIACG_PROXY", "http://172.17.0.1:7890")
REF = "https://www.niacg.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
HTTP_H = {"User-Agent": UA, "Referer": REF}

LIST_PAGE_URL = "listinfo-1-{page}.html"      # COS 板分页（0 起=最新）
DETAIL_PAGE_URL = "moehome-1-{pid}.html"      # 详情页


def list_whitelist(photos_dir: str) -> set[str]:
    """运行时扫描 photos/ 顶层目录作为模特白名单（除「未分类」）。

    Args:
        photos_dir: photos/ 根目录路径。

    Returns:
        模特目录名集合。
    """
    if not os.path.isdir(photos_dir):
        return set()
    return {d for d in os.listdir(photos_dir)
            if os.path.isdir(os.path.join(photos_dir, d)) and d != UNCLASSIFIED}


def _get(url: str, timeout: int = 25, retries: int = 3) -> str:
    """发 GET 请求，带代理与 Referer；网络抖动时有限重试。

    Args:
        url: 目标 URL。
        timeout: 单次请求超时秒数。
        retries: 失败重试次数（网络层容错，非吞异常）。

    Returns:
        响应的 HTML 文本。

    Raises:
        httpx.HTTPError: 重试耗尽仍失败时抛出。
    """
    import time as _time
    last = None
    for _ in range(retries):
        try:
            r = httpx.get(url, proxy=PROXY, headers=HTTP_H, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            _time.sleep(1.0)
    raise last if last else RuntimeError("请求失败")


def fetch_list_page(page: int) -> str:
    """拉取第 page 页的列表页 HTML（0 起=最新）。"""
    return _get(REF + LIST_PAGE_URL.format(page=page))


def fetch_detail(pid: int) -> str:
    """拉取 pid 的详情页 HTML。"""
    return _get(REF + DETAIL_PAGE_URL.format(pid=pid))


def sync_meta(conn: sqlite3.Connection, page: int, photos_dir: str,
              f_list: object = None, f_detail: object = None) -> int:
    """执行一次「纯列表页 + 增量落库」同步，**不碰详情页**。

    2026-08-30 拍板：全量建库不做详情页补全（每套一次请求，全量约 18,000 次 → 9h）。
    date/pages/tags 留空，交由预览时 `enrich_pending` 懒补（真正要预览那批才补）。

    Args:
        conn: 已初始化的 SQLite 连接（需已建 albums 表）。
        page: 要同步的列表页号（0 起=最新）。
        photos_dir: photos/ 根目录（用于动态白名单）。
        f_list: 可选，列表页抓取函数（默认为 fetch_list_page），测试注入用。
        f_detail: 保留签名但此处不使用（仅为接口一致性；懒补走 enrich_pending）。

    Returns:
        新入库的记录数。

    Raises:
        httpx.HTTPError: 抓取失败时抛出。
    """
    f_list = f_list or fetch_list_page

    whitelist = list_whitelist(photos_dir)
    albums = parse_list_page(f_list(page), classid=1, whitelist=whitelist)

    # 增量筛选 + 落库（date/pages 留空，preview_urls 用列表页封面）
    existing = {r[0] for r in conn.execute("SELECT id FROM albums")}
    new = select_new(albums, existing)
    if not new:
        print(f"  [sync_meta] page {page} 无新增（首个 pid 已在库中，撞停）")
        return 0
    n = upsert_albums(conn, new)
    print(f"  [sync_meta] page {page}: 解析{len(albums)}套 / 新增{len(new)}套 落库{n}行（未补详情页）")
    return n


def enrich_pending(conn: sqlite3.Connection, pids: list[int],
                   f_detail: object = None, concurrency: int = 4) -> int:
    """对指定 pids 并发进详情页补全 date/pages/tags 并回写库（懒补）。

    供预览 PDF 场景调用：sync_meta 只入库基础元数据，拼预览前对真正要预览那批补全。

    Args:
        conn: 已初始化的 SQLite 连接。
        pids: 要补全的 pid 列表。
        f_detail: 可选，详情页抓取函数（默认为 fetch_detail），测试注入用。
        concurrency: 并发线程数，默认 4。

    Returns:
        成功补全并回写的记录数（某 pid 库中不存在时跳过，不计入）。

    Raises:
        httpx.HTTPError: 抓取失败时抛出（f_detail 内部处理）。
    """
    if not pids:
        return 0
    f_detail = f_detail or fetch_detail

    # 先查库中已存在的 pid，缺失的跳过（容忍点名库外套）
    marks = ",".join("?" * len(pids))
    existing = {r[0] for r in conn.execute(f"SELECT id FROM albums WHERE id IN ({marks})", pids)}
    targets = [pid for pid in pids if pid in existing]
    if not targets:
        print("  [enrich_pending] 无库中存在 pid，跳过")
        return 0

    def _work(pid: int) -> tuple[int, dict]:
        detail_html = f_detail(pid)
        return pid, enrich_from_detail(detail_html)

    results = {}
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=max(1, concurrency)) as ex:
        for pid, enriched in ex.map(_work, targets):
            results[pid] = enriched

    n = 0
    for pid, en in results.items():
        conn.execute(
            "UPDATE albums SET date=?, pages=?, tags=? WHERE id=?",
            (en["date"], en["pages"], en["tags"], pid))
        n += 1
    conn.commit()
    print(f"  [enrich_pending] 补全 {n} 套详情页字段")
    return n


def sync(conn: sqlite3.Connection, page: int, photos_dir: str, max_detail: int | None = None,
         f_list: object = None, f_detail: object = None) -> int:
    """兼容入口：等价于 sync_meta（2026-08-30 起全量建库不再补详情页）。

    保留是为了不破坏旧 CLI 调用与旧测试 import；行为 = 纯列表页同步。
    """
    return sync_meta(conn, page, photos_dir, f_list=f_list, f_detail=f_detail)


def sync_multi(conn: sqlite3.Connection, start_page: int, pages: int, photos_dir: str,
               concurrency: int = 4, f_list: object = None) -> int:
    """并发抓取 start_page 起共 pages 页列表页，按序增量落库（撞已有 pid 即停）。

    全量建库走此入口：每一页 60 套，并发抓取多页 HTML 后按 page 顺序 parse+落库。
    「撞到库中已有 pid 即停」逻辑按页序生效——某页无新增即 stop（更老页也已在库）。

    Args:
        conn: 已初始化的 SQLite 连接。
        start_page: 起始列表页号（0 起=最新）。
        pages: 要抓取的页数（含 start_page）。
        photos_dir: photos/ 根目录（白名单）。
        concurrency: 并发线程数，默认 4。
        f_list: 可选，列表页抓取函数（默认为 fetch_list_page），测试注入用。

    Returns:
        总入库记录数。
    """
    f_list = f_list or fetch_list_page
    page_nums = list(range(start_page, start_page + pages))

    htmls: dict[int, str] = {}
    if concurrency > 1:
        import concurrent.futures as cf
        with cf.ThreadPoolExecutor(max_workers=concurrency) as ex:
            for p, h in zip(page_nums, ex.map(f_list, page_nums)):
                htmls[p] = h
    else:
        for p in page_nums:
            htmls[p] = f_list(p)

    total = 0
    for p in page_nums:
        n = sync_meta(conn, p, photos_dir,
                      f_list=lambda page, html=htmls[p]: html)
        total += n
        if n == 0:
            print(f"  [sync_multi] page {p} 无新增，撞停止")
            break
    return total


if __name__ == "__main__":
    import argparse
    import sys as _sys
    # 保证同目录 migrate 可被 import（CLI 直接运行时）
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    ap = argparse.ArgumentParser(description="niacg COS 列表页增量同步元数据")
    ap.add_argument("--page", type=int, default=0, help="起始列表页号（0 起=最新）")
    ap.add_argument("--pages", type=int, default=1,
                    help="抓取页数（含 start_page，全量约 300 页）")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="并发抓取线程数")
    ap.add_argument("--db", default="/AstrBot/data/skills/niacg_catalog/catalog/niacg.db",
                    help="SQLite 主库路径")
    ap.add_argument("--photos", default="/AstrBot/data/skills/niacg_catalog/photos",
                    help="photos/ 根目录")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.db), exist_ok=True)
    from migrate import init_db
    conn = init_db(args.db)
    n = sync_multi(conn, args.page, args.pages, args.photos, args.concurrency)
    print(f"完成，共入库 {n} 条。")

