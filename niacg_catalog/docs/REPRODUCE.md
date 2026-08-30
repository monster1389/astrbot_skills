# niacg COS 板：搜索 → 下载 → 验货 全链路复现文档

> 实测日期：2026-08-29
> 适用范围：niacg.com **COS 板（classid=1）**，套图板（classid=4）结构相同、图床路径不同（见 §7）
> 结论来源：全部为当日实测，非推测
> 本文档只覆盖**可复现链路**；项目背景、归档规范、分级规则见同目录 `AGENT.md`

---

## 1. 链路总览

```
① 搜索        GET /e/search/?searchget=1&keyboard={关键词}&show=title&classid=1
              → 从结果页提取 /moehome-1-{pid}.html 的 pid + 标题
② 确认目标    可选：GET /moehome-1-{pid}.html 拿详情（标题/tag/封面）
③ 提取主图     GET /moeupup-{classid}-{pid}.html  ← 一次请求暴露全部主图 URL
④ 下载        逐张 GET 主图 URL，Referer 必须指向 niacg.com
⑤ 验货        核对张数 = 主图数、尺寸 2400×3600（竖）/2400×1600（横）、大小范围、无坏图
```

纯 `httpx`，**无需浏览器 / playwright**。

---

## 2. 前置依赖与常量

```python
import httpx, re

PROXY = "http://172.17.0.1:7890"          # 容器内代理，可环境变量覆盖
# httpx 用 proxy= 单字符串，同时作用于 http/https
REF   = "https://www.niacg.com/"           # 全链路 Referer
UA    = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
H     = {"User-Agent": UA, "Referer": REF}
MIN_BYTES = 2000                            # 小于此字节数视为坏图
```

依赖：`httpx`（实测 0.28.1）。代理必须，直连 niacg.com 超时。

---

## 3. ① 搜索（按关键词找套图）

```
GET https://www.niacg.com/e/search/?searchget=1&keyboard=Rikachan&show=title&classid=1
```

- `keyboard`：关键词（实测支持作者名，如 `Rikachan`，返回该作者全部套）
- `classid`：1=COS 板，4=套图板
- 结果页条目结构：`<a href="/moehome-1-{pid}.html">` 包裹封面，`title="Rikachan - Yae Miko"` 属性携带标题

提取（2026-08-29 实测 Rikachan 返回 11 套，pid 覆盖 55627 ~ 135518）：

```python
ids = sorted(set(re.findall(r'/moehome-1-(\d+)\.html', r.text)))
# 标题从 <img ... title="..." class="..."> 取，或进详情页二次确认
```

> 注意：搜索结果里同一 pid 会出现多次（封面+缩略），务必 `set()` 去重。

---

## 4. ② 确认目标（可选）

```
GET https://www.niacg.com/moehome-1-{pid}.html
```

- `<title>` 即完整标题，如 `DJAWA Photo Luniie (루니) - Swimming Lesson`
- 标签链接格式已升级为 `/search/photos?search_query={标签}`（2026-08-29 实测）
- 本步可选：下载器 `collect_urls` 不依赖它，但归档命名、人工确认需要

---

## 5. ③ 提取主图 URL（关键一步）

```
GET https://www.niacg.com/moeupup-{classid}-{pid}.html
```

整页阅读页**一次请求**暴露全部主图，无需翻页。实测 55627 → 52 张、149343 → 124 张。

主图正则（2026-08-29 更新，**datu/hen 双路径**）：

```python
MAIN_IMG_RE = re.compile(
    r'(?:src|data-src)="(https?://(?:boom\.xunge\.cyou/(?:datu|hen)|tu\.xunge\.cyou/tupic)/[^"]+\.(?:jpg|jpeg|webp|png))"'
)

def collect_urls(classid, pid):
    url = f"{REF}moeupup-{classid}-{pid}.html"
    r = httpx.get(url, proxy=PROXY, headers=H, timeout=25)
    r.raise_for_status()
    urls = []
    for m in MAIN_IMG_RE.finditer(r.text):
        u = m.group(1)
        if u not in urls:
            urls.append(u)
    return urls
```

排除项：`gamezy.xunge.cyou/min/slt/*.png`（栏目图标）、`slthh` 推荐图、`/skin/*`（站内静态资源）——正则只匹配 `boom.xunge.cyou` 与 `tu.xunge.cyou` 主图路径，天然排除。

---

## 6. ④ 下载 + ⑤ 验货

```python
def download(urls, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    ok = fail = 0
    for i, u in enumerate(urls):
        r = httpx.get(u, proxy=PROXY, headers=H, timeout=20)
        if r.status_code == 200 and len(r.content) > MIN_BYTES:
            ext = ".webp" if ".webp" in u else ".jpg"
            with open(os.path.join(out_dir, f"{i+1:03d}{ext}"), "wb") as fp:
                fp.write(r.content)
            ok += 1
        else:
            fail += 1
    return ok, fail
```

**验货清单**（2026-08-29 对 55627 实测通过）：

| 检查项 | 实测值 |
|---|---|
| 张数 = 主图数 | 52 = 52 ✓ |
| 下载成功率 | 52/52，FAIL=0 |
| 分辨率 | 竖图 2400×3600（34 张）+ 横图 2400×1600（18 张） |
| 单张大小 | 271KB ~ 665KB |
| 总大小 | 25MB / 套 |
| 坏图（<2KB） | 0 |

---

## 7. 已知坑（全部实测踩过）

1. **图床路径分代**：2024 年及更早上传的图走 `boom.xunge.cyou/datu/年/月/...`，2025 年起的新图走 `boom.xunge.cyou/hen/年/月/日/{id}/{序号}_{hash}.webp`。**正则必须双覆盖**，只认一个会漏一半历史图。
   - 实测样本：55627(2024/05)→`datu`；86671(2025/04)、109565(2025/12)、135518(2026/06)→`hen`
2. **Referer 必须指向 niacg.com**，否则图床拒服（403）。
3. **推荐位杂图污染**：旧脚本 `pull_all.py` 曾把相关推荐位杂图当主图（仙仙桃 41P 混入 3 张），本链路用「只匹配 boom/tu 主图路径」规避。
4. **代理必需**：容器内直连超时，走 `http://172.17.0.1:7890`。
5. **列表页 ≠ 详情页**：`/listinfo-1-{page}.html` 是 COS 板分页（0~279，60 套/页，全板约 1.67 万套），`/moehome-1-{id}.html` 是详情页；`/moehome-1-1.html` 这种"列表页"写法不存在（返回"此信息不存在"）。

---

## 8. 一键复现（使用下载器脚本）

```bash
cd /AstrBot/data/niacg_catalog
# 搜索 → 拿到 pid 后：
python3 scripts/niacg_downloader/niacg_album_downloader.py \
    --set "名字:classid:pid" \
    --out 输出目录
# 例：拉 Rikachan 的 Yae Miko（COS 板 55627）
python3 scripts/niacg_downloader/niacg_album_downloader.py \
    --set "Rikachan_YaeMiko:1:55627" --out /tmp/niacg_test
```

脚本输出即验货摘要：`主图=52 下载OK=52 FAIL=0 目录张数=52`。
