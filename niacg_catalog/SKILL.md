---
name: niacg_catalog
description: 一问就列最新/未看过的 niacg COS 图集，拼预览 PDF 供挑选，选中整套下载归档。当用户想「看看新图 / 来点cos / 有没有新的 / 最新」时触发，靠语义判断只在无歧义时触发，闲聊不误伤。
---

# niacg_catalog — 「一问」编程序

## 触发（when to trigger）
- 触发词：`新图` / `看看` / `来点cos` / `有没有新的` / `最新`
- 仅当上下文**无歧义**地表达「想看 niacg 新图集」时才触发；闲聊评价其它话题不触发
- 红线：**只拉 COS 板（classid=1）**。套图板（classid=4）不拉，`来点套图` 不算触发词（口误，不扩功能）

## 目的
一问 → 增量同步元数据 → 把**未看过**的 COS 图集拼成预览 PDF → 发给用户挑 → 选中整套下载归档。

## 脚本与职责（执行层，无发送能力）
- `scripts/niacg_catalog/migrate.py` — 建库/建表（幂等）
- `scripts/niacg_catalog/sync_metadata.py` — 增量同步元数据（列表页并发拉取 + 懒补详情页）
- `scripts/niacg_catalog/build_preview_pdf.py` — 查 pdfed=0 拼预览 PDF（纯读库）
- `scripts/niacg_downloader/niacg_album_downloader.py` — 下载整套 → photos/，抽5张返回路径
- 发送由**编排层（Amadeus）**用 send_message_to_user 完成；脚本无发送/删除能力

## 编程序（一问）
1. **建库**（幂等）：`migrate.init_db(db_path)` 确保 catalog/niacg.db 存在（含 preview_batch 表）
2. **增量同步**：每次一问**只拉增量**——`sync_multi(conn, start_page=0, pages=N, concurrency=C)`
   从最新页起，撞到库中已有 pid 即停（已全量建库，增量秒停）。**不每次翻全量**。
3. **懒补详情页**：对即将预览那批（pdfed=0 按 pid 升序最前 60 套）调 `enrich_pending` 补 date/pages/tags
4. **拼预览 PDF**：`build_preview(conn, limit=60)` → 得 PDF 绝对路径
5. **记录批次映射**：发预览前把本批 `(seq→pid→title/model)` **写入 `preview_batch` 表**（batch_id = 时间戳 YYYYMMDD_HHMM）
6. **发预览**：Amadeus 用 send_message_to_user 发 PDF（存档 pdf/ 不删）
7. **用户挑中**：Amadeus 据「第几套」查 `preview_batch` 表 (batch_id, seq) 拿 pid → 调下载器
8. **下载归档**：`niacg_album_downloader --set "model:1:pid" --out photos/ --db catalog/niacg.db --samples 5` → 置 pulled=1 + 抽5张返回路径
9. **发结果**：Amadeus 拿 5 张路径合并转发/拼 PDF（发完删），源图留在 photos/ 不删

## 预览 PDF 命名
`niacg_prev_{batch_id}.pdf`，batch_id = `YYYYMMDD_HHMM` 时间戳，唯一可反查映射。

## 排序与去重
- 预览批排序键 = **pid 升序**（= 最早那批，pid 是站内时间代理，列表页无 date 也可靠）
- pdfed=1 的不再列（已看过）；pulled=1 为已归档

## 红线（勿违）
- 只拉 COS（classid=1），套图不拉
- 图不进库（只存 URL 待拉队列），本体走文件系统 photos/
- 发送不判荤素；spicy 仅归档标注，不参与列/发判定
- 含违法内容（乱伦/裸贷/盗摄）一律不碰
