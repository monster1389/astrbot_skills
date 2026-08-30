# niacg_catalog — 功能设计文档 (design.md)

> 更新：2026-08-30 13:40 (CST)
> 用途：本文件是「一问就列新 COS 图集」功能的**定稿设计**，替代并继承此前 /tmp/niacg_handoff.md 的决策树。
> 后续 agent 接手**直接按此执行**，不必重新推理。
> 可复现的技术链路（搜索→下载→验货）见同目录 `REPRODUCE.md`，本文档不重复。

---

## 1. 一句话需求（tool-nut 拍板）

**一问就列出我还没「看过」的新 COS 图集，带标题 + 日期 + tags + 一张预览图（打包成一份预览 PDF）给我选；我挑中的那套，就整套下载归档。**

**关键修正：发送不判荤素**——荤不荤不作为「列不列」的依据，`pdfed=0` 的统统都要列。荤素仅作为归档标注。

---

## 2. 状态机（两个字段，无 selected）

| 字段 | 含义 | 置 1 时机 |
|---|---|---|
| `pdfed` | 「我看过没」 | **拼过预览 PDF 即置 1**（脚本触发）。置 1 后不再列。 |
| `pulled` | 「我整套品尝过没」 | **整套下载归档完成即置 1**（下载脚本顺手写库）。 |

`selected` 字段**作废，不建**。「选中」只是中间瞬态动作，不落库。

初始化：**存量 photos/ 里 9 模特 / 14 套 / 693 张也全部置 0**（视作未看过、未拉过）。首次一问会按需列/拉。

---

## 3. 触发流程（「问才跑」，非定时）

```
一问(触发词)
  → ① 增量同步元数据
  → ② 查 pdfed=0，按 date「从最早的」开始取，限额 60
  → ③ 拼一份【预览 PDF】(缩略图 + 标题 + 日期 + tags)
      → 发给你 → 【不删，存档 pdf/】
      → 拼成即把这 60 套标 pdfed=1 (=你看过)
你挑中某套
  → ⑤ 下载整套归档 photos/（模特→套）+ 顺手置 pulled=1
     下载成功即从该套均匀抽 5 张，返回 5 张绝对路径
  → ⑥ 拿这 5 张绝对路径直接发你看（合并转发 或 拼 PDF，不用 zip；若拼 PDF 也是发完删）
  → ⑦ 清理临时文件/zip
```

### 3.1 增量同步锚点（确认过）
列表页 `listinfo-1-0.html` **按发布时间倒序**、`pid 递增` 可作锚点。
策略：**从第 1 页（最新）往后翻，撞到库中已有 pid 即停**——只补新增的套，不维护偏移量。db 随时间累积老套，之后「按最早 pdfed=0 拼」才有老图可清。

### 3.2 预览 PDF 拼取规则
- 查 `pdfed=0`，**按 date 升序从最早开始**取，**限额 60**。
- 每套包含：1 张懒加载缩略图(250px) + 标题 + 日期 + tags。
- 拼 PDF 动作由**脚本**完成（非手动），拼成即置 `pdfed=1`。

---

## 4. 判荤（spicy）—— 四级、字符串、仅归档

- 取值：**"荤" / "擦边" / "素" / "未分类"**（字符串，非 0-2 整数）。
- 映射：**`spicy_tags.json` + `spicy.py`**（荤优先查表）。
- **「未分类」= 映射不出的 tag**（表外新 tag 一律归未分类）。
- `spicy` **仅作归档标注，不参与「列不列 / 发不发」判定**。

> 注：`spicy.py` 当前返回三档（荤/擦边/素）+ 未知 tag 列表。落库时需把「未知」映射为字符串「未分类」。

---

## 5. 数据库（SQLite 主库）

库文件：`/AstrBot/data/niacg_catalog/catalog/niacg.db`

### 5.1 主表 `albums`（一行 = 一套图集）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 站内 pid（`/moehome-1-{pid}.html`） |
| `classid` | INTEGER | 1=COS 板（本次主用），4=套图板（不拉） |
| `title` | TEXT | 完整标题 |
| `model` | TEXT | 模特名（按模特分非作者；解析不出保留原始数据，允许未知） |
| `tags` | TEXT | JSON 数组或逗号分隔，站内 tags |
| `pages` | INTEGER | 张数（主图数） |
| `cover_url` | TEXT | 封面 URL |
| `date` | TEXT | 发布日期 |
| `spicy` | TEXT | "荤"/"擦边"/"素"/"未分类"（字符串四档） |
| `pdfed` | INTEGER | 0=未看过 / 1=看过（=拼过预览 PDF） |
| `pulled` | INTEGER | 0=未拉整套 / 1=已拉整套归档 |
| `updated_at` | TEXT | 最后更新 |

> `views/likes/score` 三字段已于 2026-08-28 砍掉（详情页 `video-views` 被模板注释，全站零热度数据）。

---

## 6. 脚本分工与「我（编排层）做」的

**原则（红线）：脚本是执行层，无发送/删除能力；删除须等发送成功确认后由编排层执行。**

### 🤖 纯脚本

| 脚本 | 职责 | 备注 |
|---|---|---|
| `scripts/niacg_catalog/migrate.py` | **只**负责建库/建表/schema 迁移 | **与拉量分离**，不混一处 |
| `scripts/niacg_catalog/sync_metadata.py` | 触发时**增量**抓元数据落库（非一次性全量 1.67 万） | 按 §3.1 锚点 |
| `scripts/niacg_catalog/build_preview_pdf.py` | 查 pdfed=0，按 date 从最早取限额 60，拼预览 PDF；**拼成即置 pdfed=1** | 缩略图+标题+date+tags |
| `scripts/niacg_downloader/niacg_album_downloader.py` | 下载选定整套→photos/（模特→套）；**下完顺手置 pulled=1**；成功即每套均匀抽 5 张，返回 5 张绝对路径 | 「抽几张」逻辑内置于下载器，不单独脚本、不新建目录 |

### 🧠 我（编排层）做

- 触发「一问」→ 调 `sync_metadata` 增量同步 → 调 `build_preview_pdf` 拿 PDF → `send_message_to_user` 发预览 PDF（**不删，存档**）。
- 你在预览里挑中某套 → 调 `niacg_album_downloader` 下载（脚本已置 pulled=1，并返回每套 5 张绝对路径）→ 校验张数/完整性 → 直接拿这 5 张路径用**合并转发** 或 **拼 PDF** 发（不用 zip；若拼 PDF 则发完删）。
- 清理一切临时文件/zip。

---

## 7. 目录约定

根目录：`/AstrBot/data/niacg_catalog/`（独立项目，不放在会话工作区）

```
niacg_catalog/
├── design.md            # 本文档（功能设计定稿）
├── docs/
│   ├── AGENT.md         # 项目背景/规则/决策
│   └── REPRODUCE.md     # 可复现链路（搜索→下载→验货）
├── scripts/
│   ├── niacg_downloader/niacg_album_downloader.py
│   └── niacg_catalog/
│       ├── migrate.py            # 【待建】建库/建表/迁移
│       ├── sync_metadata.py      # 【待建】增量抓元数据
│       ├── build_preview_pdf.py  # 【待建】拼预览 PDF
│       ├── spicy_tags.json       # 荤素四档映射（荤33·擦边35·素323）
│       └── spicy.py              # 分级查表（荤优先）
├── catalog/
│   ├── niacg.db                  # SQLite 主库（【未动工】）
│   ├── exports/                  # JSON/md 导出物
│   └── logs/                     # 抓取日志
├── pdf/                          # 【待建】预览 PDF 存档目录（不删）
└── photos/                       # 源图，按「模特 → 套」二级目录
```

当前 photos：9 模特 / 14 套 / 693 张（AGENT.md 08-29 记录）。

---

## 8. 当前进度

- [x] `spicy.py` + `spicy_tags.json` 荤素映射（已有；需补「未分类」字符串映射）
- [x] 下载器、REPRODUCE.md
- [x] 列表页实测：卡片自带 tags、封面懒加载(250px)、pid 递增
- [x] 增量锚点策略确认（撞到已有 pid 即停）
- [x] 设计定稿（本文件）
- [ ] `migrate.py` 建库/建表
- [ ] `sync_metadata.py` 增量同步
- [ ] `build_preview_pdf.py` 拼预览 PDF（按最早 date、限额 60）
- [ ] `niacg_album_downloader` 下载整套 + 置 pulled=1 + 每套均匀抽 5 张返回绝对路径
- [ ] `pdf/` 目录

---

## 9. 边界 / 红线（勿违反）

- **本功能只拉 COS 板（classid=1）**，套图板（classid=4）不拉。
- **图片不进库**：本体走文件系统（photos/），库内存 URL 作待拉队列；token 纪律——元数据→缩略图(250px)→抽样→脚本闭环，不整包塞上下文。
- **红线**：含违法内容（乱伦/裸贷/盗摄等）一律不碰。
- **新 tag 不猜**：表外 tag 落「未分类」，人工补档后再入表。
- **职责分离**：脚本是执行层，无发送/删除能力；删除须等发送成功确认后由编排层执行。
- **先测后进**：脚本先在 /tmp 等临时位置跑通，再归档进 `scripts/`。
- **来源标注**：社区/官方结论标来源；自推导结论标「推测：」。
