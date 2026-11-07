---
name: niacg_catalog
description: 一问就列最新/未看过的 niacg COS 图集，拼预览 PDF 供挑选，选中整套下载归档。触发词：看看新图 / 来点cos / 有没有新的 / 最新 / 下一批。
---

# niacg_catalog — 「一问」编程序

## 触发（when to trigger）
- 触发词：`新图` / `看看` / `来点cos` / `有没有新的` / `最新`
- 仅当上下文表达「想看 niacg 新图集」时触发；闲聊评价其它话题不触发

## 目的
一问 → 增量同步元数据 → 把**未看过**的 COS 图集拼成预览 PDF → 发给用户挑 → 选中整套下载归档。

## 脚本与职责（执行层，无发送能力）
- `scripts/niacg_catalog/migrate.py` — 建库/建表（幂等）
- `scripts/niacg_catalog/sync_metadata.py` — 增量同步元数据（列表页并发拉取 + 懒补详情页）
- `scripts/niacg_catalog/build_preview_pdf.py` — 查 pdfed=0 拼预览 PDF（纯读库）
- `scripts/niacg_downloader/niacg_album_downloader.py` — 下载整套 → photos/，抽5张返回路径
- 发送由 **LLM** 用 send_message_to_user 完成；脚本无发送/删除能力

### 运行约定
- 脚本相对路径（`scripts/`、`catalog/niacg.db`、`photos/`、`pdf/`）均以 `skills/niacg_catalog/` 为根运行，勿在会话工作区跑。
- `--samples N`：每套下载成功等距抽 N 张、绝对路径打到 stdout（LLM 据此发图）；`--concurrency` 每套并发线程数（默认 4）。

## 编程序（一问）
1. **建库**（幂等）：`migrate.init_db(db_path)` 确保 catalog/niacg.db 存在（含 preview_batch 表）
2. **增量同步**：每次一问**只拉增量**——`sync_multi(conn, start_page=0, pages=N, concurrency=C)`
   从最新页起，撞到库中已有 id 即停（已全量建库，增量秒停）。**不每次翻全量**。
3. **生成预览**：`build_preview(conn, limit=60)` → 返回 `(pdf_path, batch_id)`。一次调用即完成「懒补详情页字段（enrich）→ 拼预览 PDF → 写 `preview_batch` 映射（batch_id=时间戳）→ 置 pdfed=1」；LLM 只调这一下，拿 `pdf_path` 发、拿 `batch_id` 记录。
4. **用户挑中**：LLM 据「第几套」调 `query_preview_batch(conn, batch_id, seq)` 拿 `{album_id, title}` → 调下载器。**不手写 SELECT**。
5. **下载归档**：`niacg_album_downloader --set "{套名}:1:{album_id}" [--set ...] --out photos/ --db catalog/niacg.db --samples 5 [--concurrency 4]`
   - **套名 = `preview_batch` 里存的完整站方 title**，不做任何截取（不切 `-`/`[ ]` 前段）。
   - **多套**：`--set` 可传多个；每套的 model 由脚本内部白名单判定（`resolve_model`），**LLM 无需手填**。`--model` 仅作可选 override。
   - 归档路径：**photos/{模特}/{套名}/** 两级；model 不明确时脚本自动落 `photos/unclassified/{套名}/`。
6. **发结果**：LLM 拿 5 张路径合并转发/拼 PDF（发完删），源图留在 photos/ 不删

## 预览 PDF 命名
`niacg_prev_{batch_id}.pdf`，batch_id = `YYYYMMDD_HHMM` 时间戳，唯一可反查映射。

## 排序与去重
- 预览批排序键 = **id 升序**（= 最早那批，id 是站内时间代理，列表页无 date 也可靠）
- pdfed=1 的不再列（已看过）；pulled=1 为已归档

## 发送约定（预览 PDF 与结果图）
- **放一处**：发预览 PDF 用 `send_message_to_user` 一条 `type=file` 消息（`path` 指 `pdf/` 源码路径）；发结果图用 5 张路径合并转发或拼 PDF（发完删）。源图留在 photos/ 不删。
- **成功要素**：文件在 `data/skills/niacg_catalog/pdf/`（NapCat 可读），**勿放 `/tmp`**；英文名 + 完整 `.pdf` 后缀（`niacg_prev_{batch_id}.pdf`），**别改中文/去后缀**（QQ 会吞后缀发不出）；体积别太大（JPEG 约 1.7MB 级，别用 PNG 大图）；返回 `Message sent` 即送达。
- ⚠️ **陷阱**：发文件的成功记录**不走 `render.deliver` 日志**（那条只渲染 assistant 文本回复）。**别拿「render.deliver 无『已发送 文件』」当发送失败**——一次用英文名+完整后缀即可，别改中文名/挪路径/复制副本。
